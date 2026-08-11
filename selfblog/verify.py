"""Whether a built assembly tree is fit to deploy.

The deploy used to be the first reader of the tree it published: the
graft, the shared generator and the search index each did their part, the
result was committed, and whatever was wrong with it became the live site.
This module is the reading that happens before the push -- one pass over
the assembled tree asserting every property the site depends on, each
failure naming its offender.

What is asserted
----------------

* **Membership agrees in both directions.**  The declared roster, the
  ``site/`` subtrees and the files under ``manifests/`` name the same
  projects: no undeclared subtree, no declared project missing, no orphan
  manifest of any kind.
* **Each manifest describes the tree it sits next to.**  Its slug names
  its own directory, its version is the version the emitted pages carry
  (and is not sitting in the archive tree as though it were superseded),
  and every page and post it lists resolves to a file that exists.
* **The shared artifacts exist and parse.**  Front page, blog index,
  project listing, ``nav.json``, sitemap, feed, search index, robots and
  the root 404.
* **Every reference resolves.**  Internal links, canonicals, sitemap
  entries and feed links all go through :mod:`selfdoc_core.resolution` --
  the same LINK001 pass a single project's build is checked with, run over
  the assembled tree.
* **Every page is addressable.**  A title, and a canonical under the
  site's canonical base.
* **Nothing half-built or per-project leaked in.**  No unresolved
  directive markers, and none of the per-project routing artifacts the
  graft filters out.
* **Cross-project links land somewhere.**  Extracted from the emitted
  pages and checked against what the manifests say exists.
* **Outbound links still answer**, when the assembly declares a list of
  pages to check them on.  See :func:`load_outbound`.

The outbound cache is the one piece of state a verification produces.
Verification itself never writes: :func:`verify_assembly` returns the
updated cache and the caller decides whether to keep it, which is why the
``assembly verify`` command is read-only and the deploy -- which does
write, and commits the result -- is where the cache actually persists
between runs.
"""

from __future__ import annotations

import dataclasses
import json
import os
import re
import time
import xml.etree.ElementTree as ET

from selfblog.shared import (
    POSTS_SEGMENT,
    output_path_target,
    page_target,
    post_target,
    target_output_path,
    validate_cross_project_links,
)
from selfdoc_core.resolution import (
    check_output_resolution,
    external_references,
    page_references,
    reference_target,
    site_relative_path,
)

__all__ = [
    "CHECKS",
    "Failure",
    "OutboundConfig",
    "VerifyReport",
    "load_outbound",
    "load_outbound_cache",
    "parse_outbound",
    "render_outbound_cache",
    "verify_assembly",
]

#: Every assertion, in the order a run reports them.  A check that finds
#: nothing still reports itself as run, so a report can tell "asserted and
#: clean" from "never asked".
CHECKS = (
    "roster-agreement",
    "manifest-identity",
    "manifest-pages-emitted",
    "manifest-posts-emitted",
    "shared-artifacts",
    "internal-references",
    "sitemap-entries",
    "feed-links",
    "page-metadata",
    "unresolved-directives",
    "routing-artifacts",
    "cross-project-links",
    "outbound-links",
)

#: The declared list of pages whose outbound links are checked.  Absent
#: means outbound checking is not configured, which the report says out
#: loud rather than passing quietly.
OUTBOUND_PATH = "outbound.toml"

#: Where the deploy keeps outbound results between runs.
OUTBOUND_CACHE_PATH = "outbound-cache.json"

OUTBOUND_TABLES = ("page",)
OUTBOUND_KEYS = ("cache_days", "page")
OUTBOUND_PAGE_KEYS = ("path",)

#: How long a fetch of an outbound URL is trusted before it is repeated.
_SECONDS_PER_DAY = 86400

_OUTBOUND_TIMEOUT = 15

#: What the assembly itself is allowed to serve at the site root.  Every
#: other routing artifact belongs to a single project's own standalone
#: hosting and fights the site-wide one wherever it lands.
SHARED_ROUTING_FILES = ("_headers", "_worker.js")
ROUTING_ARTIFACT_NAMES = ("_headers", "_redirects", "_worker.js")
ROUTING_ARTIFACT_SUFFIXES = (".gz", ".br")

_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_CANONICAL_TAG_RE = re.compile(
    r"""<link\b[^>]*\brel\s*=\s*["']?canonical["']?[^>]*>""", re.IGNORECASE,
)
_HREF_RE = re.compile(r"""\bhref\s*=\s*["']([^"']*)["']""", re.IGNORECASE)
_VERSION_ATTR_RE = re.compile(r'data-default-version="([^"]*)"')
_CODE_BLOCK_RE = re.compile(
    r"<pre\b.*?</pre>|<code\b.*?</code>", re.IGNORECASE | re.DOTALL,
)
#: The visible marker the build leaves where a directive did not resolve,
#: and the raw markers a template carries before one is parsed at all.
_STUB_MARKER_RE = re.compile(r"\[selfdoc:[^\]]*not yet resolved\]")
_RAW_MARKER_RE = re.compile(r"(?m)^\s*(:-:|:&lt;:|:@:|:=:|:&gt;:)\s*\S")


@dataclasses.dataclass(frozen=True)
class Failure:
    """One asserted property, one offender."""

    check: str
    offender: str
    message: str

    def __str__(self) -> str:
        return f"[{self.check}] {self.offender}: {self.message}"


@dataclasses.dataclass
class VerifyReport:
    """What a verification found.

    Attributes:
        failures: Every violated property, in check order.
        ran: The checks that were asserted.
        skipped: ``(check, reason)`` for each check that could not run,
            which is never silent -- the CLI prints them and the deploy
            logs them.
        outbound_cache: The outbound store as this run leaves it.  The
            caller persists it or does not; verification does not write.
        requests: How many outbound fetches this run actually made.
    """

    failures: list[Failure] = dataclasses.field(default_factory=list)
    ran: list[str] = dataclasses.field(default_factory=list)
    skipped: list[tuple[str, str]] = dataclasses.field(default_factory=list)
    outbound_cache: dict = dataclasses.field(default_factory=dict)
    requests: int = 0

    @property
    def ok(self) -> bool:
        return not self.failures

    def failures_of(self, check: str) -> list[Failure]:
        return [f for f in self.failures if f.check == check]

    def error_text(self) -> str:
        """The whole report as one message, for a raise or a stderr dump."""
        lines = [
            f"the assembled tree failed verification: {len(self.failures)} "
            f"problem(s) across "
            f"{len({f.check for f in self.failures})} check(s)."
        ]
        for check in CHECKS:
            found = self.failures_of(check)
            if not found:
                continue
            lines.append(f"  {check}:")
            for failure in found:
                lines.append(f"    {failure.offender}: {failure.message}")
        return "\n".join(lines)


# -- the tree a verification reads -------------------------------------------


@dataclasses.dataclass(frozen=True)
class AssemblyTree:
    """The assembled tree, read once and handed to every check."""

    assembly_dir: str
    site_dir: str
    manifests_dir: str
    canonical_base: str
    roster: dict
    manifests: list[dict]
    manifest_files: dict[str, dict]
    overlay_files: dict[str, dict]
    emitted: set[str]
    pages: list[str]
    has_portfolio: bool

    def read(self, rel: str) -> str:
        with open(os.path.join(self.site_dir, *rel.split("/")),
                  encoding="utf-8") as f:
            return f.read()


def _emitted_paths(site_dir: str) -> set[str]:
    found: set[str] = set()
    if not os.path.isdir(site_dir):
        return found
    for dirpath, _dirs, files in os.walk(site_dir):
        for name in files:
            rel = os.path.relpath(os.path.join(dirpath, name), site_dir)
            found.add(rel.replace(os.sep, "/"))
    return found


def read_tree(assembly_dir: str, canonical_base: str) -> AssemblyTree:
    """Read everything a verification needs out of *assembly_dir*."""
    from selfblog.assembly import (
        MANIFEST_SIDECAR_SUFFIXES,
        load_assembly_manifests,
        load_roster,
    )

    site_dir = os.path.join(assembly_dir, "site")
    manifests_dir = os.path.join(assembly_dir, "manifests")

    manifest_files: dict[str, dict] = {}
    overlay_files: dict[str, dict] = {}
    if os.path.isdir(manifests_dir):
        for name in sorted(os.listdir(manifests_dir)):
            if not name.endswith(".json"):
                continue
            if name.endswith(MANIFEST_SIDECAR_SUFFIXES):
                continue
            with open(os.path.join(manifests_dir, name), encoding="utf-8") as f:
                data = json.load(f)
            stem = name[: -len(".json")]
            if stem.endswith("-posts"):
                overlay_files[stem[: -len("-posts")]] = data
            else:
                manifest_files[stem] = data

    emitted = _emitted_paths(site_dir)
    return AssemblyTree(
        assembly_dir=assembly_dir,
        site_dir=site_dir,
        manifests_dir=manifests_dir,
        canonical_base=canonical_base.rstrip("/"),
        roster=load_roster(assembly_dir),
        manifests=load_assembly_manifests(manifests_dir),
        manifest_files=manifest_files,
        overlay_files=overlay_files,
        emitted=emitted,
        pages=sorted(p for p in emitted if p.endswith(".html")),
        has_portfolio=os.path.isfile(
            os.path.join(assembly_dir, "portfolio", "index.html")
        ),
    )


# -- the assertions ----------------------------------------------------------


def check_roster_agreement(tree: AssemblyTree) -> list[Failure]:
    """Roster, site subtrees and manifests name the same projects."""
    from selfblog.assembly import (
        PROJECTS_PATH,
        SITE_RESERVED_DIRS,
        _manifest_owner,
        load_projects_json,
    )

    declared = set(tree.roster)
    failures = []

    subtrees = set()
    if os.path.isdir(tree.site_dir):
        for name in sorted(os.listdir(tree.site_dir)):
            if not os.path.isdir(os.path.join(tree.site_dir, name)):
                continue
            if name in SITE_RESERVED_DIRS:
                continue
            subtrees.add(name)

    for name in sorted(subtrees - declared):
        failures.append(Failure(
            "roster-agreement", f"site/{name}",
            f"a subtree no [[project]] block declares. Membership is "
            f"declared, never accumulated: add {name!r} to the roster or "
            f"retire it.",
        ))
    for slug in sorted(declared - subtrees):
        failures.append(Failure(
            "roster-agreement", slug,
            "declared in the roster but has no site/ subtree, so the site "
            "would list a project it cannot serve.",
        ))

    if os.path.isdir(tree.manifests_dir):
        for name in sorted(os.listdir(tree.manifests_dir)):
            if not name.endswith(".json"):
                continue
            if _manifest_owner(name[: -len(".json")], declared) is None:
                failures.append(Failure(
                    "roster-agreement", f"manifests/{name}",
                    "an orphan manifest: its slug is not declared in the "
                    "roster.",
                ))

    for slug in sorted(declared):
        if slug not in tree.manifest_files:
            failures.append(Failure(
                "roster-agreement", slug,
                "declared in the roster but has no manifests/<slug>.json, "
                "so it appears in no listing, feed or sitemap.",
            ))

    membership = load_projects_json(
        os.path.join(tree.assembly_dir, PROJECTS_PATH)
    )
    for slug in sorted(set(membership) - declared):
        failures.append(Failure(
            "roster-agreement", f"{PROJECTS_PATH}:{slug}",
            "a membership record for a project the roster does not declare.",
        ))
    return failures


def check_manifest_identity(tree: AssemblyTree) -> list[Failure]:
    """Each manifest names its own directory and the version on disk."""
    failures = []
    for slug, data in sorted(tree.overlay_files.items()):
        declared = str(data.get("slug") or "")
        if declared != slug:
            failures.append(Failure(
                "manifest-identity", f"manifests/{slug}-posts.json",
                f"declares slug {declared!r}, but it is {slug}'s post "
                f"overlay. One overlay belongs to one project.",
            ))
    for stem, data in sorted(tree.manifest_files.items()):
        slug = str(data.get("slug") or "")
        if slug != stem:
            failures.append(Failure(
                "manifest-identity", f"manifests/{stem}.json",
                f"declares slug {slug!r}, but it is the manifest for "
                f"{stem!r}. One manifest describes one directory.",
            ))
            continue
        version = str(data.get("version") or "")
        if not version:
            continue
        archived = os.path.join(tree.site_dir, slug, "v", version)
        if os.path.isdir(archived):
            failures.append(Failure(
                "manifest-identity", f"site/{slug}/v/{version}",
                f"the current version {version} is also emitted as an "
                f"archive. The current version lives at the stable address; "
                f"only superseded ones sit under v/.",
            ))
        prefix = f"{slug}/"
        for page_rel in tree.pages:
            if not page_rel.startswith(prefix):
                continue
            if page_rel.startswith(f"{slug}/v/"):
                continue
            if page_rel.startswith(f"{slug}/{POSTS_SEGMENT}/"):
                # A post is published between releases, from a working tree
                # the manifest's released version knows nothing about. Its
                # version disagreeing with the manifest's is the normal
                # state, not a stale deploy.
                continue
            found = _VERSION_ATTR_RE.findall(tree.read(page_rel))
            for declared_version in sorted(set(found)):
                if declared_version != version:
                    failures.append(Failure(
                        "manifest-identity", f"site/{page_rel}",
                        f"was built at version {declared_version}, but "
                        f"manifests/{slug}.json says {version}. The manifest "
                        f"and the tree come from different builds.",
                    ))
    return failures


def check_manifest_pages_emitted(tree: AssemblyTree) -> list[Failure]:
    """Every page a manifest lists resolves to an emitted file."""
    failures = []
    for manifest in tree.manifests:
        slug = str(manifest.get("slug") or "")
        for page in manifest.get("pages") or []:
            path = str(page.get("path") or "")
            target = target_output_path(page_target(slug, path))
            if target not in tree.emitted:
                failures.append(Failure(
                    "manifest-pages-emitted", f"{slug}:{path}",
                    f"is listed in the manifest but site/{target} was not "
                    f"emitted, so every listing linking to it is a 404.",
                ))
    return failures


def check_manifest_posts_emitted(tree: AssemblyTree) -> list[Failure]:
    """Every post a manifest lists resolves to an emitted file."""
    failures = []
    for manifest in tree.manifests:
        slug = str(manifest.get("slug") or "")
        for post in manifest.get("posts") or []:
            post_slug = str(post.get("slug") or "")
            target = target_output_path(post_target(slug, post_slug))
            if target not in tree.emitted:
                failures.append(Failure(
                    "manifest-posts-emitted", f"{slug}:{post_slug}",
                    f"is listed in the manifest but site/{target} was not "
                    f"emitted, so the blog index and the feed link to a 404.",
                ))
    return failures


def check_shared_artifacts(tree: AssemblyTree) -> list[Failure]:
    """The cross-project files exist, parse, and are not empty."""
    failures = []

    def _missing(rel, what):
        failures.append(Failure(
            "shared-artifacts", f"site/{rel}",
            f"{what} is missing from the assembled tree.",
        ))

    def _unparsable(rel, exc):
        failures.append(Failure(
            "shared-artifacts", f"site/{rel}", f"does not parse: {exc}",
        ))

    listing = "projects/index.html" if tree.has_portfolio else "index.html"
    required = [
        ("index.html", "the front page"),
        (listing, "the project listing"),
        ("blog/index.html", "the blog index"),
        ("robots.txt", "robots.txt"),
        ("404.html", "the root 404 page"),
    ]
    for rel, what in required:
        if rel not in tree.emitted:
            _missing(rel, what)

    for rel, what in (("sitemap.xml", "the sitemap"), ("feed.xml", "the feed")):
        if rel not in tree.emitted:
            _missing(rel, what)
            continue
        try:
            ET.fromstring(tree.read(rel))
        except ET.ParseError as exc:
            _unparsable(rel, exc)

    if "nav.json" not in tree.emitted:
        _missing("nav.json", "the navigation data")
    else:
        try:
            json.loads(tree.read("nav.json"))
        except json.JSONDecodeError as exc:
            _unparsable("nav.json", exc)

    index_files = [p for p in tree.emitted if p.startswith("pagefind/")]
    if not index_files:
        failures.append(Failure(
            "shared-artifacts", "site/pagefind",
            "the search index is empty or was never built, so the site "
            "answers no searches.",
        ))
    return failures


def check_references(tree: AssemblyTree) -> list[Failure]:
    """Every emitted reference names a file the assembly wrote.

    One LINK001 pass over the assembled tree, reported under three checks:
    a sitemap entry, a feed link and a link on a page are three different
    things to get wrong.
    """
    failures = []
    for lint in check_output_resolution(tree.site_dir, tree.canonical_base):
        where = lint.file or ""
        base = os.path.basename(where)
        if where.endswith(".xml") and "sitemap" in base:
            check = "sitemap-entries"
        elif base == "feed.xml":
            check = "feed-links"
        else:
            check = "internal-references"
        failures.append(Failure(check, f"site/{where}", lint.message))
    return failures


def check_page_metadata(tree: AssemblyTree) -> list[Failure]:
    """Every page has a title and a canonical under the canonical base."""
    failures = []
    for page_rel in tree.pages:
        page_html = tree.read(page_rel)
        title = _TITLE_RE.search(page_html)
        if title is None or not title.group(1).strip():
            failures.append(Failure(
                "page-metadata", f"site/{page_rel}",
                "has no title, so every listing, tab and search result "
                "showing it is blank.",
            ))
        canonicals = [
            match.group(1)
            for tag in _CANONICAL_TAG_RE.findall(page_html)
            for match in [_HREF_RE.search(tag)]
            if match is not None
        ]
        if not canonicals:
            failures.append(Failure(
                "page-metadata", f"site/{page_rel}",
                "declares no rel=canonical. The site is reachable on more "
                "than one host, so every page names which one is canonical.",
            ))
            continue
        if page_rel == "index.html" and tree.has_portfolio:
            # The front page is the portfolio, served at the site apex on a
            # host of its own. Its canonical names that apex deliberately,
            # so it is the one page whose canonical is not under the docs
            # base -- see generate_shared_files' portfolio_canonical.
            continue
        for href in canonicals:
            if site_relative_path(href, tree.canonical_base) is None:
                failures.append(Failure(
                    "page-metadata", f"site/{page_rel}",
                    f"declares the canonical {href}, which is not under the "
                    f"site's canonical base {tree.canonical_base}.",
                ))
    return failures


def check_unresolved_directives(tree: AssemblyTree) -> list[Failure]:
    """No page carries a directive the build did not resolve.

    Code and preformatted blocks are excluded: the documentation of the
    directive syntax quotes every marker there is, and quoting one is not
    leaving one behind.
    """
    failures = []
    for page_rel in tree.pages:
        prose = _CODE_BLOCK_RE.sub(" ", tree.read(page_rel))
        for match in _STUB_MARKER_RE.findall(prose):
            failures.append(Failure(
                "unresolved-directives", f"site/{page_rel}",
                f"carries an unresolved directive: {match}",
            ))
        for match in _RAW_MARKER_RE.findall(prose):
            failures.append(Failure(
                "unresolved-directives", f"site/{page_rel}",
                f"carries a raw directive marker {match!r} outside a code "
                f"block, so the directive was never parsed.",
            ))
    return failures


def check_routing_artifacts(tree: AssemblyTree) -> list[Failure]:
    """No per-project routing file survived the graft.

    The assembly serves one set of headers and one worker for the whole
    site.  A project's own copies -- and the pre-compressed variants its
    build emits for its own hosting -- fight them wherever they sit, so
    the graft filters them out and this is that filter, asserted.
    """
    failures = []
    for rel in sorted(tree.emitted):
        name = os.path.basename(rel)
        at_root = "/" not in rel
        if at_root and name in SHARED_ROUTING_FILES:
            continue
        if name in ROUTING_ARTIFACT_NAMES or name.endswith(ROUTING_ARTIFACT_SUFFIXES):
            failures.append(Failure(
                "routing-artifacts", f"site/{rel}",
                "is a per-project deploy artifact. The assembly serves one "
                "set of routing files for the whole site.",
            ))
    return failures


def extract_link_registry(tree: AssemblyTree) -> dict[str, list[str]]:
    """Map each emitted page to the other projects' addresses it links to.

    This is the half :func:`validate_cross_project_links` was written
    against and never had: the function knows what every project publishes,
    but nothing produced the registry of what the pages actually link to.
    A reference is resolved against the emitted tree, turned back into the
    address form the manifests speak, and kept only when it leaves the
    project the page belongs to -- a link inside one project is the
    LINK001 pass's business, not this one's.
    """
    registry: dict[str, list[str]] = {}
    for page_rel in tree.pages:
        source_project = page_rel.split("/", 1)[0] if "/" in page_rel else ""
        targets: list[str] = []
        for _attr, ref in page_references(tree.read(page_rel)):
            if ref.startswith("/"):
                continue
            target = reference_target(page_rel, ref)
            if target is None or target.startswith(".."):
                continue
            target_project = target.split("/", 1)[0] if "/" in target else ""
            if not target_project or target_project == source_project:
                continue
            if target_project not in tree.roster:
                continue
            form = output_path_target(target)
            if form and form not in targets:
                targets.append(form)
        if targets:
            registry[page_rel] = targets
    return registry


def check_cross_project_links(tree: AssemblyTree) -> list[Failure]:
    """Every link into another project names a page that project publishes."""
    registry = extract_link_registry(tree)
    return [
        Failure("cross-project-links", "site", message)
        for message in validate_cross_project_links(tree.manifests, registry)
    ]


# -- outbound links ----------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class OutboundConfig:
    """The declared outbound check: which pages, and for how long.

    Both fields are declared, neither has a default: which pages are worth
    the requests is a judgement about the site, and how long a result is
    trusted is a judgement about how fast its links rot.
    """

    cache_days: int
    paths: tuple[str, ...]


def parse_outbound(text: str, *, source: str = OUTBOUND_PATH) -> OutboundConfig:
    """Return the outbound declaration in *text*.

    Strict in every direction: an unknown top-level key, an unknown key on
    a ``[[page]]`` block, a missing or empty ``path``, a repeated path and
    a non-positive ``cache_days`` are each a hard error naming the
    offending declaration.  A file with no ``[[page]]`` block is a hard
    error too -- an empty declaration is not a way of saying "check
    nothing", it is a file somebody forgot to finish.
    """
    import tomllib

    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise RuntimeError(f"{source} is not valid TOML: {exc}") from exc

    unknown = sorted(set(data) - set(OUTBOUND_KEYS))
    if unknown:
        raise RuntimeError(
            f"{source} declares unknown key(s) "
            f"{', '.join(repr(k) for k in unknown)}. It carries "
            f"{', '.join(OUTBOUND_KEYS)} and nothing else."
        )
    if "cache_days" not in data:
        raise RuntimeError(
            f"{source} declares no cache_days. How long an outbound result "
            f"is trusted before the link is fetched again has no default; "
            f"declare it."
        )
    cache_days = data["cache_days"]
    if not isinstance(cache_days, int) or isinstance(cache_days, bool) or cache_days < 1:
        raise RuntimeError(
            f"{source}: cache_days must be a whole number of days of at "
            f"least 1, got {cache_days!r}."
        )

    raw = data.get("page", [])
    if not isinstance(raw, list):
        raise RuntimeError(
            f"{source}: 'page' must be a list of [[page]] blocks."
        )
    paths: list[str] = []
    for index, item in enumerate(raw, start=1):
        where = f"{source}: [[page]] #{index}"
        if not isinstance(item, dict):
            raise RuntimeError(f"{where} is not a table.")
        extra = sorted(set(item) - set(OUTBOUND_PAGE_KEYS))
        if extra:
            raise RuntimeError(
                f"{where} declares unknown key(s) "
                f"{', '.join(repr(k) for k in extra)}. A [[page]] block "
                f"carries {', '.join(OUTBOUND_PAGE_KEYS)}."
            )
        path = str(item.get("path") or "")
        if not path:
            raise RuntimeError(
                f"{where} declares no path. Every block names one emitted "
                f"page, relative to site/."
            )
        if path in paths:
            raise RuntimeError(f"{where} repeats the path {path!r}.")
        paths.append(path)

    if not paths:
        raise RuntimeError(
            f"{source} declares no [[page]] block, so it asks for nothing. "
            f"Name the pages whose outbound links are checked, or delete "
            f"the file."
        )
    return OutboundConfig(cache_days=cache_days, paths=tuple(paths))


def load_outbound(assembly_dir: str) -> OutboundConfig | None:
    """Return the outbound declaration, or None when there is no file.

    None is not a default -- it is "this assembly has not configured
    outbound checking", which the report states out loud.
    """
    path = os.path.join(assembly_dir, OUTBOUND_PATH)
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as f:
        return parse_outbound(f.read(), source=path)


def load_outbound_cache(assembly_dir: str) -> dict:
    """Return the outbound result store, keyed by address.

    An absent store is an empty one: nothing has been checked yet.  A
    malformed one is a hard error -- silently starting over would refetch
    every link on every deploy and never say why.
    """
    path = os.path.join(assembly_dir, OUTBOUND_CACHE_PATH)
    if not os.path.isfile(path):
        return {}
    with open(path, encoding="utf-8") as f:
        raw = f.read()
    if not raw.strip():
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{path} is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise RuntimeError(f"{path} must contain a JSON object")
    entries = data.get("entries") or {}
    if not isinstance(entries, dict):
        raise RuntimeError(f"{path}: 'entries' must be a JSON object")
    return {str(url): entry for url, entry in entries.items()}


def render_outbound_cache(entries: dict) -> str:
    """Return the JSON text of an outbound result store."""
    return json.dumps(
        {"schema_version": 1, "entries": entries}, indent=2, sort_keys=True,
    ) + "\n"


def fetch_url(url: str) -> tuple[int, str]:
    """Fetch *url* and return ``(status, error)``.

    The one function here that touches the network, and the one a test
    replaces.  It is a GET: it changes nothing, which is why it does not go
    through the effects handle.
    """
    import urllib.error
    import urllib.request

    request = urllib.request.Request(
        url, method="GET", headers={"User-Agent": "selfblog-assembly-verify"},
    )
    try:
        with urllib.request.urlopen(request, timeout=_OUTBOUND_TIMEOUT) as response:
            return int(response.status), ""
    except urllib.error.HTTPError as exc:
        return int(exc.code), str(exc.reason)
    except Exception as exc:  # noqa: BLE001 -- any transport failure is a dead link
        return 0, str(exc)


def check_outbound_links(
    tree: AssemblyTree,
    config: OutboundConfig,
    cache: dict,
    *,
    fetch,
    now: float,
) -> tuple[list[Failure], dict, int]:
    """Fetch the outbound links on the declared pages; return the results.

    A cached result inside the window answers without a request, so a
    second run over an unchanged tree makes none at all.
    """
    failures: list[Failure] = []
    updated = dict(cache)
    window = config.cache_days * _SECONDS_PER_DAY
    requests = 0

    for rel in config.paths:
        if rel not in tree.emitted:
            failures.append(Failure(
                "outbound-links", f"site/{rel}",
                "is declared in outbound.toml but was not emitted, so its "
                "outbound links are never checked.",
            ))
            continue
        for url in dict.fromkeys(external_references(tree.read(rel))):
            if site_relative_path(url, tree.canonical_base) is not None:
                continue
            entry = updated.get(url)
            fresh = (
                isinstance(entry, dict)
                and isinstance(entry.get("checked"), (int, float))
                and now - entry["checked"] < window
            )
            if not fresh:
                status, error = fetch(url)
                requests += 1
                entry = {
                    "checked": now,
                    "status": status,
                    "ok": 200 <= status < 400,
                    "error": error,
                }
                updated[url] = entry
            if not entry.get("ok"):
                detail = entry.get("error") or ""
                status = entry.get("status")
                failures.append(Failure(
                    "outbound-links", f"site/{rel}",
                    f"links to {url}, which answered "
                    f"{status if status else 'nothing'}"
                    f"{': ' + detail if detail else ''}.",
                ))
    return failures, updated, requests


# -- the run -----------------------------------------------------------------


def verify_assembly(
    assembly_dir: str,
    *,
    canonical_base: str,
    fetch=None,
    now: float | None = None,
) -> VerifyReport:
    """Assert every property the assembled tree has to have before a deploy.

    Args:
        assembly_dir: The assembly repository checkout, holding ``site/``,
            ``manifests/`` and the roster.
        canonical_base: The site's canonical base URL.  Absolute
            references -- canonicals, sitemap entries, feed links -- are
            this site's when they sit under it, and somebody else's when
            they do not, so there is nothing to verify against without it.
        fetch: The outbound fetch layer, ``url -> (status, error)``.
            Defaults to :func:`fetch_url`.
        now: The clock the cache window is measured against.

    Returns:
        A :class:`VerifyReport`.  Verification never writes: the updated
        outbound store rides on the report for the caller to persist.
    """
    if not canonical_base:
        raise ValueError(
            "canonical_base is required: without it nothing can tell this "
            "site's absolute URLs from anybody else's, and half the "
            "assertions would pass by not looking."
        )
    fetch = fetch or fetch_url
    now = time.time() if now is None else now

    tree = read_tree(assembly_dir, canonical_base)
    report = VerifyReport()

    for check, run in (
        ("roster-agreement", check_roster_agreement),
        ("manifest-identity", check_manifest_identity),
        ("manifest-pages-emitted", check_manifest_pages_emitted),
        ("manifest-posts-emitted", check_manifest_posts_emitted),
        ("shared-artifacts", check_shared_artifacts),
        ("page-metadata", check_page_metadata),
        ("unresolved-directives", check_unresolved_directives),
        ("routing-artifacts", check_routing_artifacts),
        ("cross-project-links", check_cross_project_links),
    ):
        report.ran.append(check)
        report.failures.extend(run(tree))

    report.ran.extend(["internal-references", "sitemap-entries", "feed-links"])
    report.failures.extend(check_references(tree))

    config = load_outbound(assembly_dir)
    cache = load_outbound_cache(assembly_dir)
    report.outbound_cache = cache
    if config is None:
        report.skipped.append((
            "outbound-links",
            f"no {OUTBOUND_PATH} in {assembly_dir}: outbound link checking "
            f"is not configured for this assembly, so nothing about the "
            f"site's external links was verified. Declare the pages to "
            f"check to turn it on.",
        ))
    else:
        report.ran.append("outbound-links")
        failures, updated, requests = check_outbound_links(
            tree, config, cache, fetch=fetch, now=now,
        )
        report.failures.extend(failures)
        report.outbound_cache = updated
        report.requests = requests

    report.failures.sort(key=lambda f: (CHECKS.index(f.check), f.offender))
    return report
