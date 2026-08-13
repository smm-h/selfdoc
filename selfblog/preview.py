"""The whole assembly, built from local checkouts and served on loopback.

``selfblog assembly preview`` is the look-before-you-ship step: it does
everything a deploy does to produce the tree, stops short of everything a
deploy does to publish it, and then serves the result so a person can look
at it.

The point of the command is that it looks at the *real* tree.  Every step
below is the production function the deploy itself calls -- the same build,
the same :func:`~selfblog.assembly.split_build_output` graft, the same
:func:`~selfblog.assembly.generate_shared_files` (chrome asset included),
the same :func:`~selfblog.verify.verify_assembly`.  A preview that rendered
through a second implementation would be a picture of something that is not
going to be published, which is worse than no preview at all.

What the deploy does that a preview cannot are the remote-coupled steps: it
clones from tags, it pushes manifests and membership records to the assembly
repository, and it deploys.  Those have local equivalents here, built from
the same functions' outputs into the preview tree -- a roster rendered by
:func:`~selfblog.assembly.render_roster` from the checkouts named on the
command line, a ``projects.json`` written by
:func:`~selfblog.assembly.record_membership`, manifests copied by the graft.
The tree the preview serves is therefore an assembly checkout in every
respect verification can see, which is why verification runs against it
unchanged.

Verification **reports, it does not block**.  A deploy refuses to publish a
tree that fails; a preview exists precisely to be looked at when something
is wrong, so the report is printed first and loudly and the server starts
either way.

The output directory is refused when it sits inside a git working tree at a
path that is not ignored.  A build tree dropped into a checkout pollutes
``git status`` for every other session sharing it, and a few thousand
generated files are exactly the kind of thing that gets committed by
accident.
"""

from __future__ import annotations

import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlsplit

from selfblog.serving import HOST, content_type, resolve_under

__all__ = [
    "PreviewHandler",
    "enclosing_worktree",
    "make_preview_server",
    "out_dir_refusal",
    "preview_assembly",
    "read_slug",
    "refuse_unsafe_out_dir",
    "serve_preview",
]

#: How long the one git query this module makes is given.
_CHECK_IGNORE_TIMEOUT = 15

#: The page served for an address the tree does not carry, when the tree
#: does not carry a 404 page either.  The assembly always writes one, so
#: this is the shape of a preview of a tree that was never generated.
_BARE_NOT_FOUND = (
    "<!DOCTYPE html>\n<html lang=\"en\"><head><title>404</title></head>"
    "<body><h1>404</h1><p>This preview tree carries no 404.html.</p>"
    "</body></html>\n"
)


# -- where a preview may be written -------------------------------------------


def enclosing_worktree(path: str) -> str:
    """Return the git working tree *path* sits in, or "" when it sits in none.

    The nearest ancestor carrying ``.git`` wins, and *path* itself counts.
    ``.git`` is tested for existence rather than for being a directory, so a
    linked worktree (where it is a file) is found too.
    """
    current = os.path.abspath(path)
    while True:
        if os.path.exists(os.path.join(current, ".git")):
            return current
        parent = os.path.dirname(current)
        if parent == current:
            return ""
        current = parent


def out_dir_refusal(out_dir: str) -> str:
    """Return why *out_dir* may not be written to, or "" when it may.

    A directory outside every git working tree is always fine.  Inside one,
    the only acceptable location is a path git ignores: a preview writes
    thousands of generated files, and a checkout that another session shares
    must not grow them as untracked noise.
    """
    out_dir = os.path.abspath(out_dir)
    repo = enclosing_worktree(out_dir)
    if not repo:
        return ""
    rel = os.path.relpath(out_dir, repo)
    if rel == os.curdir:
        return (
            f"{out_dir} is the root of the git working tree at {repo}. A "
            f"preview writes a whole generated site; it cannot be written "
            f"over a checkout. Choose a directory outside any repository, "
            f"or a gitignored path inside one."
        )
    # The trailing slash is not cosmetic: git decides whether a
    # directory-only pattern like ``preview/`` applies by looking at the
    # path's type, and a path that does not exist yet -- the normal state of
    # an output directory -- is taken for a file without it. The output
    # directory is a directory by definition, so it is asked about as one.
    from selfdoc_core import effects

    ignored = effects.run(
        ["git", "-C", repo, "check-ignore", "-q", "--", f"{rel}/"],
        capture_output=True, text=True, timeout=_CHECK_IGNORE_TIMEOUT,
        check=False, read=True,
    )
    if ignored.returncode == 0:
        return ""
    return (
        f"{out_dir} is inside the git working tree at {repo} and git does "
        f"not ignore it. A preview writes thousands of generated files, "
        f"which would appear as untracked noise in every `git status` run "
        f"in that checkout -- including other sessions' -- and can be "
        f"committed by accident. Either choose a directory outside any "
        f"repository, or add {rel!r} to that repository's .gitignore first."
    )


def refuse_unsafe_out_dir(out_dir: str) -> None:
    """Raise when *out_dir* is not a place a preview may be written."""
    reason = out_dir_refusal(out_dir)
    if reason:
        raise RuntimeError(reason)


# -- what a checkout says about itself ----------------------------------------


def read_slug(source_dir: str) -> str:
    """Return the assembly slug the project at *source_dir* declares."""
    from selfdoc_core.config import load_config

    config = load_config(source_dir)
    if config is None:
        raise RuntimeError(
            f"{source_dir} carries no selfdoc.json, so it is not a project "
            f"the assembly can serve."
        )
    slug = str((config.get("topology") or {}).get("slug") or "").strip()
    if not slug:
        raise RuntimeError(
            f"{source_dir}/selfdoc.json declares no topology.slug, so there "
            f"is no address to publish it at. The slug is the project's path "
            f"segment on the assembled site."
        )
    return slug


# -- the pipeline --------------------------------------------------------------


def expected_stylesheet(theme: str) -> str:
    """The stylesheet ``selfdoc build`` writes for *theme*, byte for byte.

    Recomputed the same way the build computes it -- the theme's CSS, the
    Pygments rules its metadata names, minified together -- so a
    comparison against a build's ``style.css`` is an equality rather than
    a resemblance.  It is deliberately sensitive to the theme file
    changing after a build: a page rendered against an older version of
    the theme is exactly the thing the caller wants to be told about.
    """
    from selfdoc_core.build import _minify_css
    from selfdoc_core.html import generate_pygments_css, get_css
    from selfdoc_core.themes import get_theme_meta

    meta = get_theme_meta(theme)
    css = get_css(theme)
    pygments = generate_pygments_css(
        light_style=meta.get("pygments_light", "default"),
        dark_style=meta.get("pygments_dark", "monokai"),
    )
    if pygments:
        css = css + "\n\n/* Pygments syntax highlighting */\n" + pygments
    return _minify_css(css)


def built_under_theme(source_dir: str, theme: str) -> bool:
    """Whether *source_dir*'s existing build output was made with *theme*.

    False for a checkout with no build output at all: nothing to graft is
    not the same claim as grafting something styled correctly, and the
    graft will fail on its own terms a moment later anyway.
    """
    from selfdoc_core.themes import theme_css_rel

    path = os.path.join(
        source_dir, "docs", "_build", *theme_css_rel(theme).split("/"),
    )
    if not os.path.isfile(path):
        return False
    with open(path, encoding="utf-8") as handle:
        return handle.read() == expected_stylesheet(theme)


def preview_assembly(
    *,
    home_dir: str,
    project_dirs,
    out_dir: str,
    canonical_base: str,
    legacy_blog_host: str = "",
    build: bool = True,
    theme: str = "",
) -> dict:
    """Assemble every named checkout into *out_dir* and verify the result.

    Args:
        home_dir: The checkout of the home project -- the one served at the
            site root.  Required: a site needs a front page.
        project_dirs: Checkouts of the other projects, each served under its
            own declared slug.  May be empty.
        out_dir: Where the preview tree is written.  Refused when it sits
            un-ignored inside a git working tree; see :func:`out_dir_refusal`.
        canonical_base: The site's canonical base URL.  This is the *deployed*
            base, not the loopback address the preview is served from: the
            pages carry the canonicals they would ship with, and verification
            asserts against those.
        legacy_blog_host: A retired blog subdomain the generated worker 301s,
            as the deploy passes it.  Empty when there is none.
        build: Whether to run each checkout's build.  False previews whatever
            is already in each checkout's ``docs/_build``, which is what the
            suite does and what a second look after one edit wants.
        theme: A theme name every checkout is built under, overriding each
            project's own configured theme for this preview only.  Empty
            means every project keeps its configured theme, which is what
            a deploy always does.  With ``build`` it reaches each build.
            Without it, the build trees already on disk have to have been
            produced under that theme, and a checkout whose has not is a
            hard error naming it -- see :func:`built_under_theme`.

    Returns:
        A summary: ``out_dir``, ``site_dir``, ``home``, ``slugs``, ``shared``
        (the shared files written) and ``report`` (the
        :class:`~selfblog.verify.VerifyReport`, whose failures are reported
        rather than raised -- see the module docstring).
    """
    from selfblog.assembly import (
        PROJECTS_PATH,
        ROSTER_PATH,
        RosterEntry,
        apply_project_files,
        build_source_project,
        detect_latest_version,
        generate_shared_files,
        index_site,
        parse_roster,
        reconcile_membership,
        record_membership,
        render_roster,
    )
    from selfblog.verify import verify_assembly
    from selfdoc_core import effects

    if not canonical_base:
        raise ValueError(
            "canonical_base is required: it is the base every page's "
            "canonical and every sitemap entry is written against, and the "
            "preview asserts the deployed addresses, not the loopback ones."
        )
    if theme:
        from selfdoc_core.themes import list_themes

        known = list_themes()
        if theme not in known:
            raise ValueError(
                f"unknown theme {theme!r}; available themes: "
                f"{', '.join(known)}"
            )
    refuse_unsafe_out_dir(out_dir)

    out_dir = os.path.abspath(out_dir)
    site_dir = os.path.join(out_dir, "site")
    manifests_dir = os.path.join(out_dir, "manifests")

    home_dir = os.path.abspath(home_dir)
    home_slug = read_slug(home_dir)
    checkouts = {home_slug: home_dir}
    # The home project builds LAST: its front page renders every other
    # project's live version out of the manifests beside it, so the others
    # have to be grafted before it is built.
    ordered: list[tuple[str, str, bool]] = []
    for raw in project_dirs:
        source_dir = os.path.abspath(raw)
        slug = read_slug(source_dir)
        if slug in checkouts:
            raise RuntimeError(
                f"two checkouts declare the slug {slug!r}: {checkouts[slug]} "
                f"and {source_dir}. One slug is one project's section of the "
                f"site, so the preview cannot serve both."
            )
        checkouts[slug] = source_dir
        ordered.append((slug, source_dir, False))
    ordered.append((home_slug, home_dir, True))

    # A theme reaches a page twice: the build inlines its critical part
    # into the page's own head, and the page then references the site's
    # chrome asset for the rest.  With --build both come from *theme*.
    # With --no-build only the second one can, so the first has to be
    # checked rather than assumed -- otherwise the preview would serve
    # one theme's pages against another theme's stylesheet and look like
    # a rendering bug.  The check is an equality, not a guess: it
    # recomputes the stylesheet the build writes and compares.
    if theme and not build:
        stale = [
            slug for slug, source_dir in sorted(checkouts.items())
            if not built_under_theme(source_dir, theme)
        ]
        if stale:
            raise RuntimeError(
                "--no-build was given with --theme "
                f"{theme!r}, but the build tree of "
                f"{', '.join(stale)} was not produced under that theme "
                f"(or under the theme as it stands now). Their pages carry "
                f"another theme's inlined styles, so serving them against "
                f"{theme}'s stylesheet would look like a rendering fault "
                f"rather than the theme. Rebuild those checkouts under "
                f"--theme {theme}, or run the preview with --build."
            )

    effects.makedirs(manifests_dir, exist_ok=True)
    effects.makedirs(site_dir, exist_ok=True)

    # The roster is the assembly's declaration of membership, and a preview
    # declares exactly the checkouts it was given.  The repository field is
    # what a deploy checks a dispatch's origin against, which a preview has
    # no dispatch to check, so it records where the content actually came
    # from: this machine.
    roster_path = os.path.join(out_dir, ROSTER_PATH)
    roster_text = render_roster(
        [RosterEntry(slug, f"local/{slug}") for slug in checkouts],
        home=home_slug,
    )
    effects.write_text(roster_path, roster_text)
    roster = parse_roster(roster_text, source=roster_path)

    # Reconcile first, so a rerun with a project dropped from the command
    # line loses that project's subtree, manifests and record instead of
    # serving a stale copy of it.
    reconcile_membership(out_dir, roster)

    projects_json = os.path.join(out_dir, PROJECTS_PATH)
    for slug, source_dir, is_home in ordered:
        if build:
            build_source_project(
                source_dir, "full", home=is_home,
                manifests_dir=manifests_dir, theme=theme,
            )
        apply_project_files(out_dir, source_dir, slug, "full", home=is_home)
        record_membership(
            projects_json, roster, slug, "", "local",
            detect_latest_version(source_dir),
        )

    shared = generate_shared_files(
        site_dir, manifests_dir, canonical_base,
        docs_base=canonical_base,
        legacy_blog_host=legacy_blog_host,
        home_slug=home_slug,
        theme=theme,
    )
    index_site(site_dir)

    report = verify_assembly(out_dir, canonical_base=canonical_base)
    return {
        "out_dir": out_dir,
        "site_dir": site_dir,
        "home": home_slug,
        "slugs": sorted(checkouts),
        "shared": shared,
        "report": report,
    }


def render_report(report, *, out_dir: str) -> str:
    """Return the verification report as the preview prints it.

    Loud, and first: a preview that quietly served a broken tree would be
    exactly the failure the command exists to prevent.
    """
    from selfblog.verify import CHECKS

    rule = "=" * 72
    lines = [rule, f"verify: {out_dir}"]
    lines.append(
        f"  {len(report.ran)} of {len(CHECKS)} check(s) ran, "
        f"{len(report.failures)} problem(s) found."
    )
    for check, reason in report.skipped:
        lines.append(f"  NOT CHECKED: {check} -- {reason}")
    if report.ok:
        lines.append("  Every check that ran passed.")
    else:
        lines.append("")
        lines.append(report.error_text())
        lines.append("")
        lines.append(
            "  The preview serves this tree anyway -- looking at a tree that "
            "is not right yet is what a preview is for. A deploy would "
            "refuse it."
        )
    lines.append(rule)
    return "\n".join(lines)


# -- the server ----------------------------------------------------------------


class PreviewHandler(BaseHTTPRequestHandler):
    """One request against the preview tree.  ``root`` is set on a subclass.

    What it imitates about a static host is exactly what changes whether a
    page looks right: a directory address serves that directory's
    ``index.html``, an address missing its trailing slash is redirected to
    the one that has it, everything is served under its real content type,
    and an address the tree does not carry answers with the tree's own
    ``404.html`` **and a 404 status**.  A 404 page served as 200 is how a
    broken link survives a preview.
    """

    root: str = ""
    server_version = "selfblog-preview"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):  # noqa: A002 - stdlib signature
        """One compact line per request, so a preview says what it served."""
        sys.stderr.write(f"{self.command} {self.path} {fmt % args}\n")

    # -- plumbing ------------------------------------------------------------

    def _send(self, status, payload, ctype, *, body=True):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(payload)))
        # A preview is looked at while it is being rebuilt underneath.
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if body:
            self.wfile.write(payload)

    def _redirect(self, location):
        self.send_response(301)
        self.send_header("Location", location)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _not_found(self, *, body=True):
        page = os.path.join(self.root, "404.html")
        if os.path.isfile(page):
            with open(page, "rb") as handle:
                payload = handle.read()
        else:
            payload = _BARE_NOT_FOUND.encode("utf-8")
        self._send(404, payload, "text/html; charset=utf-8", body=body)

    # -- dispatch ------------------------------------------------------------

    def do_GET(self):  # noqa: N802 - stdlib signature
        self._respond(body=True)

    def do_HEAD(self):  # noqa: N802 - stdlib signature
        self._respond(body=False)

    def _respond(self, *, body):
        path = unquote(urlsplit(self.path).path)
        target = resolve_under(self.root, path.lstrip("/"))
        if target is None:
            self._not_found(body=body)
            return
        if os.path.isdir(target):
            if not path.endswith("/"):
                self._redirect(path + "/")
                return
            target = os.path.join(target, "index.html")
        if not os.path.isfile(target):
            self._not_found(body=body)
            return
        with open(target, "rb") as handle:
            payload = handle.read()
        self._send(200, payload, content_type(target), body=body)


def make_preview_server(root: str, port: int):
    """Bind a preview server for *root* to loopback on *port*.

    ``port`` 0 binds an ephemeral port, which is what the suite uses; the
    command itself requires an explicit one.
    """

    class BoundHandler(PreviewHandler):
        pass

    BoundHandler.root = os.path.abspath(root)
    server = ThreadingHTTPServer((HOST, port), BoundHandler)
    server.daemon_threads = True
    return server


def serve_preview(root: str, port: int, on_ready=None) -> int:
    """Serve *root* until interrupted, then close the listening socket."""
    server = make_preview_server(root, port)
    if on_ready is not None:
        on_ready(server.server_port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0
