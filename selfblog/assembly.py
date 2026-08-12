"""Assembly infrastructure for unified multi-project documentation deployment via GitHub Actions dispatch and Cloudflare Pages."""

from __future__ import annotations

import base64
import dataclasses
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from collections.abc import Mapping

from selfblog.shared import POSTS_SEGMENT
from selfblog.verify import OUTBOUND_CACHE_PATH
from selfdoc_core import effects

# Files a per-project selfdoc build emits for its own standalone hosting.
# They are meaningless (and actively harmful) once the build is grafted into
# the assembly tree, which serves one set of headers, redirects and worker
# for the whole site.
DEPLOY_ARTIFACT_NAMES = ("_headers", "_redirects", "_worker.js")
DEPLOY_ARTIFACT_SUFFIXES = (".gz", ".br")

# Who may have written a path inside a project's site subtree.  Every
# publisher records the set of paths it produced, and prunes only paths it
# produced before and does not produce now -- see :func:`prune_plan`.
#
#   release  the full-scope integrate the deploy workflow runs from a tag
#   docs     `selfblog docs publish`, a documentation update with no release
#   posts    `selfblog post publish` and the posts-scope integrate
#
# The point of separating them is that a full build no longer knows how to
# destroy content it never produced: an out-of-band post or documentation
# page belongs to another owner, so a release that does not carry it leaves
# it alone.
PUBLISH_OWNERS = ("release", "docs", "posts")

# The published-file record's format.  Version 2 addresses every path from
# site/ rather than from the project's own subtree, because posts stopped
# living inside it: they are site-level, at blog/<post-slug>/, so one record
# now names paths in two different places and a single namespace is the only
# way they cannot be confused.  A version-1 record is refused, never
# reinterpreted -- see :func:`parse_files_manifest`.
FILES_RECORD_VERSION = 2

# Sidecars under manifests/ that are not project manifests and must not be
# loaded as one.
MANIFEST_SIDECAR_SUFFIXES = ("-revisions.json", "-files.json", "-listing.json")

# Directories under site/ that belong to the assembly itself rather than to
# any project, so membership reconciliation never mistakes one for a slug.
SITE_RESERVED_DIRS = ("blog", "projects", "pagefind")

# Scopes a dispatch may carry. "" from a client payload that omits the key
# means a full project build; the workflow always passes the flag.
INTEGRATE_SCOPES = ("full", "posts", "shared-only")

# The one path in the assembly repo that holds the generated deploy workflow.
WORKFLOW_PATH = ".github/workflows/deploy.yml"

# The hand-edited file in the assembly repo that declares which projects the
# unified site serves.
ROSTER_PATH = "roster.toml"

# The derived record of what each declared project last deployed.
PROJECTS_PATH = "projects.json"


_BUILD_TIMEOUT = 1800
_GIT_TIMEOUT = 300
_INDEX_TIMEOUT = 900

#: PyPI's JSON metadata endpoint, the one registry every pinned tool comes
#: from.  A pin is checked against this before it is written into a
#: workflow -- see :func:`check_pins_are_published`.
PYPI_JSON_URL = "https://pypi.org/pypi/{package}/json"

_REGISTRY_TIMEOUT = 15


@dataclasses.dataclass(frozen=True)
class ToolchainPins:
    """The exact versions the generated deploy workflow installs.

    All three tools on the install line are pinned, for one reason that
    applies equally to each: the deploy installs its toolchain fresh on
    every dispatch, so an unpinned name means "whatever was newest at
    dispatch time".  A released flag change once broke every project's
    deploy at once that way, and selfdoc -- the tool that actually builds
    the docs -- floated for longer than selfblog did.

    The pins are not the banned kind of ceiling: ``assembly sync-workflow``
    rewrites the whole file on every release, so this is a regenerated
    lock, not an upper bound a human wrote once and forgot.

    Every field is required.  :func:`resolve_toolchain_pins` is what turns
    an environment into a set of pins; this type only carries them.
    """

    selfblog: str
    selfdoc: str
    pagefind: str

    def __post_init__(self):
        for field in dataclasses.fields(self):
            if not getattr(self, field.name):
                raise ValueError(
                    f"ToolchainPins.{field.name} is required: the generated "
                    f"workflow pins every tool it installs, and there is no "
                    f"default version."
                )

    def as_registry_map(self) -> dict[str, str]:
        """Return PyPI distribution name -> pinned version, for every pin.

        The keys are registry names, not install specifiers: pagefind is
        installed as ``pagefind[bin]`` but published as ``pagefind``.
        """
        return {
            "selfblog": self.selfblog,
            "selfdoc": self.selfdoc,
            "pagefind": self.pagefind,
        }


# -- the declared roster -----------------------------------------------------


#: Every key a ``[[project]]`` block may carry, all of them required.  An
#: unknown key is a hard error rather than a silently ignored line: a typo in
#: a membership declaration would otherwise retire a project.
ROSTER_FIELDS = ("slug", "repo")

#: Every top-level key the roster document may carry.  ``home`` names the one
#: project whose content root is the site root; see :class:`Roster`.
ROSTER_TOP_LEVEL_KEYS = ("home", "project")

ROSTER_HEADER = """\
# The assembly's membership: every project the unified site serves.
#
# This file is the declaration; the deploy reconciles the site to it and can
# never add to it. A project with no [[project]] block here has its subtree,
# its manifests, its membership record and its search-index entries removed at
# the next deploy -- which is what `selfblog assembly retire <slug>` does in
# one operation.
#
# `home` names the one declared project that IS the front page: its pages are
# emitted at the site root instead of under site/<slug>/, it is left out of the
# generated project listing, and it is required -- a site needs a front page,
# so there is no default and no more than one.
#
# projects.json next to this file is derived state, rewritten by every deploy.
# Edit this file, never that one.
"""


@dataclasses.dataclass(frozen=True)
class RosterEntry:
    """One declared member of the assembly.

    ``repo`` is part of the declaration rather than derived from a dispatch
    so that a slug has one owning repository on record: a dispatch arriving
    for a declared slug from a different repository is a hard error instead
    of a silent takeover of that slug's section.
    """

    slug: str
    repo: str


class Roster(Mapping):
    """The declared membership, plus the one project that is the site root.

    A roster is read as a mapping of slug -> :class:`RosterEntry` everywhere
    membership is the question, which is most places.  ``home`` is the extra
    fact only the front page cares about: exactly one declared slug whose
    content root emits at the site root rather than under ``site/<slug>/``.

    The home project is an ordinary project in every other respect -- a real
    repository that dispatches its own deploys.  Being home is a flag on it,
    never a separate kind of thing and never the assembly repository itself.
    """

    __slots__ = ("_projects", "home")

    def __init__(self, projects, home: str):
        self._projects = dict(projects)
        self.home = home

    def __getitem__(self, slug: str) -> RosterEntry:
        return self._projects[slug]

    def __iter__(self):
        return iter(self._projects)

    def __len__(self) -> int:
        return len(self._projects)

    def __repr__(self) -> str:
        return f"Roster(projects={sorted(self._projects)!r}, home={self.home!r})"


def render_roster(entries, home: str = "") -> str:
    """Return the TOML text for *entries* (an iterable of RosterEntry).

    *home* is written as the top-level ``home`` key.  An empty *home* leaves
    a commented placeholder instead: a roster with no home is refused when it
    is read, and a scaffolded file that silently named some project home
    would be choosing the front page on the author's behalf.
    """
    head = (
        f"home = {json.dumps(home)}\n" if home
        else '# home = "<slug>"   # required: the project served at the site root\n'
    )
    blocks = []
    for entry in sorted(entries, key=lambda e: e.slug):
        blocks.append(
            "[[project]]\n"
            f"slug = {json.dumps(entry.slug)}\n"
            f"repo = {json.dumps(entry.repo)}\n"
        )
    return ROSTER_HEADER + "\n" + head + "\n" + "\n".join(blocks)


def parse_roster(text: str, *, source: str = ROSTER_PATH) -> Roster:
    """Return the :class:`Roster` the roster document *text* declares.

    Validation is strict in every direction: an unknown top-level table, an
    unknown key on a block, a missing or empty required key, a duplicate
    slug, and a slug that collides with one of the assembly's own directories
    are each a hard error naming the offending declaration.  A roster with no
    ``[[project]]`` block at all is legal and means an empty assembly.

    The ``home`` key is required and names a declared slug.  Both failures
    are hard errors: a missing key because a site needs a front page and no
    project may be picked for the author by default, and a key naming an
    undeclared slug because the front page has to be something the assembly
    actually serves.
    """
    import tomllib

    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise RuntimeError(f"{source} is not valid TOML: {exc}") from exc

    unknown_tables = sorted(set(data) - set(ROSTER_TOP_LEVEL_KEYS))
    if unknown_tables:
        raise RuntimeError(
            f"{source} declares unknown top-level key(s) "
            f"{', '.join(repr(k) for k in unknown_tables)}. The roster holds "
            f"nothing but [[project]] blocks and the 'home' key."
        )

    raw = data.get("project", [])
    if not isinstance(raw, list):
        raise RuntimeError(
            f"{source}: 'project' must be a list of [[project]] blocks."
        )

    entries: dict[str, RosterEntry] = {}
    for index, item in enumerate(raw, start=1):
        where = f"{source}: [[project]] #{index}"
        if not isinstance(item, dict):
            raise RuntimeError(f"{where} is not a table.")
        unknown = sorted(set(item) - set(ROSTER_FIELDS))
        if unknown:
            raise RuntimeError(
                f"{where} declares unknown key(s) "
                f"{', '.join(repr(k) for k in unknown)}. A [[project]] block "
                f"carries exactly {', '.join(ROSTER_FIELDS)}."
            )
        missing = [f for f in ROSTER_FIELDS if not item.get(f)]
        if missing:
            raise RuntimeError(
                f"{where} is missing {', '.join(missing)}. Every declared "
                f"project names {', '.join(ROSTER_FIELDS)}."
            )
        slug = str(item["slug"])
        if slug in SITE_RESERVED_DIRS:
            raise RuntimeError(
                f"{where} claims the slug {slug!r}, which is one of the "
                f"assembly's own directories "
                f"({', '.join(SITE_RESERVED_DIRS)}). Give the project a "
                f"different slug."
            )
        if slug in entries:
            raise RuntimeError(
                f"{where} repeats the slug {slug!r}, which an earlier block "
                f"already declares."
            )
        entries[slug] = RosterEntry(slug=slug, repo=str(item["repo"]))

    home = data.get("home")
    if home is None or (isinstance(home, str) and not home.strip()):
        declared = ", ".join(sorted(entries)) or "(none)"
        raise RuntimeError(
            f"{source} declares no home project. Exactly one declared project "
            f"is the site's front page: its pages are emitted at the site "
            f"root instead of under site/<slug>/. There is no default -- add "
            f'a top-level home = "<slug>" naming one of the declared '
            f"projects. Declared projects: {declared}."
        )
    if not isinstance(home, str):
        raise RuntimeError(
            f"{source}: home must be a slug string, got {home!r}."
        )
    home = home.strip()
    if home not in entries:
        declared = ", ".join(sorted(entries)) or "(none)"
        raise RuntimeError(
            f"{source} names {home!r} as the home project, but no [[project]] "
            f"block declares it. The home project is an ordinary declared "
            f"project that happens to be served at the site root, never a "
            f"slug the roster does not carry. Declared projects: {declared}."
        )
    return Roster(entries, home)


def _missing_roster_error(path: str) -> RuntimeError:
    example = render_roster(
        [RosterEntry("example", "owner/example")], home="example",
    )
    return RuntimeError(
        f"{path} does not exist, so the assembly declares no membership. "
        f"Membership is a declared list the deploy reconciles to, never "
        f"something a deploy accumulates, so there is no empty default. "
        f"Create the file in the assembly repository with one block per "
        f"project the site serves:\n\n{example}"
    )


def load_roster(assembly_dir: str = ".") -> Roster:
    """Return the roster declared in *assembly_dir*, or raise if absent."""
    path = os.path.join(assembly_dir, ROSTER_PATH)
    if not os.path.isfile(path):
        raise _missing_roster_error(path)
    with open(path, "r", encoding="utf-8") as f:
        return parse_roster(f.read(), source=path)


def fetch_pypi_metadata(package: str) -> dict:
    """Return PyPI's JSON metadata document for *package*.

    This is the one function that touches the network, so a test replaces
    it wholesale (or passes its own ``fetch`` into the callers below).  It
    is a GET: it changes nothing, which is why it does not go through the
    effects handle -- a recorded read would have nothing to record and a
    preview still needs the answer.
    """
    import urllib.error
    import urllib.request

    url = PYPI_JSON_URL.format(package=package)
    try:
        with urllib.request.urlopen(url, timeout=_REGISTRY_TIMEOUT) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise RuntimeError(
                f"{package} is not a package on PyPI ({url} returned 404)"
            ) from exc
        raise RuntimeError(f"could not read {url}: HTTP {exc.code}") from exc
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise RuntimeError(f"could not read {url}: {exc}") from exc


def registry_latest_version(package: str, *, fetch=None) -> str:
    """Return the version PyPI currently serves as *package*'s latest."""
    fetch = fetch if fetch is not None else fetch_pypi_metadata
    data = fetch(package)
    version = str((data.get("info") or {}).get("version") or "")
    if not version:
        raise RuntimeError(
            f"PyPI's metadata for {package} names no current version "
            f"({PYPI_JSON_URL.format(package=package)})"
        )
    return version


def check_pins_are_published(pins: ToolchainPins, *, fetch=None) -> None:
    """Raise unless every pinned version can actually be installed from PyPI.

    ``assembly sync-workflow`` defaults the selfblog pin to the *running*
    selfblog, which in a development checkout is an editable install that
    sits ahead of the registry the moment work starts on the next version.
    Writing that pin produces a workflow whose ``pip install selfblog==X``
    cannot resolve, and the failure surfaces at the next dispatch, on the
    assembly repository, far from whoever wrote it.  So the pins are
    checked here, before anything is written.

    A version that exists but has no files is unpublished for this
    purpose: pip cannot install it either.
    """
    fetch = fetch if fetch is not None else fetch_pypi_metadata
    for package, version in pins.as_registry_map().items():
        url = PYPI_JSON_URL.format(package=package)
        data = fetch(package)
        releases = data.get("releases")
        if not isinstance(releases, dict):
            raise RuntimeError(f"PyPI's metadata for {package} lists no releases ({url})")
        if not releases.get(version):
            raise RuntimeError(
                f"{package} {version} is not published on PyPI ({url}). The "
                f"generated workflow would run 'pip install "
                f"{package}=={version}', which cannot resolve, and the deploy "
                f"would fail on the assembly repository at the next dispatch. "
                f"Release {package} {version} first, or name a published "
                f"version explicitly."
            )


def resolve_toolchain_pins(
    *,
    selfblog_version: str = "",
    selfdoc_version: str = "",
    pagefind_version: str = "",
    fetch=None,
) -> ToolchainPins:
    """Resolve the three pins the generated workflow installs.

    An explicitly supplied version is taken verbatim.  Otherwise:

    * **selfblog** is the running selfblog.  That is the release path's
      whole point: the deployed workflow names the selfblog that generated
      it.
    * **selfdoc** is the selfdoc installed in this environment.  Absent is
      a hard error, not an unpinned install.
    * **pagefind** is PyPI's current release.  pagefind is a CI-only tool
      that neither selfblog nor this workspace depends on, so there is no
      installed distribution to read a version from -- the honest options
      are the registry's current release or an explicitly named version,
      and the registry answer is the one that keeps regenerating on every
      release the way the other two do.  This is the one pin that does not
      describe the machine doing the generating; that difference is
      deliberate and there is nowhere better to read it from.
    """
    if not selfblog_version:
        from selfblog import __version__ as selfblog_version

    if not selfdoc_version:
        from importlib.metadata import PackageNotFoundError
        from importlib.metadata import version as dist_version

        try:
            selfdoc_version = dist_version("selfdoc")
        except PackageNotFoundError as exc:
            raise RuntimeError(
                "selfdoc is not installed here, so the deploy workflow's "
                "selfdoc pin cannot be read from this environment. Install "
                "selfdoc, or name the pin explicitly -- the workflow does not "
                "install selfdoc unpinned."
            ) from exc

    if not pagefind_version:
        pagefind_version = registry_latest_version("pagefind", fetch=fetch)

    return ToolchainPins(
        selfblog=selfblog_version,
        selfdoc=selfdoc_version,
        pagefind=pagefind_version,
    )


def generate_workflow_yaml(
    pages_project: str,
    canonical_base: str,
    legacy_blog_host: str,
    pins: ToolchainPins,
) -> str:
    """Return a GitHub Actions workflow YAML for assembly deployment.

    Every deploy-target value is templated from the project's
    ``selfdoc.json`` -- nothing about the destination is baked into
    selfblog itself.

    The workflow is deliberately thin: checkout, install the pinned
    toolchain, invoke ``selfblog assembly integrate``, deploy.  Every
    decision the deploy makes (version detection, subtree replacement,
    artifact filtering, membership bookkeeping, the push retry loop and
    search indexing) lives in that command, where it is importable and
    testable, instead of in embedded shell and inline interpreter
    snippets that only ever ran in CI.

    pages_project: Cloudflare Pages project to deploy the assembled site
        to, from ``assembly.pages_project``.  Required.
    canonical_base: absolute canonical base URL of the assembly site,
        from ``topology.docs_base``.  Required.
    legacy_blog_host: hostname of a retired blog subdomain, from
        ``topology.legacy_blog_host``.  Empty when none exists.
    pins: the :class:`ToolchainPins` the install step names.  Required and
        complete: this function renders pins, it never resolves them, so
        it reads neither the environment nor the network.
        :func:`resolve_toolchain_pins` does the resolving and
        :func:`check_pins_are_published` refuses a pin nobody can install.
    """
    if not pages_project:
        raise ValueError(
            "generate_workflow_yaml requires a Cloudflare Pages project "
            "(assembly.pages_project); there is no default."
        )
    if not canonical_base:
        raise ValueError(
            "generate_workflow_yaml requires a canonical base URL "
            "(topology.docs_base); there is no default."
        )
    if not isinstance(pins, ToolchainPins):
        raise ValueError(
            "generate_workflow_yaml requires a ToolchainPins; the generated "
            "workflow pins every tool it installs."
        )
    canonical_base = canonical_base.rstrip("/")
    return """\
name: Assembly Deploy

on:
  repository_dispatch:
    types: [project-updated]

permissions:
  contents: write

concurrency:
  group: assembly-deploy
  cancel-in-progress: false
  queue: max

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install tools
        run: pip install 'selfdoc==@@SELFDOC_VERSION@@' 'selfblog==@@SELFBLOG_VERSION@@' 'pagefind[bin]==@@PAGEFIND_VERSION@@'

      - name: Clone source project
        if: github.event.client_payload.scope != 'shared-only'
        uses: actions/checkout@v4
        with:
          repository: ${{ github.event.client_payload.repo }}
          ref: ${{ github.event.client_payload.ref }}
          path: source/${{ github.event.client_payload.slug }}
          fetch-depth: 1

      - name: Integrate the project into the assembly
        run: >
          selfblog assembly integrate
          --slug '${{ github.event.client_payload.slug }}'
          --version '${{ github.event.client_payload.version }}'
          --ref '${{ github.event.client_payload.ref }}'
          --source-repo '${{ github.event.client_payload.repo }}'
          --scope '${{ github.event.client_payload.scope }}'
          --canonical-base '@@CANONICAL_BASE@@'
          --legacy-blog-host '@@LEGACY_BLOG_HOST@@'

      - name: Deploy to Cloudflare Pages
        run: npx wrangler pages deploy site/ --project-name '@@PAGES_PROJECT@@'
        env:
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_PAGES_API_TOKEN }}
""".replace(
        "@@PAGES_PROJECT@@", pages_project,
    ).replace(
        "@@CANONICAL_BASE@@", canonical_base,
    ).replace(
        "@@LEGACY_BLOG_HOST@@", legacy_blog_host,
    ).replace(
        "@@SELFBLOG_VERSION@@", pins.selfblog,
    ).replace(
        "@@SELFDOC_VERSION@@", pins.selfdoc,
    ).replace(
        "@@PAGEFIND_VERSION@@", pins.pagefind,
    )


def assembly_init(
    repo_name: str,
    pages_project: str,
    canonical_base: str,
    legacy_blog_host: str,
    pins: ToolchainPins,
) -> dict[str, str]:
    """Return a dict mapping filename to file content for a new assembly repo.

    repo_name: e.g. "smm-h/docs-assembly"
    pages_project: Cloudflare Pages project the workflow deploys to.
    canonical_base: absolute canonical base URL of the assembly site.
    legacy_blog_host: retired blog subdomain, or "" when none exists.
    pins: the toolchain versions the generated workflow installs.
    """
    return {
        WORKFLOW_PATH: generate_workflow_yaml(
            pages_project, canonical_base, legacy_blog_host, pins,
        ),
        ".gitignore": _gitignore_content(),
        ROSTER_PATH: render_roster([]),
        PROJECTS_PATH: json.dumps({}, indent=2) + "\n",
    }


def _gitignore_content() -> str:
    """Return a .gitignore suitable for a CI-only assembly repo."""
    return """\
node_modules/
.wrangler/
dist/
source/
*.log
"""


def assembly_push(
    assembly_repo: str,
    source_repo: str,
    slug: str,
    version: str,
    ref: str,
) -> dict:
    """Return the API endpoint and payload for a repository_dispatch event.

    assembly_repo: the assembly repo (e.g. "smm-h/docs-assembly")
    source_repo: the source project repo (e.g. "smm-h/selfdoc")
    slug: the project slug
    version: the version being deployed
    ref: the git ref (tag or branch) to clone
    """
    return {
        "endpoint": f"/repos/{assembly_repo}/dispatches",
        "payload": {
            "event_type": "project-updated",
            "client_payload": {
                "slug": slug,
                "version": version,
                "ref": ref,
                "repo": source_repo,
            },
        },
    }


def assembly_status(repo: str) -> list[list[str]]:
    """Return a list of gh CLI argument lists to query recent workflow runs.

    repo: the assembly repo identifier (e.g. "smm-h/docs-assembly")
    """
    return [
        [
            "gh",
            "api",
            f"/repos/{repo}/actions/runs",
            "--jq",
            ".workflow_runs[:5] | .[] | {status, conclusion, created_at, html_url}",
        ],
    ]


#: Every field an ``assembly integrate`` run records for a project in
#: ``projects.json``.  A rebuild replays that record, so all three have to
#: be there -- see :func:`assembly_rebuild`.
MEMBERSHIP_FIELDS = ("repo", "ref", "version")


def assembly_rebuild(
    repo: str,
    projects: dict[str, dict],
) -> list[dict]:
    """Return dispatch payloads for rebuilding all projects.

    repo: the assembly repo identifier
    projects: mapping of slug to the membership record ``assembly
        integrate`` wrote, which always carries ``repo``, ``ref`` and
        ``version``.

    An incomplete record is a hard error naming the project and the fields
    it lacks.  A missing version used to become the literal string
    ``"latest"``, which travelled through the dispatch payload and back
    into ``projects.json`` -- so the assembly's own membership record then
    claimed a version nobody released, and every later rebuild replayed
    it.
    """
    dispatches = []
    for slug, info in projects.items():
        record = info if isinstance(info, dict) else {}
        missing = [field for field in MEMBERSHIP_FIELDS if not record.get(field)]
        if missing:
            raise RuntimeError(
                f"the assembly's membership record for {slug!r} is missing "
                f"{', '.join(missing)}. 'assembly integrate' writes all of "
                f"{', '.join(MEMBERSHIP_FIELDS)} for every project, so this "
                f"entry was hand-edited or written by an older deploy. Fix "
                f"projects.json, or dispatch {slug!r} from its own repository "
                f"with 'selfblog assembly push' -- there is no default for a "
                f"version, and inventing one records docs under a version "
                f"nobody released."
            )
        dispatches.append(
            assembly_push(
                assembly_repo=repo,
                source_repo=record["repo"],
                slug=slug,
                version=record["version"],
                ref=record["ref"],
            )
        )
    return dispatches


def generate_redirects_file(slug: str, docs_base: str) -> str:
    """Return the content of a Cloudflare Pages _redirects file.

    Redirects all paths from the old per-project CF Pages site to the
    assembly site under the project's slug prefix.

    slug: project's URL path segment (e.g. "selfdoc")
    docs_base: base URL of the assembly site (e.g. "https://docs.smmh.dev")
    """
    docs_base = docs_base.rstrip("/")
    return f"/* {docs_base}/{slug}/:splat 301\n"


def generate_worker_js(
    canonical_base: str,
    legacy_blog_host: str,
    *,
    project_slugs=(),
    post_slugs=(),
) -> str:
    """Return the Cloudflare Pages ``_worker.js`` for the assembly site.

    The worker does two things, and every request answers to at most one
    301 before it reaches an asset.

    **One hostname.**  The site is bound to more than one host -- the
    canonical apex, the docs subdomain, the retired blog subdomain, the
    provider's own preview domain -- and exactly one of them serves
    content.  A request on any other host is redirected to the same path on
    the canonical host, 301, query string preserved.  No path is ever
    served on two hosts, so nothing is duplicate content and no
    ``rel=canonical`` is asked to undo a hosting decision.

    The one host that does not map to the same path is the retired blog
    subdomain, whose whole document space was the blog: ``blog.example.com/x``
    is ``<canonical>/blog/x``, not ``<canonical>/x``.  Mapping it to the
    same path would send every live post link to the site root, where
    nothing answers.

    **Historical addresses.**  The site has changed address scheme twice,
    and the shapes below are the ones with links in the wild.  Each is a
    301 to the current address, generated as *data* from the manifests --
    the assembly knows every project slug and every post slug, and a path
    that merely looks historical without naming one of them is not
    redirected at all: it falls through to the 404, which is the honest
    answer for an address that never existed.

    * ``/<slug>/<locale>/<version>/<rest>`` -> ``/<slug>/<rest>``.  The
      version segment is not preserved: **any** version collapses to the
      stable address.  Genuinely archived versions are still served from
      ``/<slug>/v/<version>/``, but an old deep link is far more likely to
      want the page as it is now than the page as it was at the version
      that happened to be current when somebody copied the URL.
    * ``/<slug>/posts/<post>/`` -> ``/blog/<post>/``.  Posts moved out of
      the project subtrees into one site-level namespace.

    The third historical shape, the flat ``/<slug>/<page>/`` sitemap
    address, needs no rule: it is what the current scheme serves, and the
    meta-refresh stubs that briefly stood at ``/<slug>/`` have been
    replaced by the real pages at the same address.

    Args:
        canonical_base: absolute base URL of the assembly site, taken from
            ``topology.docs_base``.  Required -- there is no default
            deploy target.
        legacy_blog_host: hostname of the retired blog subdomain, taken
            from ``topology.legacy_blog_host``.  An empty string means no
            such subdomain exists and it gets no prefix entry; it would
            still be redirected by the one-hostname rule if it resolved
            here.
        project_slugs: every project the assembly serves.  A historical
            path is only rewritten when its first segment is one of these.
        post_slugs: every post the blog serves, same role.
    """
    if not canonical_base:
        raise ValueError(
            "generate_worker_js requires a canonical base URL "
            "(topology.docs_base); there is no default."
        )
    canonical_base = canonical_base.rstrip("/")

    host_prefixes = {legacy_blog_host: f"/{POSTS_SEGMENT}"} if legacy_blog_host else {}

    return (
        "// Generated by selfblog. Do not edit: regenerated on every deploy.\n"
        f"const CANONICAL_BASE = {json.dumps(canonical_base)};\n"
        "const CANONICAL_HOST = new URL(CANONICAL_BASE).hostname;\n"
        "\n"
        "// Non-canonical hosts whose paths land under a prefix on the\n"
        "// canonical host. Every other non-canonical host maps to the same\n"
        "// path, so it needs no entry here. A Map, not an object: a hostname\n"
        "// is attacker-chosen input, and an object lookup would answer\n"
        "// 'constructor' and '__proto__' with something from the prototype.\n"
        "const HOST_PREFIXES = new Map("
        f"{json.dumps(sorted(host_prefixes.items()))});\n"
        "\n"
        "// The address space, as data. A historical-looking path that names\n"
        "// neither a real project nor a real post is not redirected.\n"
        f"const PROJECT_SLUGS = new Set({json.dumps(sorted(set(project_slugs)))});\n"
        f"const POST_SLUGS = new Set({json.dumps(sorted(set(post_slugs)))});\n"
        "\n"
        "// /<slug>/<locale>/<version>/<rest> -- the retired locale+version scheme.\n"
        "const LOCALE_VERSION = "
        "/^\\/([^/]+)\\/([a-z]{2}(?:-[a-z]{2})?)\\/([^/]+)(?:\\/(.*))?$/i;\n"
        "// What counts as a version segment: 1, 1.2, v1.2.3, 1.2.3-rc.1.\n"
        "const VERSION = /^v?\\d+(?:\\.\\d+)*(?:[-+][0-9A-Za-z.-]+)?$/;\n"
        "// /<slug>/posts/<post>/ -- posts before they became site-level.\n"
        "const PROJECT_POST = /^\\/([^/]+)\\/posts\\/([^/]+)\\/?$/;\n"
        "\n"
        "// The path a historical address maps to, or null when it is not one.\n"
        "export function legacyTarget(pathname) {\n"
        "  const post = pathname.match(PROJECT_POST);\n"
        "  if (post && PROJECT_SLUGS.has(post[1]) && POST_SLUGS.has(post[2])) {\n"
        f"    return \"/{POSTS_SEGMENT}/\" + post[2] + \"/\";\n"
        "  }\n"
        "  const versioned = pathname.match(LOCALE_VERSION);\n"
        "  if (versioned && PROJECT_SLUGS.has(versioned[1]) &&\n"
        "      VERSION.test(versioned[3])) {\n"
        "    return \"/\" + versioned[1] + \"/\" + (versioned[4] || \"\");\n"
        "  }\n"
        "  return null;\n"
        "}\n"
        "\n"
        "// The absolute URL a request is redirected to, or null to serve it.\n"
        "// One hop: a historical path arriving on a non-canonical host is\n"
        "// resolved before the redirect, never in a second one.\n"
        "export function routeRequest(requestUrl) {\n"
        "  const url = new URL(requestUrl);\n"
        "  const offHost = url.hostname !== CANONICAL_HOST;\n"
        "  const prefix = offHost ? (HOST_PREFIXES.get(url.hostname) || \"\") : \"\";\n"
        "  const pathname = prefix + url.pathname;\n"
        "  const legacy = legacyTarget(pathname);\n"
        "  if (legacy !== null) return CANONICAL_BASE + legacy + url.search;\n"
        "  if (offHost) return CANONICAL_BASE + pathname + url.search;\n"
        "  return null;\n"
        "}\n"
        "\n"
        "export default {\n"
        "  async fetch(request, env) {\n"
        "    const target = routeRequest(request.url);\n"
        "    if (target !== null) return Response.redirect(target, 301);\n"
        "    return env.ASSETS.fetch(request);\n"
        "  }\n"
        "}\n"
    )


def merge_post_lists(base_posts: list, overlay_posts: list) -> list:
    """Return the union of a build's post list and the overlay's, by slug.

    The build wins on a slug both carry -- it just re-rendered that post from
    the tag it was released at.  What the overlay contributes is the posts
    the build does not carry at all: the ones published between releases.

    This runs when a full build lands, not when the assembly is read: the
    overlay stays the one authority on a project's posts, and stays a
    complete list, so republishing after deleting a post still removes it
    from the site.
    """
    merged = list(base_posts or [])
    known = {
        str(post.get("slug") or "")
        for post in merged
        if isinstance(post, dict)
    }
    for post in overlay_posts or []:
        if not isinstance(post, dict):
            continue
        slug = str(post.get("slug") or "")
        if slug and slug in known:
            continue
        merged.append(post)
        known.add(slug)
    return merged


def load_assembly_manifests(manifests_dir: str) -> list[dict]:
    """Return the assembly's per-project manifests with post overlays applied.

    ``*-posts.json`` files are overlays written by ``post publish``: they
    carry a complete post list for their slug and replace the base
    manifest's ``posts`` array, which is how deleting a post and
    republishing removes it from the site.  A full build folds its own posts
    into the overlay when it lands (see :func:`merge_post_lists`), so
    replacing here never hides a release's posts behind an older overlay.
    ``*-revisions.json`` and ``*-files.json`` sidecars are not manifests and
    are skipped.
    """
    from selfdoc_core.manifest import manifest_compat

    base_manifests: list[dict] = []
    post_overlays: list[dict] = []
    if os.path.isdir(manifests_dir):
        for fname in sorted(os.listdir(manifests_dir)):
            if not fname.endswith(".json"):
                continue
            if fname.endswith(MANIFEST_SIDECAR_SUFFIXES):
                continue
            fpath = os.path.join(manifests_dir, fname)
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
            manifest_compat(data, source=fpath)
            if fname.endswith("-posts.json"):
                post_overlays.append(data)
            else:
                base_manifests.append(data)

    if post_overlays:
        base_by_slug = {m["slug"]: m for m in base_manifests}
        for overlay in post_overlays:
            slug = overlay.get("slug", "")
            if slug in base_by_slug:
                base_by_slug[slug]["posts"] = overlay.get("posts", [])

    return base_manifests


def listing_sidecar_path(manifests_dir: str, home_slug: str) -> str:
    """Where the assembly keeps the home project's curated listing."""
    from selfblog.listing import LISTING_SIDECAR_SUFFIX

    return os.path.join(manifests_dir, f"{home_slug}{LISTING_SIDECAR_SUFFIX}")


def load_listing_for(manifests_dir: str, home_slug: str):
    """Return the home project's curated listing, or None when it has none.

    The listing is authored in the home project and copied here by its
    deploy, so it is absent until that deploy has happened once.  Absent is
    a real state -- an assembly whose home project has never deployed has no
    listing to render -- and the generated page says so rather than being
    written from some other source.
    """
    from selfblog.listing import load_listing_sidecar

    if not home_slug:
        return None
    path = listing_sidecar_path(manifests_dir, home_slug)
    return load_listing_sidecar(path) if os.path.isfile(path) else None


def home_page_paths(manifests_dir: str, home_slug: str) -> list[str]:
    """Return every site-relative HTML page the home project published.

    Read from the published-file record rather than guessed from the tree:
    the home project's pages sit at the site root beside other projects'
    directories and the generated artifacts, so "which files are the home
    project's" is a question only its own record answers.
    """
    if not home_slug:
        return []
    record = load_files_manifest(files_manifest_path(manifests_dir, home_slug))
    return sorted({
        path
        for paths in record.values()
        for path in paths
        if path.endswith(".html") and path.split("/")[0] != POSTS_SEGMENT
    })


def home_owned_root_names(manifests_dir: str, home_slug: str) -> set[str]:
    """Return the top-level names under ``site/`` the home project published.

    The home project's pages are at the site root, so its directories sit
    beside the other projects' subtrees.  Membership reconciliation and the
    roster check both walk those directories looking for projects, and
    without this they would read the home project's ``cv/`` as an
    undeclared project and delete it.
    """
    if not home_slug:
        return set()
    record = load_files_manifest(files_manifest_path(manifests_dir, home_slug))
    return {
        path.split("/")[0]
        for paths in record.values()
        for path in paths
        if "/" in path and path.split("/")[0] != POSTS_SEGMENT
    }


def refresh_home_pages(site_dir: str, manifests_dir: str, manifests,
                       docs_base: str, *, home_slug: str, listing) -> list[str]:
    """Re-render every site-level directive region the home project emitted.

    This is the second of the two moments a site-level directive resolves
    (the first is the home project's own build).  It runs on every deploy,
    including deploys of other projects, which is the point: the front
    page's curated cards carry each project's live version, and a version
    changes when *that* project releases, not when the home project does.
    """
    from selfblog.sitedirectives import SiteContext, refresh_regions
    from selfdoc_core.utils import atomic_write

    written: list[str] = []
    if not home_slug:
        return written
    context = SiteContext(
        manifests=manifests, docs_base=docs_base, listing=listing,
        home_slug=home_slug,
    )
    for rel in home_page_paths(manifests_dir, home_slug):
        path = os.path.join(site_dir, *rel.split("/"))
        if not os.path.isfile(path):
            continue
        with open(path, "r", encoding="utf-8") as f:
            page_html = f.read()
        refreshed = refresh_regions(page_html, context, source=f"site/{rel}")
        if refreshed != page_html:
            atomic_write(path, refreshed)
        written.append(path)
    return written


def generate_shared_files(
    site_dir: str,
    manifests_dir: str,
    canonical_base: str,
    *,
    docs_base: str = "",
    legacy_blog_host: str = "",
    home_slug: str = "",
) -> list[str]:
    """Write the assembly's shared cross-project files and return their paths.

    The files are the project listing at ``projects/index.html``, the blog
    index at ``blog/index.html``, ``nav.json``, ``feed.xml``,
    ``sitemap.xml``, ``robots.txt``, ``llms.txt``, ``404.html``,
    ``_headers`` and ``_worker.js``.  Both generated pages sit at fixed,
    generator-owned addresses; the site root belongs to the home project,
    whose own pages are grafted there and are never written by this
    function.

    ``robots.txt``, ``llms.txt`` and ``404.html`` are the site's, not any
    project's: every constituent build writes its own set at its own output
    root, where they end up buried under ``<slug>/`` and serve nobody.  The
    per-project ``llms.txt`` files are the exception that stays useful --
    the site-wide one links to each of them rather than restating them.

    *home_slug* is the roster's home project.  It is left out of the
    generated listing and out of nav -- the front page does not list itself
    -- and its pages are addressed from the site root.  Every site-level
    directive region in its emitted pages is re-rendered here, on every
    deploy, so a version badge on the front page is as current as the last
    deploy of the project it names rather than as the last deploy of the
    home project.

    Raises ValueError when a required input is missing -- the CLI turns
    those into a usage error, the integrate command lets them abort the
    deploy.
    """
    from selfblog.shared import (
        generate_blog_index,
        generate_homepage,
        generate_llms_txt,
        generate_nav_json,
        generate_not_found_page,
        generate_robots_txt,
        generate_sitemap,
        generate_unified_feed,
        merge_project_posts,
        wrap_shared_page,
    )
    from selfdoc_core.utils import atomic_write

    if not site_dir:
        raise ValueError("site_dir is required")
    if not manifests_dir:
        raise ValueError("manifests_dir is required")
    if not canonical_base:
        raise ValueError(
            "canonical_base is required (set topology.docs_base in "
            "selfdoc.json and regenerate the assembly workflow)."
        )
    canonical_base = canonical_base.rstrip("/")
    docs_base = docs_base.rstrip("/")

    manifests = load_assembly_manifests(manifests_dir)
    listing = load_listing_for(manifests_dir, home_slug)

    homepage_fragment = generate_homepage(
        manifests, docs_base, home_slug=home_slug, listing=listing,
    )
    blog_fragment = generate_blog_index(manifests, docs_base)
    nav_json = generate_nav_json(manifests, home_slug=home_slug)
    feed_xml = generate_unified_feed(manifests, docs_base)
    # The sitemap takes the canonical base, never docs_base: every <loc> is
    # an absolute URL by protocol, and docs_base is allowed to be
    # root-relative for in-page links.
    sitemap_xml = generate_sitemap(manifests, canonical_base, home_slug=home_slug)

    blog_html = wrap_shared_page(
        "Blog", blog_fragment, canonical_url=f"{canonical_base}/blog/",
    )

    headers_content = (
        "/*\n"
        "  X-Frame-Options: DENY\n"
        "  X-Content-Type-Options: nosniff\n"
        "  Referrer-Policy: strict-origin-when-cross-origin\n"
    )

    written: list[str] = []

    effects.makedirs(site_dir, exist_ok=True)
    projects_dir = os.path.join(site_dir, "projects")
    effects.makedirs(projects_dir, exist_ok=True)
    projects_path = os.path.join(projects_dir, "index.html")
    atomic_write(projects_path, wrap_shared_page(
        "Projects", homepage_fragment,
        canonical_url=f"{canonical_base}/projects/",
    ))
    written.append(projects_path)

    written.extend(refresh_home_pages(
        site_dir, manifests_dir, manifests, docs_base,
        home_slug=home_slug, listing=listing,
    ))

    blog_dir = os.path.join(site_dir, "blog")
    effects.makedirs(blog_dir, exist_ok=True)
    blog_path = os.path.join(blog_dir, "index.html")
    atomic_write(blog_path, blog_html)
    written.append(blog_path)

    nav_path = os.path.join(site_dir, "nav.json")
    atomic_write(nav_path, nav_json)
    written.append(nav_path)

    feed_path = os.path.join(site_dir, "feed.xml")
    atomic_write(feed_path, feed_xml)
    written.append(feed_path)

    sitemap_path = os.path.join(site_dir, "sitemap.xml")
    atomic_write(sitemap_path, sitemap_xml)
    written.append(sitemap_path)

    robots_path = os.path.join(site_dir, "robots.txt")
    atomic_write(robots_path, generate_robots_txt(canonical_base))
    written.append(robots_path)

    llms_path = os.path.join(site_dir, "llms.txt")
    atomic_write(llms_path, generate_llms_txt(
        manifests, canonical_base, home_slug=home_slug,
    ))
    written.append(llms_path)

    not_found_path = os.path.join(site_dir, "404.html")
    atomic_write(not_found_path, generate_not_found_page(canonical_base))
    written.append(not_found_path)

    headers_path = os.path.join(site_dir, "_headers")
    atomic_write(headers_path, headers_content)
    written.append(headers_path)

    # The worker's redirect map is data read out of the manifests here, at
    # generation time: which slugs exist and which posts exist is what makes
    # a historical-looking path a real redirect rather than a guess.
    worker_js_path = os.path.join(site_dir, "_worker.js")
    atomic_write(worker_js_path, generate_worker_js(
        canonical_base, legacy_blog_host,
        project_slugs=[
            str(m.get("slug") or "") for m in manifests if m.get("slug")
        ],
        post_slugs=[
            post["slug"] for post in merge_project_posts(manifests)
            if post["slug"]
        ],
    ))
    written.append(worker_js_path)

    return written


# -- integrate: the deploy body the generated workflow used to embed ---------


def build_target_version(config: dict, source: str = "") -> str:
    """Return the version a ``selfdoc build`` of *config* would produce.

    This is the one definition of "the version being built", and both the
    build (:func:`detect_latest_version`) and the dispatch check
    (:func:`check_version_is_declared`) read it, so they cannot disagree.

    Empty when the project declares no versions at all -- a single
    implicit version, which ``selfdoc build`` handles without
    ``--version``.  A declared ``versions`` array whose newest entry
    carries no version string is a hard error however long the array is:
    the build takes ``versions[-1]``, so a blank newest entry would
    silently publish the docs unversioned, at the wrong address.

    source: what to name in the error message (a directory, usually).
    """
    versions = config.get("versions") or []
    if not versions:
        return ""
    newest = versions[-1]
    latest = str(newest.get("version") or "") if isinstance(newest, dict) else ""
    if not latest:
        where = f" for the project at {source}" if source else ""
        raise RuntimeError(
            f"the newest 'versions' entry in selfdoc.json{where} declares no "
            f"version, so there is nothing to build. The build takes the last "
            f"entry of 'versions'; give it a 'version' string."
        )
    return latest


def detect_latest_version(source_dir: str) -> str:
    """Return the newest version declared by a source project's config.

    A project with no ``selfdoc.json`` at all builds unversioned; see
    :func:`build_target_version` for everything else.
    """
    cfg_path = os.path.join(source_dir, "selfdoc.json")
    if not os.path.isfile(cfg_path):
        return ""
    with open(cfg_path, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    return build_target_version(cfg, source=source_dir)


def prune_deploy_artifacts(root: str) -> list[str]:
    """Delete per-project deploy artifacts under *root*; return their paths.

    A project build emits ``_headers``, ``_redirects``, ``_worker.js`` and
    pre-compressed ``.gz`` / ``.br`` copies for its own standalone
    hosting.  Inside the assembly those files would fight the site-wide
    ones the shared generator writes.
    """
    removed = []
    for dirpath, _dirnames, filenames in os.walk(root):
        for name in sorted(filenames):
            if name in DEPLOY_ARTIFACT_NAMES or name.endswith(DEPLOY_ARTIFACT_SUFFIXES):
                path = os.path.join(dirpath, name)
                effects.remove(path)
                removed.append(path)
    return sorted(removed)


def is_deploy_artifact(name: str) -> bool:
    """Return whether a file *name* is a per-project deploy artifact."""
    return name in DEPLOY_ARTIFACT_NAMES or name.endswith(DEPLOY_ARTIFACT_SUFFIXES)


def build_output_paths(root: str, *, skip_artifacts: bool = True) -> set[str]:
    """Return every file under *root* as a ``/``-joined relative path.

    This is the "what the build produces" set the prune is driven by, so it
    excludes the per-project deploy artifacts by default: those are filtered
    out on the way in and must not be recorded as though the assembly served
    them.
    """
    found: set[str] = set()
    if not os.path.isdir(root):
        return found
    for dirpath, _dirnames, filenames in os.walk(root):
        for name in filenames:
            if skip_artifacts and is_deploy_artifact(name):
                continue
            rel = os.path.relpath(os.path.join(dirpath, name), root)
            found.add(rel.replace(os.sep, "/"))
    return found


def prune_empty_dirs(root: str) -> list[str]:
    """Remove empty directories under *root*; return the ones removed.

    *root* itself always survives, even when the subtree ends up empty: the
    project still has a section, it just has no files in it.
    """
    removed = []
    if not os.path.isdir(root):
        return removed
    for dirpath, _dirnames, _filenames in sorted(os.walk(root, topdown=False)):
        if dirpath == root:
            continue
        if not os.listdir(dirpath):
            effects.rmdir(dirpath)
            removed.append(dirpath)
    return removed


def files_manifest_path(manifests_dir: str, slug: str) -> str:
    """Return the path of *slug*'s published-file record."""
    return os.path.join(manifests_dir, f"{slug}-files.json")


def parse_files_manifest(raw: str, *, source: str) -> dict[str, list[str]]:
    """Return owner -> published paths from the record text *raw*.

    Empty text is an empty mapping: nothing has published anything yet, so
    there is nothing anybody is entitled to remove.  Everything else is
    strict, because a record read wrong hands paths to the wrong publisher:
    malformed JSON, an unknown publisher and a path list that is not a list
    of strings are each a hard error, and so is a record written in the
    version-1 format, whose paths meant something else.
    """
    if not raw.strip():
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{source} is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise RuntimeError(f"{source} must contain a JSON object")
    version = data.get("schema_version")
    if version != FILES_RECORD_VERSION:
        raise RuntimeError(
            f"{source} is a version {version!r} published-file record; this "
            f"selfblog writes and reads version {FILES_RECORD_VERSION}. "
            f"Version 1 addressed every path from the project's own subtree "
            f"and put posts at '<slug>/posts/...'; version 2 addresses every "
            f"path from site/ and posts are site-level, at "
            f"'blog/<post-slug>/...'. The two cannot be told apart by "
            f"reading them, so this one is refused rather than "
            f"reinterpreted. Either rewrite it -- prefix every documentation "
            f"path with '<slug>/' and re-address every post as "
            f"'blog/<post-slug>/...' -- or delete it together with the stale "
            f"site/<slug>/posts/ tree it describes, in which case the next "
            f"publish records what it produces and until then no publisher "
            f"is entitled to remove anything."
        )
    owners = data.get("owners") or {}
    if not isinstance(owners, dict):
        raise RuntimeError(f"{source}: 'owners' must be a JSON object")
    unknown = sorted(set(owners) - set(PUBLISH_OWNERS))
    if unknown:
        raise RuntimeError(
            f"{source} records paths under unknown publisher(s) "
            f"{', '.join(repr(o) for o in unknown)}; known publishers are "
            f"{', '.join(PUBLISH_OWNERS)}."
        )
    result = {}
    for owner, paths in owners.items():
        if not isinstance(paths, list) or any(not isinstance(p, str) for p in paths):
            raise RuntimeError(
                f"{source}: the paths recorded for {owner!r} must be a list "
                f"of strings."
            )
        result[owner] = sorted(paths)
    return result


def load_files_manifest(path: str) -> dict[str, list[str]]:
    """Return owner -> published paths from the record at *path*.

    An absent record is an empty mapping, which is not a fallback but the
    real initial state: nothing has published anything for this project yet.
    """
    if not os.path.isfile(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return parse_files_manifest(f.read(), source=path)


def render_files_manifest(slug: str, owners: dict[str, list[str]]) -> str:
    """Return the JSON text of *slug*'s published-file record.

    Every path is relative to ``site/``: the project's own pages are under
    ``<slug>/`` and its posts are at ``blog/<post-slug>/``, in one namespace
    so a claim can be compared against any other project's.
    """
    return json.dumps(
        {
            "schema_version": FILES_RECORD_VERSION,
            "slug": slug,
            "owners": {
                owner: sorted(owners.get(owner, []))
                for owner in PUBLISH_OWNERS
                if owners.get(owner)
            },
        },
        indent=2,
        sort_keys=True,
    ) + "\n"


def stage_published_record(
    repo: str,
    slug: str,
    owner: str,
    produced,
    files: dict,
) -> list[str]:
    """Record what *owner* now publishes for *slug*; return what it deletes.

    The one path by which a publisher that writes through the Git Data API
    -- ``docs publish`` and ``post publish`` -- keeps the published-file
    record honest.  It reads the record on *repo*, prunes *owner*'s entry
    against *produced* (site-relative paths), and stages the rewritten
    record in *files* alongside whatever else that publisher is pushing, so
    the record and the content it describes land in the same commit.

    Without this, a publish leaves its files unclaimed: nothing accounts
    for them, the ownership-prune model cannot protect them from another
    publisher, retirement does not take them along, and the cross-project
    write refusal (:func:`foreign_post_claims`) cannot see them at all.

    Returns the repo-relative paths to delete in that same commit.
    """
    record_path = f"manifests/{slug}-files.json"
    # Absence is the real first-publish state and nothing else is: a failed
    # read here would prune this owner's entry against a record it never saw
    # and drop every other owner's claims from the file it rewrites.
    raw_record = fetch_remote_text(
        repo, record_path, missing_ok=True,
        operation=f"record what {owner!r} publishes for {slug!r} on {repo}",
    )
    owners = parse_files_manifest(raw_record, source=f"{repo}:{record_path}")
    removed, owners = prune_plan(owners, owner, set(produced))
    files[record_path] = render_files_manifest(slug, owners)
    return [f"site/{rel}" for rel in removed]


def prune_plan(
    owners: dict[str, list[str]],
    owner: str,
    produced,
) -> tuple[list[str], dict[str, list[str]]]:
    """Return the paths *owner* must remove, and the updated owners map.

    This is the whole of "prune instead of wipe".  A publisher removes a
    path only when it published that path before and does not publish it
    now -- so a page a build dropped disappears, while content the build
    never produced is untouched, because nothing entitles this publisher to
    it.  A path another publisher currently claims is never removed either:
    a documentation page or a post published between releases outlives a
    full build that happens not to carry it.
    """
    if owner not in PUBLISH_OWNERS:
        raise ValueError(
            f"unknown publisher {owner!r}; expected one of "
            f"{', '.join(PUBLISH_OWNERS)}"
        )
    produced = set(produced)
    previous = set(owners.get(owner, ()))
    claimed_elsewhere: set[str] = set()
    for other, paths in owners.items():
        if other != owner:
            claimed_elsewhere |= set(paths)
    removed = sorted((previous - produced) - claimed_elsewhere)
    updated = {o: sorted(p) for o, p in owners.items()}
    updated[owner] = sorted(produced)
    return removed, updated


#: Directory names at the site root the generator owns.  A home project page
#: emitting into one of them would be overwritten by, or would overwrite, the
#: assembly's own listing, blog or archive space.
HOME_RESERVED_DIRS = ("blog", "projects", "v", "pagefind")

#: Files at the site root the assembly generates for the whole site on every
#: deploy.  A project's own build writes its own copy of each at its own
#: output root, for its own standalone hosting; for a project under
#: ``site/<slug>/`` those copies are buried and harmless, and for the home
#: project they would land exactly on top of the site-wide ones.  They are
#: dropped from the home graft, the same treatment
#: :func:`prune_deploy_artifacts` gives every other project's routing files.
#: ``index.html`` is deliberately absent: the home project's front page is
#: exactly what belongs at the site root.
HOME_DROPPED_ARTIFACTS = (
    # The curated listing's source document, which the build copies through
    # as a static asset. The site serves the two renderings of it, not it.
    "projects.toml",
    "sitemap.xml",
    "sitemap-index.xml",
    "robots.txt",
    "404.html",
    "feed.xml",
    "llms.txt",
    "llms-full.txt",
    "nav.json",
    *DEPLOY_ARTIFACT_NAMES,
)


def home_collisions(site_rels) -> list[tuple[str, str]]:
    """Return ``(path, what it collides with)`` for every reserved address.

    The home project emits at the site root, where the assembly's own
    generated pages live.  A page called ``projects.md`` builds to
    ``projects/index.html``, which is the generated project listing's
    address; one of the two would silently win.  Neither does: the collision
    is refused, at the graft and again at verification.

    Only the reserved directories can be refused this way, and they are the
    whole rule: a name in :data:`HOME_DROPPED_ARTIFACTS` never reaches a
    graft to be checked, because every selfdoc build writes those for its
    own standalone hosting and the assembly writes the ones the site serves.
    """
    found: list[tuple[str, str]] = []
    for rel in sorted(set(site_rels)):
        head = rel.split("/")[0]
        if head in HOME_RESERVED_DIRS:
            found.append((
                rel,
                f"{head}/ is the assembly's own directory "
                f"({', '.join(HOME_RESERVED_DIRS)} are reserved)",
            ))
    return found


def check_home_collisions(site_rels, *, slug: str) -> None:
    """Raise when the home project claims an address the assembly owns."""
    found = home_collisions(site_rels)
    if not found:
        return
    detail = "; ".join(f"site/{path} -- {why}" for path, why in found)
    raise RuntimeError(
        f"the home project {slug!r} emits {len(found)} file(s) at addresses "
        f"the assembly owns: {detail}. The home project's content root is "
        f"the site root, so it shares that namespace with the generated "
        f"listing, blog, archives and site-wide artifacts. Rename the page."
    )


def split_build_output(build_rels, slug: str, *, home: bool = False) -> dict[str, str]:
    """Map each file a build produced to where the assembly serves it.

    A project's build output lands in two places, and this is the rule that
    decides which:

    * ``blog/<post-slug>/...`` -- two or more segments under ``blog/`` -- is
      one of the project's **posts**.  Posts are site-level: the file keeps
      its address exactly, at ``site/blog/<post-slug>/...``, under no
      project slug.
    * A file **directly** under ``blog/`` -- in practice ``blog/index.html``,
      the listing page the build renders so the project's own standalone
      site has a blog page -- is not grafted at all.  The assembled site's
      blog index lists every project's posts and is written by
      :func:`generate_shared_files`; a single project's copy would claim the
      same address and serve one project's posts as the whole site's.
    * Everything else is the project's documentation, and lands under its
      own subtree at ``site/<slug>/...``.

    *home* is the one project the roster names ``home``.  Its documentation
    is not filed under a slug at all: the site root **is** its content root,
    so ``index.html`` lands at ``site/index.html`` and ``cv/index.html`` at
    ``site/cv/index.html``, beside the generated ``blog/`` and ``projects/``.
    Its posts follow the same site-level rule as everybody else's, and the
    site-wide artifacts its own build wrote for standalone hosting
    (:data:`HOME_DROPPED_ARTIFACTS`, plus every compressed variant) are left
    behind -- the assembly writes the ones the site serves.

    Returns build-relative path -> site-relative path, with the skipped
    standalone blog index simply absent.
    """
    mapping: dict[str, str] = {}
    for rel in build_rels:
        segments = rel.split("/")
        if segments[0] == POSTS_SEGMENT:
            if len(segments) < 3:
                continue
            mapping[rel] = rel
        elif home:
            if rel in HOME_DROPPED_ARTIFACTS:
                continue
            if rel.endswith(DEPLOY_ARTIFACT_SUFFIXES):
                continue
            mapping[rel] = rel
        else:
            mapping[rel] = f"{slug}/{rel}"
    return mapping


def graft_subtree(
    dest: str,
    src: str,
    produced: dict[str, str],
    removed,
) -> None:
    """Copy *produced* out of *src* into *dest* and delete *removed* from it.

    *produced* maps a source-relative path to the destination-relative path
    it lands at, because a build's output no longer lands in one place: its
    posts go to the site-level blog and everything else to the project's own
    subtree.  *removed* is destination-relative, in the same addressing the
    published-file record uses.
    """
    effects.makedirs(dest, exist_ok=True)
    for src_rel, dest_rel in sorted(produced.items()):
        target = os.path.join(dest, *dest_rel.split("/"))
        effects.makedirs(os.path.dirname(target) or dest, exist_ok=True)
        effects.copy_file(os.path.join(src, *src_rel.split("/")), target)
    for rel in sorted(removed):
        target = os.path.join(dest, *rel.split("/"))
        if os.path.isfile(target):
            effects.remove(target)


def claimed_site_paths(manifests_dir: str, slug: str) -> list[str]:
    """Return the paths *slug* published outside its own subtree.

    Its documentation goes with ``site/<slug>/`` when that directory is
    removed; its posts do not, because they are site-level.  Retirement and
    reconciliation read this to take them with it, so a project that leaves
    the assembly does not leave its posts behind on the blog.
    """
    record = load_files_manifest(files_manifest_path(manifests_dir, slug))
    prefix = f"{slug}/"
    return sorted({
        path
        for paths in record.values()
        for path in paths
        if not path.startswith(prefix)
    })


def foreign_post_claims(manifests_dir: str, slug: str) -> dict[str, str]:
    """Map every site-level post path other projects claim to its claimant.

    The merge refuses two projects publishing the same post slug, but that
    refusal reads manifests; this one reads the published-file records, so
    the write itself can be refused too.  Both are needed: a graft happens
    before the manifests are merged, and it is the graft that would
    overwrite the other project's file.
    """
    claims: dict[str, str] = {}
    if not os.path.isdir(manifests_dir):
        return claims
    for name in sorted(os.listdir(manifests_dir)):
        if not name.endswith("-files.json"):
            continue
        other = name[: -len("-files.json")]
        if other == slug:
            continue
        record = load_files_manifest(os.path.join(manifests_dir, name))
        for paths in record.values():
            for path in paths:
                if path.split("/")[0] == POSTS_SEGMENT:
                    claims.setdefault(path, other)
    return claims


def refuse_foreign_post_overwrite(slug: str, produced, claims: dict[str, str]) -> None:
    """Raise if any of *produced* is a post path *claims* gives to someone else.

    One refusal for every publisher: the integrate graft, which reads the
    records out of the assembly clone, and the two Git Data API publishers,
    which read them off the remote.  Sharing the wording is the point --
    three copies of a refusal are three chances for one of them to be
    quietly weaker than the others.

    *produced* is site-relative, in the same addressing the published-file
    record uses, and *claims* maps such a path to the project that claims it.
    """
    stolen = sorted(
        (dest_rel, claims[dest_rel])
        for dest_rel in set(produced)
        if dest_rel in claims
    )
    if not stolen:
        return
    detail = "; ".join(
        f"site/{path} is claimed by {other!r}" for path, other in stolen
    )
    raise RuntimeError(
        f"{slug!r} would overwrite {len(stolen)} post file(s) another "
        f"project published: {detail}. Posts are emitted at "
        f"'{POSTS_SEGMENT}/<post-slug>/' with no project segment, so a "
        f"post slug is unique across the whole site. Rename the post's "
        f"slug in the project that claims it later."
    )


def remote_post_claims(repo: str, slug: str, others) -> dict[str, str]:
    """Map every site-level post path another project claims to its claimant.

    The remote counterpart of :func:`foreign_post_claims`.  A publisher that
    writes through the Git Data API has no assembly clone to read, so it asks
    the assembly for one published-file record per declared project other
    than its own.  That is one API read per project, which is the price of
    the site-level blog being a single namespace: without it the publish
    would find out about the collision only after it had already overwritten
    the other project's post.

    A project with no record yet claims nothing.  A record that cannot be
    read is a :class:`RemoteReadError`, never an empty claim set.
    """
    claims: dict[str, str] = {}
    for other in sorted(set(others)):
        if other == slug:
            continue
        record_path = f"manifests/{other}-files.json"
        raw = fetch_remote_text(
            repo, record_path, missing_ok=True,
            operation=(
                f"check {slug!r}'s post paths against {other!r}'s claims "
                f"on {repo}"
            ),
        )
        if not raw.strip():
            continue
        record = parse_files_manifest(raw, source=f"{repo}:{record_path}")
        for paths in record.values():
            for path in paths:
                if path.split("/")[0] == POSTS_SEGMENT:
                    claims.setdefault(path, other)
    return claims


def load_projects_json(path: str) -> dict:
    """Return the derived membership record at *path*.

    A malformed file is a hard error rather than a fresh empty mapping:
    rewriting it would silently drop every other project's record.
    """
    data: dict = {}
    if os.path.isfile(path):
        with open(path, "r", encoding="utf-8") as f:
            raw = f.read()
        if raw.strip():
            try:
                data = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise RuntimeError(f"{path} is not valid JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise RuntimeError(f"{path} must contain a JSON object")
    return data


def render_projects_json(data: dict) -> str:
    """Return the JSON text of a derived membership record."""
    return json.dumps(data, indent=2, sort_keys=True) + "\n"


def record_membership(path: str, roster: dict[str, RosterEntry], slug: str,
                      repo: str, ref: str, version: str) -> dict:
    """Record what *slug* just deployed and return the new mapping.

    ``projects.json`` is derived state now: it records what each declared
    project last deployed, and a deploy can only write a record for a slug
    the roster declares.  Membership therefore cannot grow as a side effect
    of a dispatch -- an undeclared slug is refused, naming the file that
    would have to declare it.
    """
    entry = roster.get(slug)
    if entry is None:
        declared = ", ".join(sorted(roster)) or "(none)"
        raise RuntimeError(
            f"{slug!r} is not declared in {ROSTER_PATH}, so the assembly will "
            f"not publish it. Membership is declared, never accumulated by a "
            f"deploy. Add a [[project]] block naming slug = {slug!r} and its "
            f"repo. Declared projects: {declared}."
        )
    if repo and entry.repo != repo:
        raise RuntimeError(
            f"{ROSTER_PATH} declares {slug!r} as {entry.repo}, but this "
            f"deploy came from {repo}. One slug has one owning repository; "
            f"fix the declaration or dispatch under the right slug."
        )
    data = load_projects_json(path)
    data[slug] = {"repo": entry.repo, "ref": ref, "version": version}
    effects.write_text(path, render_projects_json(data))
    return data


def manifest_files_for(manifests_dir: str, slug: str) -> list[str]:
    """Return every file under *manifests_dir* that belongs to *slug*.

    "Belongs" is the base manifest plus every kind sidecar -- the posts
    overlay, the revisions sidecar, the published-file record, and anything
    added later, since the rule is the ``<slug>-`` prefix rather than a
    closed list of kinds.
    """
    if not os.path.isdir(manifests_dir):
        return []
    found = []
    for name in sorted(os.listdir(manifests_dir)):
        if not name.endswith(".json"):
            continue
        stem = name[: -len(".json")]
        if stem == slug or stem.startswith(f"{slug}-"):
            found.append(os.path.join(manifests_dir, name))
    return found


def _manifest_owner(stem: str, declared) -> str | None:
    """Return the declared slug a manifest file's *stem* belongs to."""
    if stem in declared:
        return stem
    head, sep, _kind = stem.rpartition("-")
    if sep and head in declared:
        return head
    return None


def reconcile_membership(assembly_dir: str, roster: dict[str, RosterEntry]) -> dict:
    """Remove every trace of a project the roster no longer declares.

    A project drops out of the assembly by leaving the roster, and this is
    what "leaving" costs it: its site subtree, every one of its manifest
    kinds, its derived membership record, and -- because the search index is
    rebuilt from scratch whenever anything went -- its entries in the index.

    Returns a summary naming the retired slugs and every path removed.
    """
    site_dir = os.path.join(assembly_dir, "site")
    manifests_dir = os.path.join(assembly_dir, "manifests")
    projects_json = os.path.join(assembly_dir, PROJECTS_PATH)
    declared = set(roster)

    retired: set[str] = set()
    removed: list[str] = []

    if os.path.isdir(site_dir):
        for name in sorted(os.listdir(site_dir)):
            path = os.path.join(site_dir, name)
            if not os.path.isdir(path):
                continue
            if name in declared or name in SITE_RESERVED_DIRS:
                continue
            retired.add(name)

    membership = load_projects_json(projects_json)
    retired |= {slug for slug in membership if slug not in declared}

    for slug in sorted(retired):
        subtree = os.path.join(site_dir, slug)
        if os.path.isdir(subtree):
            effects.rmtree(subtree)
            removed.append(subtree)
        # A retired project's posts are not in its subtree -- they are
        # site-level, at blog/<post-slug>/ -- so the record is what says
        # which of them were its. Read it before it is deleted below.
        for path in claimed_site_paths(manifests_dir, slug):
            target = os.path.join(site_dir, *path.split("/"))
            if os.path.isfile(target):
                effects.remove(target)
                removed.append(target)
        for path in manifest_files_for(manifests_dir, slug):
            effects.remove(path)
            removed.append(path)
    if retired:
        prune_empty_dirs(os.path.join(site_dir, POSTS_SEGMENT))

    # A manifest whose stem matches no declared project at all is stale even
    # when no subtree or record named it -- a hand-dropped file, or a kind
    # sidecar left by a slug that was renamed.
    if os.path.isdir(manifests_dir):
        for name in sorted(os.listdir(manifests_dir)):
            if not name.endswith(".json"):
                continue
            path = os.path.join(manifests_dir, name)
            if path in removed:
                continue
            if _manifest_owner(name[: -len(".json")], declared) is None:
                effects.remove(path)
                removed.append(path)

    dropped = [slug for slug in membership if slug not in declared]
    if dropped:
        for slug in dropped:
            del membership[slug]
        effects.write_text(projects_json, render_projects_json(membership))

    # pagefind keys its fragments by content hash, so a page that is gone
    # from the tree can still have a fragment on disk. Rebuilding the index
    # from an empty directory is the only way to be sure a retired project
    # stops answering searches.
    index_dir = os.path.join(site_dir, "pagefind")
    if removed and os.path.isdir(index_dir):
        effects.rmtree(index_dir)
        removed.append(index_dir)

    return {"retired": sorted(retired), "removed": removed}


def _settled(result):
    """Return *result*, or None when it is a recorded (previewed) effect."""
    return None if effects.unsettled(result) else result


def _run_step(argv, *, cwd, step, timeout, resource=None, grant=None,
              check=True, capture_output=False):
    """Run *argv* and raise RuntimeError on failure. None means previewed."""
    result = _settled(effects.run(
        argv, cwd=cwd, timeout=timeout, capture_output=capture_output,
        text=capture_output, resource=resource, grant=grant,
    ))
    if result is None:
        return None
    if check and result.returncode != 0:
        detail = (result.stderr or "").strip() if capture_output else ""
        raise RuntimeError(f"{step} failed (exit {result.returncode}){': ' + detail if detail else ''}")
    return result


def build_source_project(source_dir: str, scope: str, *, home: bool = False,
                         manifests_dir: str = "",
                         docs_base: str = "") -> list[str]:
    """Build the cloned source project and return the argv that was run.

    The home project builds through ``selfblog build --target home``, which
    is the one build that can resolve a site-level directive: its front page
    renders the curated listing with every project's live version, and the
    manifests those versions come from are the assembly's, not its own.
    """
    if scope == "posts":
        argv = ["selfblog", "build", "--target", "posts", "--no-auto-commit"]
    elif home:
        argv = [
            "selfblog", "build", "--target", "home",
            "--site-manifests", os.path.abspath(manifests_dir),
            "--docs-base", docs_base,
            "--no-auto-commit",
        ]
    else:
        argv = ["selfdoc", "build", "--no-auto-commit"]
        latest = detect_latest_version(source_dir)
        if latest:
            argv += ["--version", latest]
    _run_step(
        argv, cwd=source_dir, step=f"source build ({scope})",
        timeout=_BUILD_TIMEOUT, resource=f"build:{source_dir}",
    )
    return argv


def apply_project_files(assembly_dir: str, source_dir: str, slug: str,
                        scope: str, *, home: bool = False) -> list[str]:
    """Graft a built project into the assembly tree; return changed paths.

    The graft prunes rather than wipes: what the build produces is what the
    build owns, and only paths this publisher produced *before* and does not
    produce now are removed.  Everything else -- a post or a documentation
    page published between releases -- is somebody else's and survives.  The
    published-file record at ``manifests/<slug>-files.json`` is what makes
    that distinction possible.

    The build's output lands in two places, by the rule
    :func:`split_build_output` states: the project's documentation under
    ``site/<slug>/``, its posts at the site level under ``site/blog/``.

    *home* routes the documentation to the site root instead, which is the
    whole of what being the home project changes about a graft.  Its output
    is checked against the addresses the assembly owns first, and its
    curated listing is copied in beside the manifests.
    """
    build_root = os.path.join(source_dir, "docs", "_build")
    site_dir = os.path.join(assembly_dir, "site")
    site_slug_dir = os.path.join(site_dir, slug)
    manifests_dir = os.path.join(assembly_dir, "manifests")
    effects.makedirs(manifests_dir, exist_ok=True)
    touched: list[str] = []

    if scope == "posts":
        # Posts-only: this publisher's whole world is the build's post
        # output, so anything the clone happens to carry outside blog/ is
        # not its business and is not grafted.
        owner = "posts"
        outputs = {
            rel for rel in build_output_paths(build_root)
            if rel.split("/")[0] == POSTS_SEGMENT
        }
        src_manifest = os.path.join(source_dir, ".selfdoc", "post-manifest.json")
        dest_manifest = os.path.join(manifests_dir, f"{slug}-posts.json")
    else:
        owner = "release"
        outputs = build_output_paths(build_root)
        src_manifest = os.path.join(source_dir, ".selfdoc", "manifest.json")
        dest_manifest = os.path.join(manifests_dir, f"{slug}.json")

    produced = split_build_output(outputs, slug, home=home)
    if home:
        check_home_collisions(
            [rel for rel in produced.values()
             if rel.split("/")[0] != POSTS_SEGMENT],
            slug=slug,
        )

    if scope == "posts" and not produced:
        # A build that produced no posts is not an instruction to unpublish
        # the ones already on the site: the pruning publisher would remove
        # every path it claimed, and a posts build emits nothing when the
        # source's posts directory is empty or absent for any reason at all.
        print(
            f"posts scope for {slug!r}: the build produced no post pages, so "
            f"there is nothing to publish. Nothing was written and nothing "
            f"was removed -- posts already published stay. To unpublish a "
            f"post, delete it at the source and run a full release, which "
            f"republishes this project's whole post set.",
            file=sys.stderr,
        )
        return touched

    record_path = files_manifest_path(manifests_dir, slug)
    owners = load_files_manifest(record_path)
    removed, owners = prune_plan(owners, owner, set(produced.values()))

    # The site-level blog is one namespace shared by every project, so the
    # write itself is checked, not only the merge that reads the manifests
    # afterwards: a post path another project's record claims is refused
    # before anything is copied over it.
    refuse_foreign_post_overwrite(
        slug, produced.values(), foreign_post_claims(manifests_dir, slug),
    )

    graft_subtree(site_dir, build_root, produced, removed)
    # An artifact already in the tree from an older deploy is removed on
    # sight: the assembly serves one set of headers, redirects and worker for
    # the whole site, and a project's own copies fight them wherever they sit.
    # The home project has no subtree of its own to sweep -- its output was
    # filtered on the way in, by split_build_output.
    if not home:
        prune_deploy_artifacts(site_slug_dir)
        prune_empty_dirs(site_slug_dir)
    prune_empty_dirs(os.path.join(site_dir, POSTS_SEGMENT))
    touched.append(site_dir if home else site_slug_dir)
    if any(rel.split("/")[0] == POSTS_SEGMENT for rel in produced.values()):
        touched.append(os.path.join(site_dir, POSTS_SEGMENT))

    effects.write_text(record_path, render_files_manifest(slug, owners))
    touched.append(record_path)

    if os.path.isfile(src_manifest):
        effects.copy_file(src_manifest, dest_manifest)
        touched.append(dest_manifest)

    if home and scope != "posts":
        sidecar = copy_home_listing(assembly_dir, source_dir, slug)
        if sidecar:
            touched.append(sidecar)

    if owner == "release":
        overlay = fold_posts_into_overlay(manifests_dir, slug, src_manifest)
        if overlay:
            touched.append(overlay)
    return touched


def copy_home_listing(assembly_dir: str, source_dir: str, slug: str) -> str:
    """Copy the home project's curated listing into the assembly.

    The listing is authored in the home project (``docs/projects.toml``)
    because it is content, and it is copied here because both renderings of
    it -- the front page's cards and the generated ``/projects/`` page --
    are produced on every deploy, including deploys the home project has
    nothing to do with.

    A home project that declares no listing is a real state and leaves no
    sidecar; a malformed one is a hard error naming the file, raised here
    rather than at the far end where the document is no longer in reach.
    Returns the sidecar's path, or "" when there was nothing to copy.
    """
    from selfblog.listing import (
        LISTING_SOURCE, load_listing_source, render_listing_sidecar,
    )

    source = os.path.join(source_dir, *LISTING_SOURCE.split("/"))
    if not os.path.isfile(source):
        return ""
    listing = load_listing_source(source)
    manifests_dir = os.path.join(assembly_dir, "manifests")
    path = listing_sidecar_path(manifests_dir, slug)
    effects.write_text(path, render_listing_sidecar(listing, slug))
    return path


def fold_posts_into_overlay(manifests_dir: str, slug: str,
                            build_manifest: str) -> str:
    """Add a full build's posts to *slug*'s post overlay; return its path.

    The overlay is the assembly's one authority on a project's posts, so a
    full build cannot simply ignore it -- an overlay written before the
    release would keep the release's own posts off the site.  It used to
    delete the overlay outright for exactly that reason, which threw away
    every post published between releases along with the staleness.

    Folding is the version that keeps both: the build's posts go in, the
    overlay's posts that the build does not carry stay, and the file remains
    the complete list ``post publish`` overwrites wholesale.  Returns "" when
    there is no overlay to fold into.
    """
    overlay_path = os.path.join(manifests_dir, f"{slug}-posts.json")
    if not os.path.isfile(overlay_path) or not os.path.isfile(build_manifest):
        return ""
    with open(overlay_path, "r", encoding="utf-8") as f:
        overlay = json.load(f)
    with open(build_manifest, "r", encoding="utf-8") as f:
        built = json.load(f)
    overlay["posts"] = merge_post_lists(
        built.get("posts") or [], overlay.get("posts") or [],
    )
    effects.write_text(overlay_path, json.dumps(overlay, indent=2) + "\n")
    return overlay_path


def index_site(site_dir: str) -> None:
    """Build the pagefind search index over the assembled site."""
    _run_step(
        [sys.executable, "-m", "pagefind", "--site", site_dir],
        cwd=None, step="pagefind index", timeout=_INDEX_TIMEOUT,
        resource=f"search-index:{site_dir}",
    )


def verify_before_deploy(assembly_dir: str, *, canonical_base: str) -> list[str]:
    """Verify the assembled tree, or refuse to let the deploy continue.

    Returns the checks that ran.  A check that could not run says so on
    stderr rather than passing quietly -- an assertion nobody made must
    not look like one that held.

    The outbound results this produces are written back into the checkout
    so the next deploy inherits them; that write is the deploy's, not the
    verification's, which is why it happens here and not inside
    :func:`~selfblog.verify.verify_assembly`.

    Raises:
        RuntimeError: naming every offender, before anything is committed
            or pushed.
    """
    from selfblog.verify import (
        OUTBOUND_CACHE_PATH as _CACHE_PATH,
        render_outbound_cache,
        verify_assembly,
    )

    report = verify_assembly(assembly_dir, canonical_base=canonical_base)
    for check, reason in report.skipped:
        print(f"verify: {check} was NOT checked -- {reason}", file=sys.stderr)
    if not report.ok:
        raise RuntimeError(report.error_text())
    if report.outbound_cache:
        effects.write_text(
            os.path.join(assembly_dir, _CACHE_PATH),
            render_outbound_cache(report.outbound_cache),
        )
    return list(report.ran)


def integrate_project(
    *,
    slug: str,
    version: str,
    ref: str,
    source_repo: str,
    scope: str,
    canonical_base: str,
    assembly_dir: str = ".",
    source_dir: str = "",
    legacy_blog_host: str = "",
    branch: str = "main",
    attempts: int = 3,
    retry_delay: float = 5.0,
    git_user_name: str = "github-actions[bot]",
    git_user_email: str = "github-actions[bot]@users.noreply.github.com",
    build: bool = True,
) -> dict:
    """Integrate one dispatched project into the assembly repo and push.

    This is the body the generated deploy workflow used to embed as shell
    and inline interpreter snippets.  It builds the cloned source project,
    then -- inside a retry loop that re-syncs to the remote every attempt,
    so two concurrent deploys converge instead of clobbering each other --
    grafts the build into ``site/<slug>/``, refreshes the project's
    manifest and membership record, regenerates the shared cross-project
    files, rebuilds the search index, commits and pushes.

    Returns a summary dict: the scope actually run, the paths touched, the
    shared files regenerated, the attempt that pushed, and whether a
    commit was created at all.
    """
    scope = scope or "full"
    if scope not in INTEGRATE_SCOPES:
        raise ValueError(
            f"unknown scope {scope!r}; expected one of {', '.join(INTEGRATE_SCOPES)}"
        )
    if not slug and scope != "shared-only":
        raise ValueError("slug is required for a project-scoped integrate")
    if attempts < 1:
        raise ValueError("attempts must be at least 1")

    source_dir = source_dir or os.path.join(assembly_dir, "source", slug)
    site_dir = os.path.join(assembly_dir, "site")
    manifests_dir = os.path.join(assembly_dir, "manifests")
    projects_json = os.path.join(assembly_dir, PROJECTS_PATH)

    summary = {
        "scope": scope,
        "slug": slug,
        "version": version,
        "touched": [],
        "shared": [],
        "retired": [],
        "attempt": 0,
        "committed": False,
    }

    # The roster is read here as well as inside the loop, for one fact the
    # build itself needs: whether this slug is the home project, which
    # decides both how it is built and where its output lands. The reading
    # inside the loop stays authoritative -- it happens after the re-sync,
    # so a retirement or a change of home landed by another deploy is
    # honoured there.
    is_home = slug != "" and slug == load_roster(assembly_dir).home

    if scope != "shared-only" and build:
        build_source_project(
            source_dir, scope, home=is_home,
            manifests_dir=manifests_dir, docs_base=canonical_base,
        )

    last_push_error = ""
    for attempt in range(1, attempts + 1):
        summary["attempt"] = attempt

        # Re-sync to the remote first: another project's deploy may have
        # landed since this run started, and its files must survive ours.
        _run_step(["git", "fetch", "origin", branch], cwd=assembly_dir,
                  step="git fetch", timeout=_GIT_TIMEOUT,
                  resource=f"git-fetch:{assembly_dir}")
        _run_step(["git", "reset", "--hard", f"origin/{branch}"], cwd=assembly_dir,
                  step="git reset", timeout=_GIT_TIMEOUT,
                  resource=f"git-reset:{assembly_dir}")

        effects.makedirs(manifests_dir, exist_ok=True)

        # The roster is read after the re-sync, so a retirement another
        # deploy landed a minute ago is honoured by this one too. Every
        # scope reconciles: membership is declared, and the deploy's job is
        # to make the tree match the declaration whatever else it is doing.
        roster = load_roster(assembly_dir)
        if scope != "shared-only" and slug not in roster:
            raise RuntimeError(
                f"{slug!r} is not declared in {ROSTER_PATH} on the assembly "
                f"repository, so this dispatch has nothing to publish into. "
                f"Add a [[project]] block naming slug = {slug!r} and its "
                f"repo, then dispatch again."
            )
        summary["retired"] = reconcile_membership(assembly_dir, roster)["retired"]

        if scope != "shared-only":
            summary["touched"] = apply_project_files(
                assembly_dir, source_dir, slug, scope,
                home=slug == roster.home,
            )
            record_membership(
                projects_json, roster, slug, source_repo, ref, version,
            )

        summary["shared"] = generate_shared_files(
            site_dir, manifests_dir, canonical_base,
            docs_base=canonical_base,
            legacy_blog_host=legacy_blog_host,
            home_slug=roster.home,
        )

        index_site(site_dir)

        # Everything the deploy publishes exists now, and nothing has left
        # this checkout yet. This is the last moment a broken tree can be
        # refused instead of served, so it is where it is refused.
        summary["verified"] = verify_before_deploy(
            assembly_dir, canonical_base=canonical_base,
        )

        staged = ["site", "manifests", "projects.json"]
        if os.path.isfile(os.path.join(assembly_dir, OUTBOUND_CACHE_PATH)):
            staged.append(OUTBOUND_CACHE_PATH)
        _run_step(["git", "add", *staged],
                  cwd=assembly_dir, step="git add", timeout=_GIT_TIMEOUT,
                  resource=f"git-add:{assembly_dir}")

        label = f"deploy: {slug} v{version}" if scope != "shared-only" else "deploy: shared elements"
        commit = _run_step(
            ["git", "-c", f"user.name={git_user_name}",
             "-c", f"user.email={git_user_email}",
             "commit", "-m", label],
            cwd=assembly_dir, step="git commit", timeout=_GIT_TIMEOUT,
            resource=f"git-commit:{assembly_dir}", check=False,
            capture_output=True,
        )
        if commit is None:
            # Preview mode: nothing ran, so there is no push to attempt.
            return summary
        summary["committed"] = commit.returncode == 0

        push = _run_step(["git", "push", "origin", f"HEAD:{branch}"],
                         cwd=assembly_dir, step="git push", timeout=_GIT_TIMEOUT,
                         resource=f"git-push:{assembly_dir}", grant="assembly-commit",
                         check=False, capture_output=True)
        if push is None or push.returncode == 0:
            return summary
        last_push_error = (push.stderr or "").strip()
        if attempt < attempts:
            time.sleep(retry_delay)

    raise RuntimeError(
        f"assembly push failed after {attempts} attempt(s): {last_push_error}"
    )


# -- dispatch: which tag is this project's tag -------------------------------


_TAG_VERSION_RE = re.compile(
    r"^(?P<family>.*?)v?(?P<version>\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.\-+]+)?)$"
)


def parse_version_tag(tag: str) -> tuple[str, str] | None:
    """Split *tag* into (family prefix, version), or None if it is not one.

    ``v1.2.3`` -> ``("", "1.2.3")``; ``selfblog@v0.3.1`` ->
    ``("selfblog@", "0.3.1")``; ``mypkg/v2.0.0-rc.1`` ->
    ``("mypkg/", "2.0.0-rc.1")``.
    """
    match = _TAG_VERSION_RE.match(tag.strip())
    if not match:
        return None
    return match.group("family"), match.group("version")


def resolve_project_tag(tags: list[str], version: str) -> str:
    """Return the tag that names *version* for this project.

    Tag resolution used to be "the repository's newest tag by creation
    date", which is wrong in any repo that releases more than one thing:
    a sibling package released an hour later owns the newest tag, and the
    assembly then builds that sibling's ref under this project's slug.
    That shipped a 404 stub to the live site once.

    The version being dispatched is the anchor instead: the tag has to
    carry that version, whatever family prefix it wears.  Two families at
    the same version is a hard error rather than a coin flip, and a
    version with no tag is a hard error rather than a fallback onto
    something newer.
    """
    if not version:
        raise RuntimeError(
            "cannot resolve a release tag without a version; set 'version' "
            "in selfdoc.json or run this from a project with a detectable "
            "version"
        )
    parsed = [(tag, parse_version_tag(tag)) for tag in tags]
    version_tags = [(tag, info) for tag, info in parsed if info is not None]
    matches = [tag for tag, info in version_tags if info[1] == version]

    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        raise RuntimeError(
            f"ambiguous release tag for version {version}: "
            f"{', '.join(sorted(matches))}. Two tag families carry the same "
            f"version, so the dispatch cannot tell which one is this "
            f"project's."
        )

    families = sorted({info[0] for _tag, info in version_tags})
    known = f" Tag families in this repo: {', '.join(repr(f) for f in families)}." if families else ""
    raise RuntimeError(
        f"no git tag names version {version}.{known} Release this project "
        f"before dispatching an assembly rebuild -- the assembly builds the "
        f"tag, so an untagged version would publish the wrong docs."
    )


def list_repo_tags(cwd: str = ".") -> list[str]:
    """Return the repository's tags, newest creation date first."""
    result = effects.run(
        ["git", "for-each-ref", "--sort=-creatordate",
         "--format=%(refname:short)", "refs/tags"],
        cwd=cwd, capture_output=True, text=True, timeout=30, read=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"failed to list git tags: {result.stderr.strip()}")
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def check_version_is_declared(config: dict, version: str) -> None:
    """Raise unless *version* is the version the build will actually produce.

    Membership in ``versions`` was never the question.  The assembly builds
    ``versions[-1]`` and records the dispatch under the version the payload
    carries, so dispatching a version that is merely *present* in the array
    publishes the newest version's docs under the dispatched version's name
    -- silently, and for as long as nobody compares the two.  The two have
    to be the same version, and :func:`build_target_version` is what says
    which one the build produces.
    """
    declared = [
        str(entry.get("version"))
        for entry in (config.get("versions") or [])
        if isinstance(entry, dict) and entry.get("version")
    ]
    if not declared:
        raise RuntimeError(
            "selfdoc.json declares no versions; the assembly has nothing to "
            "build. Add the released version to 'versions'."
        )
    target = build_target_version(config)
    if version != target:
        raise RuntimeError(
            f"version {version} is not the version the assembly would build. "
            f"selfdoc.json's newest declared version is {target} (declared: "
            f"{', '.join(declared)}), and the build takes the newest one -- so "
            f"this dispatch would publish {target}'s docs recorded under the "
            f"name {version}. Make {version} the last entry of 'versions'."
        )


def _gh_api(args: list[str], input_data: str | None = None, step: str = "",
            *, read: bool = False, resource: str | None = None,
            grant: str | None = None) -> str:
    """Run a gh api command and return stdout. Raise RuntimeError on failure.

    *read* declares a GET-shaped call, which changes nothing and therefore
    executes in every mode.  A non-read call is a network mutation: under a
    command's ``--dry-run`` it is recorded and the returned carrier has no
    stdout to read, so the framework truncates the preview at that point --
    the honest outcome for an API whose next step needs a SHA that was never
    minted.
    """
    cmd = ["gh", "api", *args]
    try:
        result = effects.run(
            cmd,
            input=input_data,
            capture_output=True,
            text=True,
            timeout=30,
            read=read,
            resource=resource,
            grant=grant,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"{step}: gh api timed out after 30s")
    if result.returncode != 0:
        raise RuntimeError(f"{step}: {result.stderr.strip()}")
    return result.stdout.strip()


@dataclasses.dataclass(frozen=True)
class PushResult:
    """What one :func:`push_files_to_repo` call did.

    ``changed`` is false when every file already matched the branch and
    nothing was deleted -- no commit exists in that case and ``sha`` is
    the untouched head.  A caller that regenerates an artifact on every
    release reads this to tell "wrote it" from "it was already right".
    """

    sha: str
    changed: bool
    uploaded: tuple[str, ...] = ()
    deleted: tuple[str, ...] = ()


def git_blob_sha1(data: bytes) -> str:
    """Return git's object id for a blob holding *data*.

    Git hashes ``blob <len>\\0<bytes>``, so this is computable locally and
    comparable against the ``sha`` the Trees API reports for a path --
    which is how an unchanged file is recognized without uploading it.
    """
    header = f"blob {len(data)}\0".encode()
    return hashlib.sha1(header + data).hexdigest()


def _remote_blob_shas(repo: str, tree_sha: str) -> dict[str, str]:
    """Return path -> blob sha for every file in *tree_sha*, recursively."""
    raw = _gh_api(
        [f"/repos/{repo}/git/trees/{tree_sha}", "-f", "recursive=1"],
        step="list tree",
        read=True,
    )
    try:
        tree = json.loads(raw) if raw else {}
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"list tree: unparseable response: {exc}") from exc
    if tree.get("truncated"):
        raise RuntimeError(
            f"list tree: {repo}'s tree is too large for the Trees API to "
            f"return in one response, so unchanged files cannot be "
            f"identified. Push through a clone instead."
        )
    return {
        entry["path"]: entry["sha"]
        for entry in tree.get("tree", [])
        if entry.get("type") == "blob"
    }


def push_files_to_repo(
    repo: str,
    files: dict[str, str | bytes] | None,
    message: str,
    branch: str = "main",
    *,
    delete_paths: list[str] | None = None,
) -> PushResult:
    """Push files and deletions to a remote repo in one commit via the Git Data API.

    Uses the GitHub REST API (via gh cli) to create blobs, a tree, a commit,
    and update the branch ref -- all without cloning.

    Content may be ``str`` (encoded UTF-8) or ``bytes``, which travel to the
    blob API base64-encoded either way, so an image round-trips
    byte-identically instead of dying on ``str.encode``.

    Every path is hashed locally with git's own blob hash and compared
    against the remote tree: a file whose bytes already match uploads no
    blob and contributes no tree entry.  When nothing differs and nothing
    is deleted, no commit is created at all and the current head SHA comes
    back -- which is what makes a regenerating writer idempotent.

    Args:
        repo: GitHub repo identifier (e.g. "smm-h/selfdoc-cache").
        files: Mapping of file paths to str or bytes content.
        message: Commit message.
        branch: Target branch (default "main").
        delete_paths: Paths to remove from the branch in the same commit.
            A path that is already absent is not an error -- the commit
            just does not mention it.

    Returns:
        A :class:`PushResult`. When nothing differed, ``changed`` is false
        and ``sha`` is the untouched head SHA -- no commit was created.

    Raises:
        ValueError: If there is neither a file nor a deletion to push.
        RuntimeError: If any API call fails.
    """
    files = files or {}
    delete_paths = list(delete_paths or [])
    if not files and not delete_paths:
        raise ValueError("files dict is empty -- nothing to push")

    # 1. Get current HEAD SHA
    head_sha = _gh_api(
        [f"/repos/{repo}/git/ref/heads/{branch}", "--jq", ".object.sha"],
        step="get HEAD ref",
        read=True,
    )

    # 2. Get the current tree SHA
    tree_sha = _gh_api(
        [f"/repos/{repo}/git/commits/{head_sha}", "--jq", ".tree.sha"],
        step="get tree SHA",
        read=True,
    )

    # 3. Learn what the branch already holds, so unchanged files stay home
    remote_shas = _remote_blob_shas(repo, tree_sha)

    # 4. Create a blob for each changed file
    tree_entries: list[dict] = []
    uploaded: list[str] = []
    deleted: list[str] = []
    for path, content in files.items():
        data = content if isinstance(content, bytes) else content.encode()
        if remote_shas.get(path) == git_blob_sha1(data):
            continue
        encoded = base64.b64encode(data).decode()
        payload = json.dumps({"content": encoded, "encoding": "base64"})
        blob_sha = _gh_api(
            ["--method", "POST", f"/repos/{repo}/git/blobs", "--jq", ".sha", "--input", "-"],
            input_data=payload,
            step=f"create blob for {path}",
            resource=f"gh-blob:{repo}/{path}",
        )
        tree_entries.append(
            {"path": path, "mode": "100644", "type": "blob", "sha": blob_sha}
        )
        uploaded.append(path)

    # 5. A null sha on an existing path is how the Trees API spells deletion
    for path in delete_paths:
        if path not in remote_shas:
            continue
        tree_entries.append(
            {"path": path, "mode": "100644", "type": "blob", "sha": None}
        )
        deleted.append(path)

    if not tree_entries:
        return PushResult(sha=head_sha, changed=False)

    # 6. Create a new tree
    tree_payload = json.dumps({"base_tree": tree_sha, "tree": tree_entries})
    new_tree_sha = _gh_api(
        ["--method", "POST", f"/repos/{repo}/git/trees", "--jq", ".sha", "--input", "-"],
        input_data=tree_payload,
        step="create tree",
        resource=f"gh-tree:{repo}",
    )

    # 7. Create a commit
    commit_payload = json.dumps({
        "message": message,
        "tree": new_tree_sha,
        "parents": [head_sha],
    })
    new_commit_sha = _gh_api(
        ["--method", "POST", f"/repos/{repo}/git/commits", "--jq", ".sha", "--input", "-"],
        input_data=commit_payload,
        step="create commit",
        resource=f"gh-commit:{repo}",
    )

    # 8. Update the ref
    ref_payload = json.dumps({"sha": new_commit_sha})
    _gh_api(
        ["--method", "PATCH", f"/repos/{repo}/git/refs/heads/{branch}", "--jq", ".object.sha", "--input", "-"],
        input_data=ref_payload,
        step="update ref",
        resource=f"gh-ref:{repo}/{branch}",
    )

    return PushResult(
        sha=new_commit_sha,
        changed=True,
        uploaded=tuple(uploaded),
        deleted=tuple(deleted),
    )


# -- reading the assembly from the outside -----------------------------------


def list_remote_paths(repo: str, branch: str = "main") -> list[str]:
    """Return every file path on *repo*'s *branch*, recursively.

    This is how a publisher that never clones the assembly learns what is
    already there: which of a project's pages exist remotely, so the ones the
    local build no longer produces can be deleted in the same commit that
    uploads the ones it does.
    """
    head_sha = _gh_api(
        [f"/repos/{repo}/git/ref/heads/{branch}", "--jq", ".object.sha"],
        step="get HEAD ref",
        read=True,
    )
    tree_sha = _gh_api(
        [f"/repos/{repo}/git/commits/{head_sha}", "--jq", ".tree.sha"],
        step="get tree SHA",
        read=True,
    )
    return sorted(_remote_blob_shas(repo, tree_sha))


class RemoteReadError(RuntimeError):
    """A read from the assembly repository did not succeed and did not 404.

    Kept distinct from the absent-file outcome because the two used to be the
    same value.  Every publisher treats an absent published-file record or an
    absent membership record as the real initial state and writes a fresh one
    over it; a rate limit, an expired token or a 502 returned that same
    "nothing there" and the fresh record destroyed whatever the read failed
    to see.  A failure now stops the operation before anything is written.
    """


# gh reports the HTTP status in its error line -- "gh: Not Found (HTTP 404)",
# "gh: API rate limit exceeded ... (HTTP 403)".  A failure with no status at
# all did not reach the API (DNS, timeout, gh missing) and is never absence.
_GH_HTTP_STATUS_RE = re.compile(r"\(HTTP (\d{3})\)")


def _gh_http_status(stderr: str) -> int | None:
    """Return the HTTP status gh reported, or None if it reported none."""
    match = _GH_HTTP_STATUS_RE.search(stderr or "")
    return int(match.group(1)) if match else None


def fetch_remote_text(repo: str, path: str, *, missing_ok: bool = False,
                      operation: str = "") -> str:
    """Return the text of *path* on *repo*'s default branch.

    Absence and failure are two outcomes, not one.  Only an explicit HTTP 404
    means the file is not there, and only then does *missing_ok* turn it into
    the empty string -- the real initial state of a record nothing has written
    yet.  Every other outcome raises :class:`RemoteReadError` naming
    *operation*, the path and what gh said, because a caller that reads "" as
    "nothing published yet" would then write a record that erases what it
    could not read.

    *operation* describes what the read is for, so the error says which
    operation was abandoned rather than only which path was unreadable.
    """
    what = operation or f"read {path} from {repo}"
    result = effects.run(
        ["gh", "api", f"/repos/{repo}/contents/{path}", "--jq", ".content"],
        check=False, capture_output=True, text=True, timeout=30, read=True,
    )
    if result.returncode != 0:
        stderr = (result.stderr or "").strip()
        detail = stderr or f"gh api exited {result.returncode} with no output"
        if _gh_http_status(stderr) == 404:
            if missing_ok:
                return ""
            raise RemoteReadError(
                f"{what}: {path} does not exist on {repo} ({detail})."
            )
        raise RemoteReadError(
            f"{what}: reading {path} from {repo} failed, and the failure is "
            f"not an absent file, so it cannot be read as one: {detail}. "
            f"Nothing was written. Re-run once the read succeeds."
        )
    encoded = "".join((result.stdout or "").split())
    if not encoded:
        return ""
    try:
        return base64.b64decode(encoded).decode()
    except (ValueError, UnicodeDecodeError) as exc:
        raise RemoteReadError(
            f"{what}: could not decode {path} from {repo}: {exc}"
        ) from exc


def load_remote_roster(repo: str) -> Roster:
    """Return the roster declared on the assembly repository *repo*.

    An absent roster is its own error naming the block that has to exist; a
    failed read is a :class:`RemoteReadError`, never mistaken for one.
    """
    text = fetch_remote_text(
        repo, ROSTER_PATH, missing_ok=True,
        operation=f"read the assembly roster on {repo}",
    )
    if not text.strip():
        raise _missing_roster_error(f"{repo}:{ROSTER_PATH}")
    return parse_roster(text, source=f"{repo}:{ROSTER_PATH}")


def project_paths(paths, slug: str, claimed=()) -> list[str]:
    """Return every assembly path that belongs to *slug*.

    That is its whole site subtree, plus every one of its manifest kinds --
    the base manifest, the posts overlay, the revisions sidecar and the
    published-file record -- plus *claimed*, the site-relative paths its
    published-file record names outside that subtree.  Its posts are all of
    the last kind: they sit at the site level under ``blog/``, so removing
    the subtree alone would leave them on the blog with nothing left to
    explain where they came from.
    """
    site_prefix = f"site/{slug}/"
    manifest_prefix = f"manifests/{slug}-"
    base_manifest = f"manifests/{slug}.json"
    outside = {f"site/{rel}" for rel in claimed}
    owned = [
        path for path in paths
        if path.startswith(site_prefix)
        or path in outside
        or path == base_manifest
        or (path.startswith(manifest_prefix) and path.endswith(".json"))
    ]
    return sorted(set(owned))


def retire_project(repo: str, slug: str, *, branch: str = "main") -> dict:
    """Remove *slug* from the assembly's roster and tree in one commit.

    Retirement is a roster edit plus the reconciliation that edit implies,
    done together so the published site never lags the declaration: the
    ``[[project]]`` block goes, the derived membership record loses its
    entry, and every path the project owns -- its whole section and all its
    manifest kinds -- is deleted in the same commit.  What remains is the
    shared elements, which the caller regenerates by dispatching a
    shared-only rebuild; that pass also rebuilds the search index, so the
    retired project stops answering searches.

    Returns a summary: the paths deleted, the roster that remains, and the
    :class:`PushResult`.
    """
    roster = load_remote_roster(repo)
    if slug not in roster:
        declared = ", ".join(sorted(roster)) or "(none)"
        raise RuntimeError(
            f"{slug!r} is not declared in {ROSTER_PATH} on {repo}, so there "
            f"is nothing to retire. Declared projects: {declared}."
        )

    if slug == roster.home:
        raise RuntimeError(
            f"{slug!r} is the home project: {ROSTER_PATH} on {repo} names it "
            f"home, so it is the site's front page and every page it serves "
            f"is at the site root. Retiring it would leave the site with no "
            f"front page. Name another declared project home first, then "
            f"retire this one."
        )

    remaining = [entry for name, entry in roster.items() if name != slug]
    record_path = f"manifests/{slug}-files.json"
    # A project that published nothing outside its subtree has no record, and
    # that is a real state.  A failed read is not: retirement would compute an
    # empty claim set and leave the project's posts on the site-level blog
    # with nothing left to explain where they came from.
    record = parse_files_manifest(
        fetch_remote_text(
            repo, record_path, missing_ok=True,
            operation=f"retire {slug!r} from {repo}",
        ),
        source=f"{repo}:{record_path}",
    )
    claimed = {
        path
        for paths in record.values()
        for path in paths
        if not path.startswith(f"{slug}/")
    }
    deleted = project_paths(list_remote_paths(repo, branch), slug, claimed)

    files: dict[str, str | bytes] = {
        ROSTER_PATH: render_roster(remaining, home=roster.home),
    }

    # No membership record yet is a real state; a failed read is not, and
    # would silently leave the retired project's entry behind.
    raw_membership = fetch_remote_text(
        repo, PROJECTS_PATH, missing_ok=True,
        operation=f"retire {slug!r} from {repo}",
    )
    if raw_membership.strip():
        try:
            membership = json.loads(raw_membership)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"{repo}:{PROJECTS_PATH} is not valid JSON: {exc}") from exc
        if not isinstance(membership, dict):
            raise RuntimeError(f"{repo}:{PROJECTS_PATH} must contain a JSON object")
        if slug in membership:
            del membership[slug]
            files[PROJECTS_PATH] = render_projects_json(membership)

    push = push_files_to_repo(
        repo, files, f"assembly: retire {slug}", branch, delete_paths=deleted,
    )
    return {
        "slug": slug,
        "deleted": deleted,
        "remaining": sorted(entry.slug for entry in remaining),
        "push": push,
    }


def collect_site_files(output_dir: str, slug: str) -> dict[str, bytes]:
    """Return assembly path -> bytes for every file a local build produced.

    Content travels as bytes because a documentation site is not all text:
    fonts, favicons and screenshots go through the same commit as the HTML,
    and decoding them as UTF-8 on the way past would destroy them.  The same
    per-project deploy artifacts the deploy filters out are filtered here --
    see :func:`build_output_paths` -- and the output is split the same way a
    deploy splits it, so a locally built post lands on the site-level blog
    rather than inside the project's subtree.  See
    :func:`split_build_output`.
    """
    files: dict[str, bytes] = {}
    produced = split_build_output(build_output_paths(output_dir), slug)
    for build_rel, site_rel in sorted(produced.items()):
        with open(os.path.join(output_dir, *build_rel.split("/")), "rb") as f:
            files[f"site/{site_rel}"] = f.read()
    return files


def publish_project_docs(
    repo: str,
    slug: str,
    output_dir: str,
    *,
    version: str,
    manifest_path: str = "",
    branch: str = "main",
) -> dict:
    """Push a locally built documentation site into the assembly.

    This is the documentation counterpart of publishing a post: a
    documentation change reaches the live site with no tag and no release,
    through the same Git Data API commit that a post takes.  What it pushes
    is the project's subtree, its manifest, its published-file record and its
    derived membership entry; what it deletes is every page it published
    before and does not publish now, so a page removed locally disappears
    remotely.

    It cannot create membership: publishing into a slug the roster does not
    declare is a hard error naming the block that would have to exist.

    Returns a summary: the paths uploaded and deleted, and the
    :class:`PushResult`.
    """
    roster = load_remote_roster(repo)
    if slug not in roster:
        declared = ", ".join(sorted(roster)) or "(none)"
        raise RuntimeError(
            f"{slug!r} is not declared in {ROSTER_PATH} on {repo}, so there is "
            f"no section to publish into. Membership is declared, never "
            f"created by a publish. Add a [[project]] block naming "
            f"slug = {slug!r} and its repo. Declared projects: {declared}."
        )

    produced = set(split_build_output(build_output_paths(output_dir), slug).values())

    # A full documentation build carries the project's posts too, and a post
    # is site-level: it addresses `blog/<post-slug>/` with no project segment,
    # in a namespace every project shares. The write is refused before
    # anything is collected, exactly as the integrate graft refuses it.
    refuse_foreign_post_overwrite(
        slug, produced, remote_post_claims(repo, slug, roster),
    )

    files: dict[str, str | bytes] = dict(collect_site_files(output_dir, slug))

    delete_paths = stage_published_record(repo, slug, "docs", produced, files)

    if manifest_path and os.path.isfile(manifest_path):
        with open(manifest_path, "r", encoding="utf-8") as f:
            files[f"manifests/{slug}.json"] = f.read()

    # An assembly with no membership record at all is a real state; a failed
    # read is not.  This publish rewrites the whole record, so reading a
    # failure as "empty" would push a file naming only this project and
    # destroy every other project's entry.
    raw_membership = fetch_remote_text(
        repo, PROJECTS_PATH, missing_ok=True,
        operation=f"publish {slug!r} documentation to {repo}",
    )
    membership: dict = {}
    if raw_membership.strip():
        try:
            membership = json.loads(raw_membership)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"{repo}:{PROJECTS_PATH} is not valid JSON: {exc}") from exc
        if not isinstance(membership, dict):
            raise RuntimeError(f"{repo}:{PROJECTS_PATH} must contain a JSON object")
    # A documentation publish has no tag, which is the point of it, so it
    # records the version it built and leaves whatever ref the last release
    # recorded alone. A project that has never been released therefore has no
    # ref here, and `assembly rebuild` says so rather than inventing one.
    previous = membership.get(slug) if isinstance(membership.get(slug), dict) else {}
    entry = {"repo": roster[slug].repo, "version": version}
    if previous.get("ref"):
        entry["ref"] = previous["ref"]
    membership[slug] = entry
    files[PROJECTS_PATH] = render_projects_json(membership)

    push = push_files_to_repo(
        repo, files, f"docs: {slug} {version}".strip(), branch,
        delete_paths=delete_paths,
    )
    return {
        "slug": slug,
        "published": sorted(produced),
        "deleted": delete_paths,
        "push": push,
    }
