"""Tests for selfdoc.manifest -- manifest generation and loading."""

import json
import os

import pytest

from selfdoc.manifest import Manifest, _extract_title, _to_kebab, generate_manifest, load_manifest


class TestToKebab:
    """Tests for _to_kebab()."""

    def test_to_kebab_basic(self):
        """Spaces converted to hyphens, result lowercased."""
        assert _to_kebab("My Project") == "my-project"

    def test_to_kebab_underscores(self):
        """Underscores converted to hyphens."""
        assert _to_kebab("my_cool_project") == "my-cool-project"

    def test_to_kebab_special_chars(self):
        """Non-alphanumeric characters (except hyphens) are stripped."""
        assert _to_kebab("hello@world!v2") == "helloworldv2"

    def test_to_kebab_collapse_hyphens(self):
        """Multiple consecutive hyphens collapsed to one."""
        assert _to_kebab("a - - b") == "a-b"

    def test_to_kebab_strips_leading_trailing(self):
        """Leading and trailing hyphens are stripped."""
        assert _to_kebab(" -hello- ") == "hello"


class TestExtractTitle:
    """Tests for _extract_title()."""

    def test_extract_title_from_frontmatter(self):
        """Uses title from frontmatter dict when present."""
        assert _extract_title({"title": "My Page"}, "# Heading\nBody") == "My Page"

    def test_extract_title_from_heading(self):
        """Falls back to first markdown heading when frontmatter has no title."""
        assert _extract_title({}, "# First Heading\nSome text") == "First Heading"

    def test_extract_title_empty(self):
        """Returns empty string when no frontmatter title and no heading."""
        assert _extract_title({}, "Just some plain text\nNo headings here") == ""


class TestGenerateManifest:
    """Tests for generate_manifest()."""

    @pytest.fixture()
    def base_config(self):
        return {
            "source": [{"path": "src/", "language": "python"}],
            "base_url": "https://example.com",
            "version": "1.0.0",
        }

    @pytest.fixture()
    def base_pages_data(self):
        return {
            "index.md": ({"title": "Home"}, "resolved content", "# Home\nWelcome", 4),
        }

    def test_generate_manifest_basic(self, tmp_path, base_config, base_pages_data):
        """Returns a Manifest with correct field types and schema_version=1."""
        m = generate_manifest(base_config, base_pages_data, dir_path=str(tmp_path))
        assert isinstance(m, Manifest)
        assert m.schema_version == 1
        assert m.version == "1.0.0"
        assert m.base_url == "https://example.com"
        assert m.language == "python"

    def test_generate_manifest_name_from_config(self, tmp_path, base_config, base_pages_data):
        """Uses name from config when provided."""
        base_config["name"] = "Configured Name"
        m = generate_manifest(base_config, base_pages_data, dir_path=str(tmp_path))
        assert m.name == "Configured Name"

    def test_generate_manifest_name_from_dirname(self, tmp_path, base_config, base_pages_data):
        """Falls back to directory basename when config has no name."""
        m = generate_manifest(base_config, base_pages_data, dir_path=str(tmp_path))
        assert m.name == os.path.basename(str(tmp_path))

    def test_generate_manifest_slug_from_topology(self, tmp_path, base_config, base_pages_data):
        """Uses slug from topology config when provided."""
        base_config["topology"] = {"slug": "custom-slug"}
        m = generate_manifest(base_config, base_pages_data, dir_path=str(tmp_path))
        assert m.slug == "custom-slug"

    def test_generate_manifest_slug_from_name(self, tmp_path, base_config, base_pages_data):
        """Falls back to kebab-cased name when topology has no slug."""
        base_config["name"] = "My Project"
        m = generate_manifest(base_config, base_pages_data, dir_path=str(tmp_path))
        assert m.slug == "my-project"

    def test_generate_manifest_pages(self, tmp_path, base_config):
        """Pages list is populated from pages_data with correct fields."""
        pages_data = {
            "guide.md": ({"title": "Guide", "type": "tutorial"}, "resolved", "# Guide\nText", 3),
            "api.md": ({}, "resolved", "# API Reference\nStuff", 0),
        }
        m = generate_manifest(base_config, pages_data, dir_path=str(tmp_path))
        assert len(m.pages) == 2
        # Pages are sorted by rel_path
        assert m.pages[0]["path"] == "api.md"
        assert m.pages[0]["title"] == "API Reference"
        assert m.pages[0]["type"] == "doc"  # default type
        assert m.pages[1]["path"] == "guide.md"
        assert m.pages[1]["title"] == "Guide"
        assert m.pages[1]["type"] == "tutorial"

    def test_generate_manifest_posts(self, tmp_path, base_config, base_pages_data):
        """Posts list is populated from posts_data."""
        posts = [
            {"path": "blog/first.md", "title": "First Post", "date": "2026-01-01", "slug": "first", "tags": ["news"]},
        ]
        m = generate_manifest(base_config, base_pages_data, posts_data=posts, dir_path=str(tmp_path))
        assert len(m.posts) == 1
        assert m.posts[0]["title"] == "First Post"
        assert m.posts[0]["date"] == "2026-01-01"
        assert m.posts[0]["slug"] == "first"
        assert m.posts[0]["tags"] == ["news"]

    def test_generate_manifest_no_posts(self, tmp_path, base_config, base_pages_data):
        """Posts defaults to empty list when posts_data is None."""
        m = generate_manifest(base_config, base_pages_data, dir_path=str(tmp_path))
        assert m.posts == []

    def test_generate_manifest_writes_file(self, tmp_path, base_config, base_pages_data):
        """Manifest JSON file is written to .selfdoc/manifest.json."""
        generate_manifest(base_config, base_pages_data, dir_path=str(tmp_path))
        manifest_path = tmp_path / ".selfdoc" / "manifest.json"
        assert manifest_path.exists()
        data = json.loads(manifest_path.read_text())
        assert data["schema_version"] == 1
        assert data["version"] == "1.0.0"
        assert data["base_url"] == "https://example.com"
        assert isinstance(data["pages"], list)
        assert isinstance(data["posts"], list)


class TestLoadManifest:
    """Tests for load_manifest()."""

    def _write_manifest(self, path, data):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f)

    def test_load_manifest_basic(self, tmp_path):
        """Loads a valid manifest and returns a Manifest instance."""
        path = str(tmp_path / "manifest.json")
        self._write_manifest(path, {
            "schema_version": 1,
            "name": "test-project",
            "slug": "test-project",
            "version": "2.0.0",
            "description": "A test",
            "language": "python",
            "base_url": "https://test.com",
            "pages": [{"path": "index.md", "title": "Home", "type": "doc"}],
            "posts": [],
            "last_gen": "2026-01-01T00:00:00+00:00",
        })
        m = load_manifest(path)
        assert isinstance(m, Manifest)
        assert m.name == "test-project"
        assert m.version == "2.0.0"
        assert m.language == "python"
        assert len(m.pages) == 1

    def test_load_manifest_missing_file(self, tmp_path):
        """Returns None when the file does not exist."""
        path = str(tmp_path / "nonexistent.json")
        assert load_manifest(path) is None

    def test_load_manifest_schema_v1(self, tmp_path):
        """Schema version 1 is accepted."""
        path = str(tmp_path / "manifest.json")
        self._write_manifest(path, {"schema_version": 1, "name": "ok"})
        m = load_manifest(path)
        assert m is not None
        assert m.schema_version == 1

    def test_load_manifest_schema_v0(self, tmp_path):
        """Schema version 0 (lower than 1) is accepted."""
        path = str(tmp_path / "manifest.json")
        self._write_manifest(path, {"schema_version": 0, "name": "legacy"})
        m = load_manifest(path)
        assert m is not None
        assert m.schema_version == 0

    def test_load_manifest_schema_v2_rejected(self, tmp_path):
        """Schema version 2 raises RuntimeError."""
        path = str(tmp_path / "manifest.json")
        self._write_manifest(path, {"schema_version": 2, "name": "future"})
        with pytest.raises(RuntimeError, match="Unsupported manifest schema_version 2"):
            load_manifest(path)

    def test_load_manifest_defaults_for_missing_keys(self, tmp_path):
        """Missing JSON keys get sensible defaults."""
        path = str(tmp_path / "manifest.json")
        self._write_manifest(path, {"schema_version": 1})
        m = load_manifest(path)
        assert m.name == ""
        assert m.slug == ""
        assert m.version == ""
        assert m.description == ""
        assert m.language == ""
        assert m.base_url == ""
        assert m.pages == []
        assert m.posts == []
        assert m.last_gen == ""
