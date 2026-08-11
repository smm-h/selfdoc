"""Tests for the search index entry dataclass (selfdoc_core.context)."""

from selfdoc.context import SearchEntry


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
