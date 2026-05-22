from selfdoc.context import BuildContext, PageContext, SearchEntry


def _build_context(**overrides):
    defaults = dict(
        dir_path="/tmp/proj",
        config={"name": "test"},
        locale="en",
        version="0.7.0",
        url_prefix="en/0.7.0",
        output_dir="/tmp/proj/site/en/0.7.0",
        output_subdir="en/0.7.0",
        is_latest=True,
        available_versions=[{"version": "0.7.0"}],
        available_locales=[{"code": "en"}],
        base_url="https://example.com",
        project_name="myproj",
        theme_meta={"name": "default"},
        accent_color="#3b82f6",
        critical_css="body{margin:0}",
        deploy_target=None,
    )
    defaults.update(overrides)
    return BuildContext(**defaults)


def _page_context(**overrides):
    defaults = dict(
        md_path="index.md",
        html_path="index.html",
        title="Home",
        body_html="<p>Hello</p>",
        nav_html="<nav></nav>",
        toc_html="",
        breadcrumbs=None,
        prefix="",
        frontmatter={},
        prev_page=None,
        next_page=None,
        page_number=1,
        total_pages=5,
        summary="",
        source_path=None,
    )
    defaults.update(overrides)
    return PageContext(**defaults)


class TestBuildContext:
    def test_instantiation(self):
        ctx = _build_context()
        assert ctx.dir_path == "/tmp/proj"
        assert ctx.locale == "en"
        assert ctx.version == "0.7.0"

    def test_fields_accessible(self):
        ctx = _build_context()
        for name in (
            "dir_path", "config", "locale", "version", "url_prefix",
            "output_dir", "output_subdir", "is_latest", "available_versions",
            "available_locales", "base_url", "project_name", "theme_meta",
            "accent_color", "critical_css", "deploy_target",
        ):
            assert hasattr(ctx, name)

    def test_nullable_fields(self):
        ctx = _build_context(base_url=None, deploy_target=None)
        assert ctx.base_url is None
        assert ctx.deploy_target is None


class TestPageContext:
    def test_instantiation(self):
        pg = _page_context()
        assert pg.title == "Home"
        assert pg.body_html == "<p>Hello</p>"

    def test_fields_accessible(self):
        pg = _page_context()
        for name in (
            "md_path", "html_path", "title", "body_html", "nav_html",
            "toc_html", "breadcrumbs", "prefix", "frontmatter", "prev_page",
            "next_page", "page_number", "total_pages", "summary", "source_path",
        ):
            assert hasattr(pg, name)

    def test_nullable_fields(self):
        pg = _page_context(
            breadcrumbs=None, prev_page=None, next_page=None,
            page_number=None, total_pages=None, source_path=None,
        )
        assert pg.breadcrumbs is None
        assert pg.source_path is None


class TestSearchEntry:
    def test_instantiation_required_only(self):
        entry = SearchEntry(title="Home", path="/", body="Welcome")
        assert entry.title == "Home"
        assert entry.path == "/"
        assert entry.body == "Welcome"

    def test_defaults(self):
        entry = SearchEntry(title="Home", path="/", body="Welcome")
        assert entry.version == ""
        assert entry.locale == ""
        assert entry.group == ""
        assert entry.type == ""
        assert entry.target == ""
        assert entry.project == ""
        assert entry.tags == []

    def test_tags_not_shared_mutable(self):
        a = SearchEntry(title="A", path="/a", body="a")
        b = SearchEntry(title="B", path="/b", body="b")
        a.tags.append("python")
        assert b.tags == []

    def test_fields_accessible(self):
        entry = SearchEntry(title="T", path="/t", body="t")
        for name in (
            "title", "path", "body", "version", "locale",
            "group", "type", "target", "project", "tags",
        ):
            assert hasattr(entry, name)

    def test_custom_defaults(self):
        entry = SearchEntry(
            title="API", path="/api", body="Reference",
            version="1.0.0", locale="fr", group="Reference",
            type="api", target="python", project="mylib",
            tags=["generated"],
        )
        assert entry.version == "1.0.0"
        assert entry.locale == "fr"
        assert entry.tags == ["generated"]
