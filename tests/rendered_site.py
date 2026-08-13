"""The fixture assembly the rendered-reality suite looks at, built for real.

This module writes source checkouts to disk and hands them to
:func:`selfblog.preview.preview_assembly` -- the production pipeline, not a
stand-in for it.  Everything the suite asserts against is therefore a page a
deploy would publish: the same ``selfdoc build`` / ``selfblog build``, the
same :func:`~selfblog.assembly.split_build_output` graft, the same
:func:`~selfblog.assembly.generate_shared_files` (chrome asset included),
the same real Pagefind index over the assembled tree.

The checkouts are small but they are not thin: between them they carry
every page class the site serves -- a home project at the site root with a
CV and posts, a versioned project with an archive under ``v/``, an
unversioned project, a table-heavy page, a page that declares glossary
terms, and the generated shared pages nobody's build wrote.  A page class
missing here is a page class the browser suite cannot see.

See ``test_rendered_reality.py`` for why the pipeline is never mocked.
"""

from __future__ import annotations

import base64
import contextlib
import json
import os
import socket
import subprocess
import sys
import threading
import time

# The site every fixture page canonicalizes against.  It is the *deployed*
# base, not the loopback address the preview is served from -- the pages
# carry the canonicals they would ship with, exactly as a deploy writes them.
CANONICAL_BASE = "https://docs.example.com"

# The one off-site address the fixture *content* names, from a link in
# alpha's index page.  Everything a reader can click that is not on this
# origin and not in EXTERNAL_ALLOWLIST below is a page sending readers off
# the site, which is the defect class the navigation test stands for.
ALLOWED_EXTERNAL = "https://example.org/external-reference"

#: The generator's attribution link, which every page's chrome carries.
GENERATOR_LINK = "https://github.com/smm-h/selfdoc"

AUTHOR = {
    "name": "Test Author",
    "url": "https://author.example",
    "same_as": ["https://github.com/testauthor"],
}

#: Every off-origin address a fixture page may name, and why.  Written out
#: rather than pattern-matched: an allowlist that accepts a shape accepts
#: the next link of that shape too, and the point is that a new external
#: link has to be declared deliberately.
EXTERNAL_ALLOWLIST = {
    ALLOWED_EXTERNAL: "a link in alpha's page content",
    GENERATOR_LINK: "the generator's attribution link in the page chrome",
    AUTHOR["url"]: "the author the fixture declares",
    AUTHOR["same_as"][0]: "the author's declared profile, and the CV's",
}

LOCALES = [{"code": "en", "label": "English", "default": True}]

# A 2x2 opaque PNG.  The CV test asserts the portrait decodes to a non-zero
# natural size, which a zero-byte placeholder would not.
_PNG_2X2 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAAFklEQVR4nGP8z4AAT"
    "AwMDAwMDAwMDAwMAA8mAgHRvGYYAAAAAElFTkSuQmCC"
)


# -- writing a checkout --------------------------------------------------------


def _write(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)


def _write_json(path: str, data) -> None:
    _write(path, json.dumps(data, indent=2))


def _git(args, cwd) -> None:
    """Run git in *cwd*.

    No identity is injected: stricttest's isolation floor owns the git
    identity and the throwaway global config for the whole session.
    """
    subprocess.run(
        ["git", *args], cwd=str(cwd), check=True, capture_output=True,
    )


def _config(slug: str, name: str, **overrides) -> dict:
    """A project config.

    ``source`` is deliberately absent from the base: a project that
    declares source code is refused an ``unversioned: true`` declaration
    (code is what gets released, so it carries a version), and two of the
    three fixture checkouts are codeless on purpose.
    """
    config = {
        "name": name,
        "description": f"{name}, a fixture project.",
        "docs": "docs/",
        "output": "docs/_build/",
        "base_url": f"{CANONICAL_BASE}/{slug}",
        "search_engine": "pagefind",
        "author": dict(AUTHOR),
        "locales": list(LOCALES),
        "topology": {"slug": slug, "docs_base": CANONICAL_BASE},
    }
    config.update(overrides)
    return config


def _src(root: str, name: str) -> None:
    """The one source file a versioned project's config points at."""
    _write(
        os.path.join(root, "src", "__init__.py"),
        f'"""The {name} package."""\n\n\n'
        f"def greet(who):\n"
        f'    """Return a greeting for *who*."""\n'
        f'    return f"hello {{who}}"\n',
    )


def _write_manifest(root: str) -> None:
    """Write the checkout's ``.selfdoc/manifest.json``, the way ``gen`` does.

    A real checkout carries a committed manifest: ``selfdoc gen`` writes it
    during a release, and the assembly reads it for the version badge, the
    project listing, the unified feed and the sitemap.  A fixture without
    one assembles into a site whose shared pages know about no projects at
    all, so this runs the production generator over the production
    resolution of the checkout's own docs -- not a hand-written manifest,
    which would be exactly the sort of stand-in this suite refuses.
    """
    from selfdoc.docs import resolve_all_docs
    from selfdoc_core import require_post_provider
    from selfdoc_core.config import load_config
    from selfdoc_core.manifest import generate_manifest

    config = load_config(root)
    all_docs = resolve_all_docs(config, base_dir=root)
    posts_rel = (config.get("posts") or {}).get("dir", ".selfdoc/posts/")
    posts_dir = os.path.join(root, posts_rel)
    posts = (
        require_post_provider()(posts_dir) if os.path.isdir(posts_dir) else []
    )
    posts_data = [
        {key: post[key] for key in ("path", "title", "date", "slug", "tags")}
        for post in posts
        if not post.get("draft")
    ]
    generate_manifest(config, all_docs, posts_data=posts_data, dir_path=root)


# -- the table-heavy page ------------------------------------------------------

#: Rows long enough that the table's own scrollport really scrolls, and
#: columns wide enough that it scrolls sideways too.  The sticky-header
#: assertion needs both: a thead that stays put while rows move under it.
_TABLE_ROWS = 40
_TABLE_COLS = 9


def _long_table_markdown() -> str:
    """A table that overflows its wrapper under every theme.

    The cells are code spans holding one unbroken identifier each, which
    is what makes the overflow reliable rather than incidental. Prose
    cells wrap, so whether the table is wider than its box comes down to
    the theme's font metrics -- and tinymoon's table font is small enough
    that a prose table fits at every width the sweep visits, leaving the
    sticky-column and header-alignment assertions with nothing to scroll.
    An unbroken token has a min-content width the browser cannot reduce.
    """
    headers = ["Setting"] + [f"Column {i}" for i in range(1, _TABLE_COLS)]
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in range(1, _TABLE_ROWS + 1):
        cells = [f"`setting_{row:02d}`"] + [
            f"`value_{row:02d}_{col}_unbroken_identifier`"
            for col in range(1, _TABLE_COLS)
        ]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


# -- the three checkouts -------------------------------------------------------


def write_home_checkout(root: str) -> str:
    """The project served at the site root: front page, CV, posts, listing.

    Its ``topology`` carries the slug and deliberately **no** ``docs_base``,
    which is what makes it the home project's config rather than another
    mounted project's: a topology with both builds every URL under
    ``<docs_base>/<slug>/``, and the home project's pages are grafted to
    the site root instead.  Declaring both is what a real home project
    does not do -- and the production verification says so, which is why
    the fixture guard below asserts the assembled tree passes it.
    """
    _write_json(
        os.path.join(root, "selfdoc.json"),
        _config(
            "home", "Home",
            base_url=CANONICAL_BASE,
            topology={"slug": "home"},
            unversioned=True,
            posts={"repo": "testauthor/posts"},
        ),
    )

    _write(
        os.path.join(root, "docs", "index.md"),
        "---\n"
        "title: The Fixture Site\n"
        "description: Front page of the fixture assembly.\n"
        "date: 2026-02-01\n"
        "---\n"
        "\n"
        "# The Fixture Site\n"
        "\n"
        "This front page exists so the site root is a page a browser can\n"
        "load, with prose long enough for the search index to have words\n"
        "to match against.\n"
        "\n"
        "## Where to go\n"
        "\n"
        "- [The CV](cv/)\n"
        "- [Every project](projects/)\n"
        "- [The blog](blog/)\n"
        "\n"
        "## A second section\n"
        "\n"
        "A second heading so the front page has a table of contents worth\n"
        "rendering at every viewport width the sweep visits.\n",
    )

    # The CV page is a thin host: the whole body comes from the TOML.
    _write(
        os.path.join(root, "docs", "cv.md"),
        "---\n"
        "title: CV\n"
        "type: cv\n"
        "description: Curriculum vitae of the fixture author.\n"
        "date: 2026-02-01\n"
        "---\n"
        "\n"
        ':-: cv path="docs/cv.toml"\n',
    )
    _write(os.path.join(root, "docs", "cv.toml"), _CV_TOML)
    os.makedirs(os.path.join(root, "docs", "assets"), exist_ok=True)
    with open(os.path.join(root, "docs", "assets", "photo.png"), "wb") as fh:
        fh.write(_PNG_2X2)

    # The curated listing the front page and /projects/ both render from.
    _write(os.path.join(root, "docs", "projects.toml"), _LISTING_TOML)

    # Posts are site-level: they land at /blog/<slug>/ under no project slug.
    posts_dir = os.path.join(root, ".selfdoc", "posts")
    _write(
        os.path.join(posts_dir, "first.md"),
        "---\n"
        "title: The First Post\n"
        "date: 2026-01-10\n"
        "slug: the-first-post\n"
        "tags: [notes]\n"
        "draft: false\n"
        "directives: false\n"
        "---\n"
        "\n"
        "## A heading inside a post\n"
        "\n"
        "A post reads top to bottom and carries no table of contents, at\n"
        "any width. This heading is here so that a post with headings is\n"
        "what the viewport sweep looks at.\n"
        "\n"
        "## A second heading\n"
        "\n"
        "More prose, so the search index has something to return.\n",
    )
    _write(
        os.path.join(posts_dir, "second.md"),
        "---\n"
        "title: The Second Post\n"
        "date: 2026-01-20\n"
        "slug: the-second-post\n"
        "tags: [notes]\n"
        "draft: false\n"
        "directives: false\n"
        "---\n"
        "\n"
        "## Another post\n"
        "\n"
        "Two posts, so the blog index lists more than one and the feed has\n"
        "an order to get right.\n",
    )
    _write_manifest(root)
    return root


def write_alpha_checkout(root: str) -> str:
    """A versioned project: two tagged versions, so ``v/0.1.0/`` is an archive.

    It also carries the table-heavy page and the page that declares the
    glossary terms, because both belong to a project subtree rather than to
    the site root.
    """
    _write_json(
        os.path.join(root, "selfdoc.json"),
        _config(
            "alpha", "Alpha",
            source=[{"path": "src/", "language": "python"}],
            version="0.2.0",
            versions=[{"version": "0.1.0"}, {"version": "0.2.0"}],
        ),
    )
    _src(root, "alpha")

    index_md = (
        "---\n"
        "title: Alpha\n"
        "description: The versioned fixture project.\n"
        "date: 2026-02-01\n"
        "---\n"
        "\n"
        "# Alpha\n"
        "\n"
        "Alpha is the versioned fixture project. It has an archive, a\n"
        "version picker, and enough prose to be indexed.\n"
        "\n"
        "## Reading on\n"
        "\n"
        "- [The settings table](tables/)\n"
        "- [The terms](terms/)\n"
        f"- [An external reference]({ALLOWED_EXTERNAL})\n"
        "\n"
        "## A second section\n"
        "\n"
        "So the page has a table of contents with more than one entry.\n"
    )
    _write(os.path.join(root, "docs", "index.md"), index_md)

    _write(
        os.path.join(root, "docs", "tables.md"),
        "---\n"
        "title: Settings\n"
        "description: A table long enough to scroll under its own header.\n"
        "date: 2026-02-01\n"
        "---\n"
        "\n"
        "# Settings\n"
        "\n"
        "Every setting Alpha reads, in one table. The table is longer than\n"
        "the box it scrolls inside of, on purpose: the header row stays put\n"
        "while the rows move under it.\n"
        "\n"
        f"{_long_table_markdown()}\n"
        "\n"
        "## After the table\n"
        "\n"
        "Prose after the table, so the page does not end on it.\n"
        "\n"
        "## Reading the table\n"
        "\n"
        "A second heading, because a table of contents is only built for a\n"
        "page with two or more of them -- and this page is one of the ones\n"
        "the sweep asserts a table of contents on.\n",
    )

    # The terms page declares the glossary; the build generates
    # ``glossary/index.html`` from every term declared across the project.
    _write(
        os.path.join(root, "docs", "terms.md"),
        "---\n"
        "title: Terms\n"
        "description: The terms Alpha's documentation uses.\n"
        "date: 2026-02-01\n"
        "---\n"
        "\n"
        "# Terms\n"
        "\n"
        "The words below mean something specific in Alpha's documentation.\n"
        "\n"
        ":<: list-glossary\n"
        ":=:\n"
        "::: **Archive**: A superseded version of a page, emitted under its "
        "own version segment\n"
        "::: **Manifest**: The record a build writes describing every page "
        "it emitted\n"
        "::: **Anchor**: The identifier a heading carries so that a link can "
        "point straight at it\n"
        ":>:\n"
        "\n"
        "## Why they are here\n"
        "\n"
        "A term exists only because an author declared it.\n"
        "\n"
        "## Where they are used\n"
        "\n"
        "A second heading, for the same reason the settings page has one:\n"
        "a page with a single heading is given no table of contents.\n",
    )

    _git(["init", "-b", "main"], cwd=root)
    _git(["add", "."], cwd=root)
    _git(["commit", "-m", "alpha 0.1.0"], cwd=root)
    _git(["tag", "v0.1.0"], cwd=root)
    # A visible edit between the two versions, so the archive is not a
    # byte-for-byte copy of the current version.
    _write(
        os.path.join(root, "docs", "index.md"),
        index_md.replace(
            "Alpha is the versioned fixture project.",
            "Alpha is the versioned fixture project, revised for 0.2.0.",
        ),
    )
    _git(["add", "docs/index.md"], cwd=root)
    _git(["commit", "-m", "alpha 0.2.0"], cwd=root)
    _git(["tag", "v0.2.0"], cwd=root)
    _write_manifest(root)
    return root


def write_beta_checkout(root: str) -> str:
    """An unversioned project: no version badge, no picker, no archive."""
    _write_json(
        os.path.join(root, "selfdoc.json"),
        _config("beta", "Beta", unversioned=True),
    )
    _write(
        os.path.join(root, "docs", "index.md"),
        "---\n"
        "title: Beta\n"
        "description: The unversioned fixture project.\n"
        "date: 2026-02-01\n"
        "---\n"
        "\n"
        "# Beta\n"
        "\n"
        "Beta declares no versions at all, so nothing about it should carry\n"
        "a version badge or a version picker.\n"
        "\n"
        "## Reading on\n"
        "\n"
        "- [The guide](guide/)\n"
        "\n"
        "## A second section\n"
        "\n"
        "So this page has a table of contents too.\n",
    )
    _write(
        os.path.join(root, "docs", "guide.md"),
        "---\n"
        "title: Beta Guide\n"
        "description: A second page in the unversioned project.\n"
        "date: 2026-02-01\n"
        "---\n"
        "\n"
        "# Beta Guide\n"
        "\n"
        "A second page, so the project has page-to-page navigation.\n"
        "\n"
        "## A section\n"
        "\n"
        "And a heading, so it has a table of contents.\n",
    )
    _write_manifest(root)
    return root


_CV_TOML = """\
format_version = 1

[identity]
name = "Test Author"
headline = "Fixture Engineer"
location = "Somewhere"
email = "author@example.com"
photo = "../assets/photo.png"
updated = "2026-02-01"
summary = \"\"\"
Writes fixtures that are built the way the real thing is built.
\"\"\"

[[identity.profile]]
label = "GitHub"
url = "https://github.com/testauthor"

[[skills]]
category = "Rendering"
items = ["HTML", "CSS", "Headless browsers"]

[[skills]]
category = "Tooling"
items = ["Python", "Static site generation"]

[[projects]]
name = "The fixture assembly"
notes = ["Built through the real pipeline, never a mock."]
technologies = ["Python"]

[[interests]]
title = "Rendered reality"
body = "Asserting against what a browser actually paints."

[[education]]
degree = "BSc"
years = "2010-2014"
institute = "A University"
location = "Somewhere"

[[experience]]
role = "Engineer"
period = "2014-present"
company = "A Company"
location = "Somewhere"
body = "Kept the pipeline honest."

[[languages]]
name = "English"
level = "Native"

[contact]
body = "Reach the fixture author at author@example.com."
"""

_LISTING_TOML = """\
[[category]]
name = "Projects"

[[category.project]]
slug = "alpha"
blurb = "The versioned fixture project."

[[category.project]]
slug = "beta"
blurb = "The unversioned fixture project."
"""


# -- building and serving ------------------------------------------------------


@contextlib.contextmanager
def _toolchain_on_path():
    """Put the running environment's console scripts first on ``PATH``.

    The real pipeline shells out to ``selfdoc build`` and ``selfblog build``
    by name, which is right: that is what a deploy runs.  It does mean the
    build under test is whichever one ``PATH`` resolves first, and a machine
    with an older copy in ``~/.local/bin`` would have the suite assert
    against a site some other version produced.  Pinning the interpreter's
    own script directory removes the ambiguity without changing what runs.
    """
    scripts = os.path.dirname(os.path.abspath(sys.executable))
    previous = os.environ.get("PATH", "")
    os.environ["PATH"] = os.pathsep.join([scripts, previous]) if previous else scripts
    try:
        yield
    finally:
        os.environ["PATH"] = previous


def build_fixture_site(root: str, theme: str) -> dict:
    """Write the three checkouts under *root* and assemble them under *theme*.

    Returns :func:`~selfblog.preview.preview_assembly`'s summary, whose
    ``site_dir`` is the tree the server below serves.
    """
    from selfblog.preview import preview_assembly

    src = os.path.join(root, "src")
    home = write_home_checkout(os.path.join(src, "home"))
    alpha = write_alpha_checkout(os.path.join(src, "alpha"))
    beta = write_beta_checkout(os.path.join(src, "beta"))

    with _toolchain_on_path():
        summary = preview_assembly(
            home_dir=home,
            project_dirs=[alpha, beta],
            out_dir=os.path.join(root, "out"),
            canonical_base=CANONICAL_BASE,
            build=True,
            theme=theme,
        )

    # The preview reports verification failures and serves the tree anyway,
    # which is right for a person looking at a broken site and wrong for a
    # suite: a browser assertion against a tree the production verification
    # rejects is an assertion about something a deploy would refuse to
    # publish. So the fixture takes the report as a precondition. This is
    # not a second implementation -- it is the deploy's own check, and it
    # is what told us the first draft of the home checkout was configured
    # like a mounted project.
    report = summary["report"]
    if not report.ok:
        raise AssertionError(
            f"the {theme} fixture assembled into a tree the production "
            f"verification rejects, so nothing below would be asserting "
            f"against a publishable site:\n{report.error_text()}"
        )
    return summary


def build_standalone_project(root: str, theme: str) -> str:
    """Build the versioned checkout's own standalone site; return its output root.

    A project has two published shapes and this is the other one: its own
    site, built by ``selfdoc build`` with no version filter and deployed by
    ``selfdoc deploy``.  The distinction is not cosmetic -- it is where the
    archive lives.  An assembly build takes ``--version <latest>``
    deliberately (see :func:`~selfblog.assembly.build_source_project`), so
    an assembled subtree carries the current version and nothing else; a
    standalone build emits every declared version, the current one at the
    stable address and each superseded one under ``v/<version>/``.

    So the superseded notice, its dismissal and the version picker are
    assertions about *this* tree, and the assembled site is separately
    asserted to offer no version picker at all -- a picker there would
    offer addresses the assembled site does not serve.

    Runs after the assembly so it is this build's output that stays in the
    checkout, and indexes it, because a real standalone deploy is indexed
    too.
    """
    from selfblog.assembly import index_site

    checkout = os.path.join(root, "src", "alpha")
    argv = ["selfdoc", "build", "--no-auto-commit"]
    if theme:
        argv += ["--theme", theme]
    with _toolchain_on_path():
        subprocess.run(argv, cwd=checkout, check=True, capture_output=True)
        out = os.path.join(checkout, "docs", "_build")
        index_site(out)
    return out


class ServedSite:
    """A built fixture tree, served on loopback for the length of a session."""

    def __init__(self, site_dir: str, port: int, theme: str):
        self.site_dir = site_dir
        self.port = port
        self.theme = theme

    @property
    def origin(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def url(self, path: str) -> str:
        return f"{self.origin}/{path.lstrip('/')}"


@contextlib.contextmanager
def serve(site_dir: str, theme: str):
    """Serve *site_dir* with the production preview server on a free port.

    Yields a :class:`ServedSite` and shuts the server down on the way out.
    The server is the one ``selfblog assembly preview`` runs, on an
    ephemeral port -- not a stand-in static server, because a directory
    address serving its index and a 404 answering with a 404 status are
    exactly the wire behaviors the browser assertions depend on.
    """
    from selfblog.preview import make_preview_server

    server = make_preview_server(site_dir, 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        _wait_until_serving(server.server_port)
        yield ServedSite(site_dir, server.server_port, theme)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=10)


def _wait_until_serving(port: int, timeout: float = 10.0) -> None:
    """Block until *port* accepts a connection, or raise."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return
        except OSError:
            time.sleep(0.05)
    raise RuntimeError(f"preview server on port {port} never accepted a connection")
