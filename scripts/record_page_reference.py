#!/usr/bin/env python3
"""Record the Python page renderer's output as reference files for the Go port.

The Go ``internal/page`` package is a byte-for-byte port of the page-chrome
half of ``selfdoc_core/html.py``. Its tests assert equality against files this
script writes, so the reference is the Python's real output rather than a
transcription of it.

Usage::

    scripts/record_page_reference.py --list
    scripts/record_page_reference.py <case>        # writes one case
    scripts/record_page_reference.py --all         # re-execs itself per case

Each case runs in its OWN process, because the picker id counter in the module
under test is process-wide: recording two cases in one process would give the
second one ids no fresh Go run can reproduce.
"""

import os
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

OUT_DIR = os.path.join(REPO, "internal", "page", "testdata")

AUTHOR = {
    "name": "Test Author",
    "url": "https://author.example",
    "same_as": ["https://github.com/testauthor"],
}


def _cases():
    """Every recorded case, as name -> zero-argument callable.

    A callable returns either a dict of output key -> HTML (the multi-page
    renderers) or a single string (everything else).
    """
    from selfdoc_core.html import generate_html, generate_404_page
    from selfdoc_core.themes import get_theme_meta
    from selfdoc_core.urls import TopologyURLBuilder

    def gh(files, **kw):
        kw.setdefault("project_name", "TestProject")
        kw.setdefault("author", AUTHOR)
        return lambda: generate_html(files, **kw)

    cases = {}

    cases["simple"] = gh({"index.md": "# My Page\n\nContent here.\n"})

    cases["multipage"] = gh({
        "index.md": "# Home\n\nWelcome.\n",
        "guide.md": "# Guide\n\nA guide with prose.\n",
        "api.md": "# API\n\nReference material.\n",
    })

    cases["subdirs"] = gh(
        {
            "index.md": "# Home\n\nWelcome.\n",
            "guide.md": "# Guide\n\nContent.\n",
            "api/endpoints.md": "# Endpoints\n\nList.\n",
            "api/auth.md": "# Auth\n\nTokens.\n",
            "user_guide/quick-start.md": "# Quickstart\n\nSteps.\n",
        },
        frontmatter={
            "guide.md": {"title": "User Guide", "order": 2},
            "api/endpoints.md": {"nav_order": 2},
            "api/auth.md": {"nav_order": 1, "nav_group": "API Reference"},
        },
    )

    cases["frontmatter"] = gh(
        {
            "index.md": "# Home\n\nWelcome home.\n",
            "guide.md": "## Overview\n\nSome prose here.\n",
        },
        frontmatter={
            "guide.md": {
                "title": "The Guide",
                "description": "A complete description of the guide page.",
                "tags": ["deploy", "hosting"],
                "type": "tutorial",
            },
        },
        base_url="https://example.com",
    )

    cases["repo_dates"] = gh(
        {
            "index.md": "# Home\n\nWelcome.\n",
            "guide.md": "# Guide\n\nContent.\n",
        },
        repo="https://github.com/user/repo/",
        docs_dir_name="docs",
        branch="develop",
        page_dates={
            "index.md": ("2024-06-01", "2026-03-15"),
            "guide.md": (None, "2025-01-02"),
        },
        base_url="https://example.com",
        twitter_site="@example",
        feed_url="feed.xml",
        critical_css="body{margin:0}",
    )

    cases["feedback_ga"] = gh(
        {"index.md": "# Home\n\nWorld.\n"},
        feedback={"webhook": "https://example.com/hook", "ga": "G-XXXXX"},
    )

    cases["branding_auto"] = gh(
        {
            "index.md": "# Welcome\n\nSome intro text.\n",
            "api/one.md": "# One\n\nText.\n",
            "api/two.md": "# Two\n\nText.\n",
        },
        branding={"tagline": "A test project", "logo": "logo.svg"},
        config_description="The project description.",
    )

    cases["branding_explicit"] = gh(
        {"index.md": "# Welcome\n\nIntro.\n"},
        branding={
            "tagline": "A test project",
            "cta_text": "Start",
            "cta_link": "guide/",
            "secondary_cta_text": "Source",
            "secondary_cta_link": "https://example.com/src",
            "features": [
                {"title": "Fast", "description": "Very fast."},
                {"title": "Linked", "description": "Has a link.",
                 "link": "guide/"},
            ],
        },
    )

    cases["pickers"] = gh(
        {"index.md": "# Test\n\nHello.\n"},
        version="1.0.0",
        mount_version="1.0.0",
        available_versions=[{"version": "0.9.0"}, {"version": "1.0.0"}],
        current_version="1.0.0",
        base_url="https://example.com",
    )

    cases["locales"] = gh(
        {"index.md": "# Test\n\nHello.\n", "guide.md": "# Guide\n\nText.\n"},
        version="1.0.0",
        mount_locale="fr",
        available_locales=[
            {"code": "en", "label": "English", "default": True},
            {"code": "fr", "label": "French"},
        ],
        current_locale="fr",
        base_url="https://example.com",
    )

    cases["archived"] = gh(
        {"guide.md": "# Guide\n\nOld content.\n"},
        version="0.9.0",
        mount_locale="en",
        mount_version="0.9.0",
        mount_archived=True,
        available_versions=[{"version": "0.9.0"}, {"version": "1.0.0"}],
        current_version="0.9.0",
        current_locale="en",
        available_locales=[
            {"code": "en", "label": "English", "default": True},
            {"code": "fr", "label": "French"},
        ],
        base_url="https://example.com",
        is_latest=False,
    )

    cases["glossary"] = gh({
        "index.md": (
            "# Home\n\nWelcome. A parser is a core component.\n"
        ),
        "terms.md": (
            "# Terms\n\n"
            "Parser\n: Breaks input into tokens\n\n"
            "Lexer\n: Tokenizes raw text\n\n"
            "A <dfn>widget</dfn> is a reusable interface element.\n"
        ),
    })

    cases["itemlist"] = gh(
        {"index.md": (
            "# Links\n\n"
            "- [Alpha](https://alpha.com)\n"
            "- [Beta](https://beta.com)\n"
            "- Plain item\n"
        )},
        frontmatter={"index.md": {"schema": "itemlist"}},
    )

    cases["itemlist_auto"] = gh({"index.md": (
        "# Many\n\n"
        "- one\n- two\n- three\n- four\n- five\n- six\n"
    )})

    cases["code"] = gh(
        {"index.md": (
            "# API Reference\n\n"
            "```python\nprint('hi')\n```\n"
            "```go\nfmt.Println(1)\n```\n\n"
            "## Plain\n\n```\nplain code\n```\n\n"
            "### Config.load\n\n```python\ndef load(path): ...\n```\n\n"
            "Load configuration from a file.\n"
        )},
        repo="https://github.com/user/repo",
        run_button=True,
        line_numbers=True,
        code_icons="monochrome",
        auto_detect={"api_entries": True, "steps": True},
    )

    cases["toc"] = gh({"index.md": (
        "# Title\n\n"
        "## Section One\n\nText.\n\n"
        "### Nested\n\nMore.\n\n"
        "## Section Two\n\nMore text.\n"
    )})

    cases["deploy_github_pages"] = gh(
        {"index.md": "# Home\n\nWelcome.\n"},
        base_url="https://example.com",
        deploy_target="github-pages",
    )

    cases["unversioned"] = gh(
        {"index.md": "# Home\n\nWelcome.\n", "guide.md": "# Guide\n\nText.\n"},
        version="1.0.0",
        mount_version="1.0.0",
        unversioned_pages={
            "about.md": "# About\n\nUs.\n",
            "blog/hello.md": "# Hello\n\nA post.\n",
            "blog/later.md": "# Later\n\nAnother post.\n",
        },
        unversioned_frontmatter={
            "about.md": {"title": "About Us", "nav_order": 2},
            "blog/hello.md": {"title": "Hello", "type": "post",
                              "date": "2026-01-01"},
            "blog/later.md": {"title": "Later", "type": "post",
                              "date": "2026-02-01"},
        },
    )

    cases["post_layout"] = gh(
        {
            "index.md": "# Home\n\nWelcome.\n",
            "news.md": "## One\n\nText.\n\n## Two\n\nMore.\n",
        },
        frontmatter={"news.md": {
            "title": "A Post", "type": "post",
            "description": "The post's own summary line.",
            "tags": ["release"],
        }},
        page_dates={"news.md": ("2026-06-01", "2026-06-29")},
        base_url="https://example.com",
    )

    cases["search_bar"] = gh(
        {"index.md": "# Home\n\nWelcome.\n"}, search="bar")

    cases["search_hidden"] = gh(
        {"index.md": "# Home\n\nWelcome.\n"}, search="hidden")

    cases["theme_clean"] = gh(
        {"index.md": "# Home\n\nWelcome.\n"},
        theme_meta=get_theme_meta("clean"),
    )

    cases["theme_tinymoon"] = gh(
        {"index.md": "# Home\n\nWelcome.\n", "guide.md": "# Guide\n\nText.\n"},
        theme_meta=get_theme_meta("tinymoon"),
    )

    cases["mounted"] = gh(
        {
            "index.md": "# Home\n\nWelcome.\n",
            "guide.md": "# Guide\n\nText.\n",
            "blog/hello.md": "# Hello\n\nA post about things.\n",
        },
        frontmatter={"blog/hello.md": {"title": "Hello", "type": "post"}},
        url_builder=TopologyURLBuilder("https://docs.example.com", "myproj"),
        base_url="https://docs.example.com/myproj",
        mount_project="myproj",
        feed_url="feed.xml",
    )

    cases["no_page_nav"] = gh(
        {
            "index.md": "# Home\n\nWelcome.\n",
            "guide.md": "# Guide\n\nText.\n",
        },
        page_nav=False,
        page_progress=False,
        glossary=False,
        has_custom_css=True,
    )

    def docs_corpus():
        """A frozen copy of the repository's docs templates, as a corpus.

        Directives are deliberately NOT resolved: both renderers see the same
        marker text, so the case measures the page chrome over real documents
        -- long pages, nested directories, frontmatter, tables, code blocks --
        rather than over fixtures written for it.

        The corpus is a FROZEN copy under testdata/corpus, not the live docs
        directory, so the reference does not move when the documentation is
        edited and both renderers read the same bytes.

        A template that states neither an H1 nor a frontmatter title is
        refused by the renderer, so one gets an H1 named after its path.
        """
        from selfdoc_core.utils import parse_frontmatter
        from selfdoc_core.tokenizer import tokenize, Heading

        docs = {}
        frontmatter = {}
        docs_dir = os.path.join(OUT_DIR, "corpus")
        for root, _dirs, files in os.walk(docs_dir):
            if "_build" in root:
                continue
            for fname in sorted(files):
                if not fname.endswith(".md") or fname.startswith("_"):
                    continue
                full = os.path.join(root, fname)
                rel = os.path.relpath(full, docs_dir)
                with open(full, "r", encoding="utf-8") as handle:
                    raw = handle.read()
                meta, body = parse_frontmatter(raw)[:2]
                has_h1 = any(
                    isinstance(tok, Heading) and tok.level == 1
                    for tok in tokenize(body)
                )
                if not has_h1 and not meta.get("title"):
                    body = "# " + rel.replace(".md", "") + "\n\n" + body
                docs[rel] = body
                if meta:
                    frontmatter[rel] = meta
        return generate_html(
            docs,
            project_name="selfdoc",
            version="0.38.1",
            frontmatter=frontmatter,
            author=AUTHOR,
            base_url="https://selfdoc.smmh.dev",
            repo="https://github.com/smm-h/selfdoc",
            feed_url="feed.xml",
            theme_meta=get_theme_meta("tinymoon"),
        )

    cases["docs_corpus"] = docs_corpus

    def not_found():
        from selfdoc_core.html import _build_nav
        nav = _build_nav(
            {
                "index.md": "# Home",
                "guide.md": "# Guide",
                "api/auth.md": "# Auth",
                "api/endpoints.md": "# Endpoints",
                "extra.md": "# Extra",
                "sixth.md": "# Sixth",
            },
            frontmatter={"guide.md": {"title": "The Guide"}},
        )
        return generate_404_page(
            project_name="TestProject",
            version="1.0.0",
            has_custom_css=True,
            nav_items=nav,
            base_url="https://example.com",
            lang="en",
            feed_url="feed.xml",
            critical_css="body{margin:0}",
            theme_meta=get_theme_meta("minimal"),
        )

    cases["not_found"] = not_found

    def not_found_mounted():
        from selfdoc_core.html import _build_nav
        nav = _build_nav({"index.md": "# Home", "guide.md": "# Guide"})
        return generate_404_page(
            project_name="TestProject",
            nav_items=nav,
            mount_locale="en",
            mount_project="core",
            theme_meta=get_theme_meta("minimal"),
        )

    cases["not_found_mounted"] = not_found_mounted

    def seo_variants():
        from selfdoc_core.html import _render_seo_tags
        blocks = []
        variants = [
            ("guide", None, None, "guide/index.html", "A test page"),
            ("tutorial", None, None, "guide/index.html", "A test page"),
            ("post", None, ["python", "testing", "ci"], "guide/index.html",
             "A test page"),
            ("post", None, [], "guide/index.html", "A test page"),
            ("changelog", None, None, "guide/index.html", "A test page"),
            ("fieldnote", None, None, "guide/index.html", "A test page"),
            (None, None, None, "guide/index.html", "A test page"),
            ("guide", {"guide": "HowTo"}, None, "guide/index.html",
             "A test page"),
            ("news", {"news": "BlogPosting"}, ["breaking", "update"],
             "guide/index.html", "A test page"),
            ("cv", None, None, "cv/index.html", ""),
            ("guide", {}, None, "index.html", ""),
            ("guide", None, None, "api/auth/index.html", "Nested page"),
        ]
        langs = ["en"] * len(variants)
        # An unmapped language tag and an unstated one: the Open Graph locale
        # is derived from the tag rather than looked up, and the empty tag
        # reaches inLanguage as written while the locale falls back.
        variants = variants + [
            ("guide", None, None, "guide/index.html", "A test page"),
            ("guide", None, None, "guide/index.html", "A test page"),
        ]
        langs = langs + ["pt-BR", ""]
        for (page_type, schema_types, page_tags, page_path, desc), lang in zip(
            variants, langs
        ):
            seo, security = _render_seo_tags(
                title="A Page",
                base_url="https://example.com",
                page_path=page_path,
                description=desc,
                body_html="<p>Body of the page. Second sentence.</p>",
                author=AUTHOR,
                project_name="mypackage",
                repo="https://github.com/u/r",
                date_published="2024-01-01",
                date_modified="2026-01-01",
                lang=lang,
                breadcrumbs="<nav>crumbs</nav>",
                schema=None,
                twitter_site="@mypackage",
                deploy_target="github-pages",
                page_type=page_type,
                schema_types=schema_types,
                page_tags=page_tags,
                available_locales=[
                    {"code": "en", "label": "English", "default": True},
                    {"code": "pt-BR", "label": "Portuguese"},
                ],
                current_locale="en",
                mount_locale="en",
            )
            blocks.append(
                f"--- page_type={page_type!r} schema_types={schema_types!r} "
                f"page_tags={page_tags!r} page_path={page_path!r} "
                f"lang={lang!r}\n"
                f"{seo}\n### security\n{security}"
            )
        return "\n".join(blocks)

    cases["seo_variants"] = seo_variants

    def seo_no_base_url():
        from selfdoc_core.html import _render_seo_tags
        seo, security = _render_seo_tags(
            title="A Page",
            base_url=None,
            page_path="guide/index.html",
            description="",
            body_html='<p>Body.</p><pre><code class="language-python">x</code></pre>',
            author=AUTHOR,
            project_name="mypackage",
            repo=None,
            date_published=None,
            date_modified=None,
            lang="pt",
            breadcrumbs=None,
            schema=None,
            twitter_site=None,
            deploy_target=None,
            page_type="guide",
        )
        return f"{seo}\n### security\n{security}"

    cases["seo_no_base_url"] = seo_no_base_url

    def fragments():
        from selfdoc_core.html import (
            pagefind_head_tags,
            pagefind_init_script,
            pagefind_dialog_html,
            palette_search_script,
            pagefind_facets_html,
            pagefind_meta_html,
            module_specifier,
            theme_modules_prefix,
        )
        out = []
        out.append("## pagefind_head_tags\n" + pagefind_head_tags("../../"))
        out.append("## pagefind_init_script\n" + pagefind_init_script("../"))
        out.append("## pagefind_dialog_html\n" + pagefind_dialog_html())
        for prefix, css in (
            ("", "css/style.css"),
            ("../", "../css/style.css"),
            ("../../", "../../_chrome/tinymoon-abc123/css/style.css"),
        ):
            out.append(
                f"## palette_search_script {prefix!r} {css!r}\n"
                + palette_search_script(prefix, css))
        out.append("## theme_modules_prefix\n" + "\n".join(
            theme_modules_prefix(h) for h in (
                "css/style.css", "../css/style.css",
                "../_chrome/tinymoon-abc123/css/style.css",
            )))
        out.append("## module_specifier\n" + "\n".join(
            module_specifier(p) for p in (
                "js/palette.js", "./js/palette.js", "../js/palette.js",
                "/js/palette.js", "pagefind/pagefind.js",
            )))
        out.append("## pagefind_facets_html\n" + pagefind_facets_html(
            version="1.0.0", locale="pt-BR", group="Guides",
            page_type="guide", target="cloudflare-pages",
            project='My "Project" <1>', tags=["a,b", "c", ""],
        ))
        out.append("## pagefind_facets_html empty\n"
                   + pagefind_facets_html(tags=[]))
        out.append("## pagefind_meta_html\n" + pagefind_meta_html(
            project='My "Project" <1>', page_type="guide", date="2024-01-15",
        ))
        out.append("## pagefind_meta_html empty\n" + pagefind_meta_html())
        return "\n".join(out)

    cases["fragments"] = fragments

    def derive_types():
        from selfdoc_core.html import derive_page_type
        rows = [
            ("intro.md", {"type": "tutorial"}, ""),
            ("changelog.md", {"type": "post"}, ""),
            ("glossary.md", {"type": "reference"}, ""),
            ("api.md", {"generated": True, "type": "reference"},
             "API Reference"),
            ("cli.md", {"generated": True, "type": "tutorial"},
             "CLI Reference"),
            ("blog.md", {"type": "post"}, ""),
            ("page.md", {"type": "cookbook"}, ""),
            ("page.md", {"title": "Page"}, ""),
            ("page.md", {}, ""),
            ("changelog.md", {}, ""),
            ("glossary.md", {}, ""),
            ("api.md", {"generated": True}, "API Reference"),
            ("cli.md", {"generated": True}, "CLI Reference"),
            ("changelog.md", {"type": ""}, ""),
            ("glossary.md", {"type": None}, ""),
            ("page.md", {"type": "tutorial", "tags": ["python"]}, ""),
            ("api.md", {"generated": True, "type": "reference"}, ""),
            ("api.md", {"generated": True}, "Guides"),
            ("api.md", {"generated": "yes"}, "API Reference"),
            ("docs/CHANGELOG.md", {}, ""),
            ("Glossary.md", {}, ""),
        ]
        return "\n".join(
            f"{md!r} {meta!r} {group!r} -> {derive_page_type(md, meta, group)}"
            for md, meta, group in rows
        )

    cases["derive_page_type"] = derive_types

    def nav_variants():
        from selfdoc_core.html import _build_nav, _flatten_nav
        import json

        def dump(nav):
            return json.dumps(nav, indent=2, sort_keys=True)

        out = []
        out.append("## plain\n" + dump(_build_nav(
            {"index.md": "", "guide.md": ""},
            frontmatter={"index.md": {"title": "Home"},
                         "guide.md": {"title": "User Guide"}},
        )))
        out.append("## ordered\n" + dump(_build_nav(
            {"index.md": "", "b.md": "", "a.md": "", "c.md": ""},
            frontmatter={"b.md": {"order": 1}, "c.md": {"order": 0}},
        )))
        out.append("## groups\n" + dump(_build_nav(
            {
                "index.md": "",
                "guide.md": "",
                "api/endpoints.md": "",
                "api/auth.md": "",
                "user_guide/quickstart.md": "",
                "zed-things/x.md": "",
            },
            frontmatter={
                "api/auth.md": {"nav_order": 1},
                "api/endpoints.md": {"nav_order": 2,
                                     "nav_group": "API Reference"},
            },
        )))
        out.append("## unversioned\n" + dump(_build_nav(
            {"index.md": "", "guide.md": ""},
            frontmatter={"index.md": {"title": "Home"},
                         "guide.md": {"title": "User Guide"}},
            unversioned_pages={"about.md": "", "terms.md": "",
                               "p1.md": "", "p2.md": ""},
            unversioned_frontmatter={
                "about.md": {"title": "About Us", "nav_order": 2},
                "terms.md": {"title": "Terms of Service", "nav_order": 1},
                "p1.md": {"title": "First", "type": "post",
                          "date": "2026-01-01"},
                "p2.md": {"title": "Second", "type": "post",
                          "date": "2026-03-01"},
            },
        )))
        out.append("## unversioned only posts\n" + dump(_build_nav(
            {"index.md": ""},
            unversioned_pages={"about.md": ""},
        )))
        out.append("## empty unversioned\n" + dump(_build_nav(
            {"index.md": "", "guide.md": ""}, unversioned_pages={},
        )))
        out.append("## flatten\n" + dump(_flatten_nav(_build_nav(
            {"index.md": "", "api/a.md": "", "api/b.md": "", "z.md": ""},
        ))))
        return "\n".join(out)

    cases["build_nav"] = nav_variants

    def nav_render():
        from selfdoc_core.html import _build_nav, _render_nav
        nav = _build_nav(
            {
                "index.md": "",
                "guide.md": "",
                "api/auth.md": "",
                "api/endpoints.md": "",
            },
            frontmatter={"guide.md": {"title": "The <Guide>"}},
            unversioned_pages={"about.md": "", "blog/hello.md": ""},
            unversioned_frontmatter={
                "blog/hello.md": {"title": "Hello", "type": "post",
                                  "date": "2026-01-01"},
            },
        )
        out = []
        for current in ("index.html", "api/auth/index.html",
                        "blog/hello/index.html", ""):
            out.append(f"## current={current!r}\n" + _render_nav(
                nav, "../", current_path=current,
                unversioned_prefix="../../", site_prefix="../../../",
            ))
        return "\n".join(out)

    cases["render_nav"] = nav_render

    def toc_and_crumbs():
        from selfdoc_core.html import (
            _build_toc, _build_breadcrumbs, _extract_first_paragraph,
            _extract_title,
        )
        out = []
        bodies = [
            "<p>No headings.</p>",
            '<h2 id="a"><a class="heading-link" href="#a" aria-label="x">#</a>One</h2>',
            ('<h2 id="a"><a class="heading-link" href="#a" aria-label="x">#</a>One</h2>\n'
             '<h3 id="b"><a class="heading-link" href="#b" aria-label="x">#</a>Two <code>x</code></h3>\n'
             '<h2 id="c"><a class="heading-link" href="#c" aria-label="x">#</a>Three &amp; four</h2>'),
            ('<h2 id="a">One</h2>\n<h2 id="b">Two</h2>'),
            ('<h4 id="a"><a class="heading-link" href="#a">#</a>One</h4>\n'
             '<h2 id="b"><a class="heading-link" href="#b">#</a>Two</h2>\n'
             '<h2 id="c"><a class="heading-link" href="#c">#</a>Three</h2>'),
            # A heading with no anchor of its own, standing before two that
            # have one: the pattern this port replaces could walk past the
            # close tag looking for an anchor, so this pins what it really
            # produced.
            ('<h2 id="a">plain</h2>\n'
             '<h3 id="b"><a class="heading-link" href="#b">#</a>Two</h3>\n'
             '<h3 id="c"><a class="heading-link" href="#c">#</a>Three</h3>'),
            # A heading whose text spans a newline is not a heading the table
            # of contents reads, because the pattern's wildcard never
            # crossed one.
            ('<h2 id="a"><a class="heading-link" href="#a">#</a>One\ntwo</h2>\n'
             '<h2 id="b"><a class="heading-link" href="#b">#</a>Three</h2>\n'
             '<h2 id="c"><a class="heading-link" href="#c">#</a>Four</h2>'),
            # Markup standing between the opening tag and the anchor.
            ('<h2 id="a"><span class="pre">x</span>'
             '<a class="heading-link" href="#a">#</a>One</h2>\n'
             '<h2 id="b"><a class="heading-link" href="#b">#</a>Two</h2>'),
            # A repeated heading text, whose ids the anchor authority made
            # unique.
            ('<h2 id="setup"><a class="heading-link" href="#setup">#</a>Setup</h2>\n'
             '<h2 id="setup-1"><a class="heading-link" href="#setup-1">#</a>Setup</h2>'),
        ]
        for i, body in enumerate(bodies):
            out.append(f"## toc {i}\n" + _build_toc(body))
        crumb_cases = [
            ("guide/index.html", "Guide", "", set(), "index.html", None),
            ("api/endpoints/index.html", "Endpoints", "../",
             {"api/index.html"}, "../index.html", None),
            ("api/endpoints/index.html", "Endpoints", "../", set(),
             "../index.html", None),
            ("blog/hello/index.html", "Hello <post>", "../", {"blog/index.html"},
             "../index.html", "../../"),
        ]
        for i, (path, title, prefix, existing, home, site) in enumerate(
            crumb_cases
        ):
            out.append(f"## crumbs {i}\n" + _build_breadcrumbs(
                path, title, prefix, existing, home_href=home,
                site_prefix=site,
            ))
        for i, body in enumerate([
            "<p>First <b>bold</b> paragraph.</p><p>Second.</p>",
            "no paragraph",
            "<p>Multi\nline\nparagraph.</p>",
        ]):
            out.append(f"## first_paragraph {i}\n"
                       + _extract_first_paragraph(body))
        for i, (md, fb) in enumerate([
            ("# Hello World\n\nContent.", "fallback"),
            ("## Only H2\n\nContent.", "fallback"),
            ("# Hello `World`\n\nContent.", "fallback"),
            ("```\n# Not a title\n```\n\n# Real Title\n", "fallback"),
            ("```\n# Not a title\n```\n", "fallback"),
        ]):
            out.append(f"## extract_title {i}\n" + _extract_title(md, fb))
        return "\n".join(out)

    cases["toc_and_crumbs"] = toc_and_crumbs

    return cases


def _write(name, result):
    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, name + ".txt")
    if isinstance(result, str):
        payload = result
    else:
        parts = []
        for key in sorted(result):
            parts.append(f"===== KEY {key}\n{result[key]}")
        payload = "".join(parts)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(payload)
    print(f"wrote {os.path.relpath(path, REPO)}")


def main(argv):
    cases = _cases()
    if not argv or argv[0] == "--list":
        for name in sorted(cases):
            print(name)
        return 0
    if argv[0] == "--all":
        for name in sorted(cases):
            subprocess.run(
                [sys.executable, os.path.abspath(__file__), name], check=True,
            )
        return 0
    name = argv[0]
    if name not in cases:
        print(f"unknown case {name!r}", file=sys.stderr)
        return 2
    _write(name, cases[name]())
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
