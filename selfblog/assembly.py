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

from selfdoc_core import effects

# Files a per-project selfdoc build emits for its own standalone hosting.
# They are meaningless (and actively harmful) once the build is grafted into
# the assembly tree, which serves one set of headers, redirects and worker
# for the whole site.
DEPLOY_ARTIFACT_NAMES = ("_headers", "_redirects", "_worker.js")
DEPLOY_ARTIFACT_SUFFIXES = (".gz", ".br")

# Scopes a dispatch may carry. "" from a client payload that omits the key
# means a full project build; the workflow always passes the flag.
INTEGRATE_SCOPES = ("full", "posts", "shared-only")

# The one path in the assembly repo that holds the generated deploy workflow.
WORKFLOW_PATH = ".github/workflows/deploy.yml"

_BUILD_TIMEOUT = 1800
_GIT_TIMEOUT = 300
_INDEX_TIMEOUT = 900


def generate_workflow_yaml(
    pages_project: str,
    canonical_base: str,
    legacy_blog_host: str,
    portfolio_canonical: str,
    selfblog_version: str = "",
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
    portfolio_canonical: absolute canonical URL of the portfolio page,
        from ``assembly.portfolio_canonical``.  Empty when the assembly
        has no portfolio -- the generated step hard-errors if a portfolio
        file turns up without it.
    selfblog_version: the selfblog version the generated workflow pins
        its toolchain install to.  Empty means the version of the
        selfblog doing the generating.

        The pin is not the banned kind: it is not a ceiling a human wrote
        once and forgot.  ``assembly sync-workflow`` rewrites this file on
        every release, so the deployed workflow always names the selfblog
        that generated it -- a lockfile, regenerated, not an upper bound.
        Without it the workflow installs whatever is newest at dispatch
        time, which is how a released flag change once broke every
        project's deploy at once.
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
    canonical_base = canonical_base.rstrip("/")
    if not selfblog_version:
        from selfblog import __version__ as selfblog_version
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
        run: pip install selfdoc 'selfblog==@@SELFBLOG_VERSION@@' 'pagefind[bin]'

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
          --portfolio-canonical '@@PORTFOLIO_CANONICAL@@'

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
        "@@PORTFOLIO_CANONICAL@@", portfolio_canonical,
    ).replace(
        "@@SELFBLOG_VERSION@@", selfblog_version,
    )


def assembly_init(
    repo_name: str,
    pages_project: str,
    canonical_base: str,
    legacy_blog_host: str,
    portfolio_canonical: str,
    selfblog_version: str = "",
) -> dict[str, str]:
    """Return a dict mapping filename to file content for a new assembly repo.

    repo_name: e.g. "smm-h/docs-assembly"
    pages_project: Cloudflare Pages project the workflow deploys to.
    canonical_base: absolute canonical base URL of the assembly site.
    legacy_blog_host: retired blog subdomain, or "" when none exists.
    portfolio_canonical: absolute canonical URL of the portfolio page,
        or "" when the assembly has no portfolio.
    selfblog_version: selfblog version the generated workflow pins its
        toolchain to; empty means the running selfblog's version.
    """
    return {
        WORKFLOW_PATH: generate_workflow_yaml(
            pages_project, canonical_base, legacy_blog_host,
            portfolio_canonical, selfblog_version,
        ),
        ".gitignore": _gitignore_content(),
        "projects.json": json.dumps({}, indent=2) + "\n",
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


def assembly_rebuild(
    repo: str,
    projects: dict[str, dict],
) -> list[dict]:
    """Return dispatch payloads for rebuilding all projects.

    repo: the assembly repo identifier
    projects: mapping of slug to project info (must have "repo" and "ref" keys)
    """
    return [
        assembly_push(
            assembly_repo=repo,
            source_repo=info["repo"],
            slug=slug,
            version=info.get("version", "latest"),
            ref=info["ref"],
        )
        for slug, info in projects.items()
    ]


def generate_redirects_file(slug: str, docs_base: str) -> str:
    """Return the content of a Cloudflare Pages _redirects file.

    Redirects all paths from the old per-project CF Pages site to the
    assembly site under the project's slug prefix.

    slug: project's URL path segment (e.g. "selfdoc")
    docs_base: base URL of the assembly site (e.g. "https://docs.smmh.dev")
    """
    docs_base = docs_base.rstrip("/")
    return f"/* {docs_base}/{slug}/:splat 301\n"


def generate_worker_js(canonical_base: str, legacy_blog_host: str) -> str:
    """Return the Cloudflare Pages ``_worker.js`` for the assembly site.

    The worker consolidates every non-canonical way of reaching the blog
    onto a single canonical origin with one 301 hop:

    * requests to the legacy blog subdomain become
      ``<canonical_base>/blog<path>``;
    * requests for ``/blog`` (or anything below it) that arrive on a host
      other than the canonical host become ``<canonical_base><path>``.

    canonical_base: absolute base URL of the assembly site, taken from
        ``topology.docs_base`` (e.g. "https://docs.smmh.dev").  Required --
        there is no default deploy target.
    legacy_blog_host: hostname of the retired blog subdomain, taken from
        ``topology.legacy_blog_host`` (e.g. "blog.smmh.dev").  An empty
        string means no legacy subdomain exists and the rule is omitted.
    """
    if not canonical_base:
        raise ValueError(
            "generate_worker_js requires a canonical base URL "
            "(topology.docs_base); there is no default."
        )
    canonical_base = canonical_base.rstrip("/")

    legacy_rule = ""
    if legacy_blog_host:
        legacy_rule = (
            "    // Retired blog subdomain: one hop onto the canonical blog URL.\n"
            f"    if (url.hostname === {json.dumps(legacy_blog_host)}) {{\n"
            "      return Response.redirect(\n"
            "        CANONICAL_BASE + \"/blog\" + url.pathname + url.search, 301);\n"
            "    }\n"
        )

    return (
        f"const CANONICAL_BASE = {json.dumps(canonical_base)};\n"
        "const CANONICAL_HOST = new URL(CANONICAL_BASE).hostname;\n"
        "\n"
        "export default {\n"
        "  async fetch(request, env) {\n"
        "    const url = new URL(request.url);\n"
        f"{legacy_rule}"
        "    // Any other host serving /blog consolidates onto the canonical host.\n"
        "    if (url.hostname !== CANONICAL_HOST &&\n"
        "        (url.pathname === \"/blog\" || url.pathname.startsWith(\"/blog/\"))) {\n"
        "      return Response.redirect(CANONICAL_BASE + url.pathname + url.search, 301);\n"
        "    }\n"
        "    return env.ASSETS.fetch(request);\n"
        "  }\n"
        "}\n"
    )


def load_assembly_manifests(manifests_dir: str) -> list[dict]:
    """Return the assembly's per-project manifests with post overlays applied.

    ``*-posts.json`` files are overlays written by ``post publish``: they
    carry a fresher post list than the base manifest of the same slug and
    replace its ``posts`` array.  ``*-revisions.json`` sidecars are not
    manifests and are skipped.
    """
    from selfdoc_core.manifest import manifest_compat

    base_manifests: list[dict] = []
    post_overlays: list[dict] = []
    if os.path.isdir(manifests_dir):
        for fname in sorted(os.listdir(manifests_dir)):
            if not fname.endswith(".json"):
                continue
            if fname.endswith("-revisions.json"):
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


def generate_shared_files(
    site_dir: str,
    manifests_dir: str,
    canonical_base: str,
    *,
    docs_base: str = "",
    legacy_blog_host: str = "",
    portfolio_file: str = "",
    portfolio_canonical: str = "",
) -> list[str]:
    """Write the assembly's shared cross-project files and return their paths.

    The 7 files are the project listing (or portfolio + listing when a
    portfolio file is supplied), the blog index, ``nav.json``,
    ``feed.xml``, ``sitemap.xml``, ``_headers`` and ``_worker.js``.

    Raises ValueError when a required input is missing -- the CLI turns
    those into a usage error, the integrate command lets them abort the
    deploy.
    """
    from selfblog.shared import (
        _ensure_canonical,
        generate_blog_index,
        generate_homepage,
        generate_nav_json,
        generate_sitemap,
        generate_unified_feed,
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

    homepage_fragment = generate_homepage(manifests, docs_base)
    blog_fragment = generate_blog_index(manifests, docs_base)
    nav_json = generate_nav_json(manifests)
    feed_xml = generate_unified_feed(manifests, docs_base)
    sitemap_xml = generate_sitemap(manifests, docs_base)

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

    # When a portfolio file is provided, it becomes the root index.html
    # and the project listing moves to /projects/index.html
    if portfolio_file and os.path.isfile(portfolio_file):
        if not portfolio_canonical:
            raise ValueError(
                "portfolio_canonical is required when a portfolio file is "
                "supplied (set assembly.portfolio_canonical in selfdoc.json "
                "and regenerate the assembly workflow). The portfolio is the "
                "site apex, not a docs page, so it has no default canonical."
            )
        with open(portfolio_file, "r", encoding="utf-8") as f:
            portfolio_html = f.read()
        try:
            portfolio_html = _ensure_canonical(portfolio_html, portfolio_canonical)
        except ValueError as exc:
            raise ValueError(f"{portfolio_file}: {exc}") from exc
        index_path = os.path.join(site_dir, "index.html")
        effects.makedirs(os.path.dirname(index_path) or site_dir, exist_ok=True)
        atomic_write(index_path, portfolio_html)
        written.append(index_path)

        projects_dir = os.path.join(site_dir, "projects")
        effects.makedirs(projects_dir, exist_ok=True)
        projects_path = os.path.join(projects_dir, "index.html")
        atomic_write(projects_path, wrap_shared_page(
            "Projects", homepage_fragment,
            canonical_url=f"{canonical_base}/projects/",
        ))
        written.append(projects_path)
    else:
        index_path = os.path.join(site_dir, "index.html")
        effects.makedirs(os.path.dirname(index_path) or site_dir, exist_ok=True)
        atomic_write(index_path, wrap_shared_page(
            "Projects", homepage_fragment,
            canonical_url=f"{canonical_base}/",
        ))
        written.append(index_path)

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

    headers_path = os.path.join(site_dir, "_headers")
    atomic_write(headers_path, headers_content)
    written.append(headers_path)

    worker_js_path = os.path.join(site_dir, "_worker.js")
    atomic_write(worker_js_path, generate_worker_js(canonical_base, legacy_blog_host))
    written.append(worker_js_path)

    return written


# -- integrate: the deploy body the generated workflow used to embed ---------


def detect_latest_version(source_dir: str) -> str:
    """Return the newest version declared by a source project's config.

    Empty when the project declares no versions at all (a single implicit
    version, which ``selfdoc build`` handles without ``--version``).  A
    multi-version project whose newest entry carries no version string is
    a hard error: building it unversioned would silently publish the
    wrong docs.
    """
    cfg_path = os.path.join(source_dir, "selfdoc.json")
    if not os.path.isfile(cfg_path):
        return ""
    with open(cfg_path, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    versions = cfg.get("versions") or []
    if not versions:
        return ""
    latest = str(versions[-1].get("version") or "")
    if not latest and len(versions) > 1:
        raise RuntimeError(
            f"Could not detect latest version for multi-version project "
            f"at {source_dir}"
        )
    return latest


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


def replace_subtree(dest: str, src: str) -> None:
    """Replace the *dest* directory with a copy of *src*.

    The replacement is total: a page deleted upstream disappears here,
    which an overlay copy would not achieve.  A missing *src* leaves an
    empty *dest* -- the build produced nothing for this subtree.
    """
    if os.path.isdir(dest):
        effects.rmtree(dest)
    effects.makedirs(dest, exist_ok=True)
    if os.path.isdir(src):
        effects.copytree(src, dest, dirs_exist_ok=True)


def update_projects_json(path: str, slug: str, repo: str, ref: str,
                         version: str) -> dict:
    """Record *slug*'s membership in the assembly and return the new mapping.

    A malformed ``projects.json`` is a hard error rather than a fresh
    empty mapping: rewriting it would silently drop every other project's
    membership record.
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
    data[slug] = {"repo": repo, "ref": ref, "version": version}
    effects.write_text(path, json.dumps(data, indent=2, sort_keys=True) + "\n")
    return data


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


def build_source_project(source_dir: str, scope: str) -> list[str]:
    """Build the cloned source project and return the argv that was run."""
    if scope == "posts":
        argv = ["selfblog", "build", "--target", "posts", "--no-auto-commit"]
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
                        scope: str) -> list[str]:
    """Graft a built project into the assembly tree; return changed paths."""
    site_slug_dir = os.path.join(assembly_dir, "site", slug)
    manifests_dir = os.path.join(assembly_dir, "manifests")
    effects.makedirs(manifests_dir, exist_ok=True)
    touched: list[str] = []

    if scope == "posts":
        # Posts-only: only the posts subtree is authoritative here; the
        # rest of the project's pages stay as the last full build left them.
        posts_dest = os.path.join(site_slug_dir, "posts")
        replace_subtree(posts_dest, os.path.join(source_dir, "docs", "_build", "posts"))
        prune_deploy_artifacts(posts_dest)
        touched.append(posts_dest)
        src_manifest = os.path.join(source_dir, ".selfdoc", "post-manifest.json")
        dest_manifest = os.path.join(manifests_dir, f"{slug}-posts.json")
        if os.path.isfile(src_manifest):
            effects.copy_file(src_manifest, dest_manifest)
            touched.append(dest_manifest)
        return touched

    # Full build: the project subtree is replaced wholesale.
    replace_subtree(site_slug_dir, os.path.join(source_dir, "docs", "_build"))
    prune_deploy_artifacts(site_slug_dir)
    touched.append(site_slug_dir)
    src_manifest = os.path.join(source_dir, ".selfdoc", "manifest.json")
    dest_manifest = os.path.join(manifests_dir, f"{slug}.json")
    if os.path.isfile(src_manifest):
        effects.copy_file(src_manifest, dest_manifest)
        touched.append(dest_manifest)
    # The full build carries its own posts, so a stale posts overlay would
    # re-apply an older post list on top of it.
    overlay = os.path.join(manifests_dir, f"{slug}-posts.json")
    if os.path.isfile(overlay):
        effects.remove(overlay)
        touched.append(overlay)
    return touched


def index_site(site_dir: str) -> None:
    """Build the pagefind search index over the assembled site."""
    _run_step(
        [sys.executable, "-m", "pagefind", "--site", site_dir],
        cwd=None, step="pagefind index", timeout=_INDEX_TIMEOUT,
        resource=f"search-index:{site_dir}",
    )


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
    portfolio_canonical: str = "",
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
    projects_json = os.path.join(assembly_dir, "projects.json")
    portfolio_file = os.path.join(assembly_dir, "portfolio", "index.html")

    summary = {
        "scope": scope,
        "slug": slug,
        "version": version,
        "touched": [],
        "shared": [],
        "attempt": 0,
        "committed": False,
    }

    if scope != "shared-only" and build:
        build_source_project(source_dir, scope)

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
        if scope != "shared-only":
            summary["touched"] = apply_project_files(
                assembly_dir, source_dir, slug, scope,
            )
            update_projects_json(projects_json, slug, source_repo, ref, version)

        summary["shared"] = generate_shared_files(
            site_dir, manifests_dir, canonical_base,
            legacy_blog_host=legacy_blog_host,
            portfolio_file=portfolio_file if os.path.isfile(portfolio_file) else "",
            portfolio_canonical=portfolio_canonical,
        )

        index_site(site_dir)

        _run_step(["git", "add", "site", "manifests", "projects.json"],
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
    """Raise when *version* is absent from the project's declared versions.

    The assembly builds ``versions[-1]``, so a ``versions`` array that has
    not kept up with the released version publishes docs for whatever
    stale version it does list -- silently, and for as long as nobody
    compares the two.
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
    if version not in declared:
        raise RuntimeError(
            f"version {version} is not in selfdoc.json's 'versions' "
            f"({', '.join(declared)}). The assembly builds the newest "
            f"declared version, so this dispatch would publish "
            f"{declared[-1]} under the name {version}."
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
