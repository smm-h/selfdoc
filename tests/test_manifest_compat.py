"""Tests for manifest tolerant-reader contract and manifest_compat().

These tests codify the contract that manifest loading ignores unknown
keys, ensuring forward compatibility as new fields are added.
"""

import json
import os

import pytest

from selfdoc_core.manifest import (
    Manifest,
    load_manifest,
    manifest_compat,
)


# -- Tolerant-reader regression tests -----------------------------------------


class TestTolerantReader:
    """Unknown keys in manifest JSON must not cause errors."""

    def test_load_manifest_ignores_unknown_keys(self, tmp_path):
        """load_manifest silently ignores keys it does not recognize."""
        path = str(tmp_path / "manifest.json")
        data = {
            "schema_version": 1,
            "name": "test",
            "slug": "test",
            "version": "1.0.0",
            "description": "A test project",
            "language": "python",
            "base_url": "https://example.com",
            "pages": [],
            "posts": [],
            "last_gen": "2026-01-01T00:00:00Z",
            # Unknown keys that future versions might add
            "revisions": {"posts": {}},
            "theme": "dark",
            "build_timestamp": 1234567890,
            "experimental_feature": True,
            "nested_unknown": {"deep": {"value": 42}},
        }
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump(data, f)

        m = load_manifest(path)
        assert m is not None
        assert isinstance(m, Manifest)
        assert m.name == "test"
        assert m.version == "1.0.0"

    def test_manifest_compat_ignores_unknown_keys(self):
        """manifest_compat silently ignores keys it does not recognize."""
        data = {
            "schema_version": 1,
            "name": "compat-test",
            "future_field": "should be ignored",
            "another_unknown": [1, 2, 3],
        }
        m = manifest_compat(data)
        assert m.name == "compat-test"
        assert m.schema_version == 1

    def test_manifest_compat_minimal_data(self):
        """manifest_compat works with minimal data (only schema_version)."""
        m = manifest_compat({"schema_version": 1})
        assert m.name == ""
        assert m.slug == ""
        assert m.version == ""
        assert m.pages == []
        assert m.posts == []

    def test_manifest_compat_empty_dict(self):
        """manifest_compat works with an empty dict (defaults schema_version)."""
        m = manifest_compat({})
        assert m.schema_version == 1
        assert m.name == ""

    def test_manifest_compat_rejects_future_schema(self):
        """manifest_compat raises RuntimeError for schema_version > 1."""
        with pytest.raises(RuntimeError, match="Unsupported manifest schema_version 2"):
            manifest_compat({"schema_version": 2})

    def test_manifest_compat_includes_source_in_error(self):
        """Error message includes the source string when provided."""
        with pytest.raises(RuntimeError, match="in git HEAD"):
            manifest_compat({"schema_version": 2}, source="git HEAD")


# -- All read paths use manifest_compat ---------------------------------------


class TestAllReadPathsUseCompat:
    """Verify that load_manifest uses manifest_compat internally.

    This is a structural test: if unknown keys cause an error through
    load_manifest, then manifest_compat is not being used.
    """

    def test_load_manifest_tolerant(self, tmp_path):
        """load_manifest handles unknown keys without error."""
        path = str(tmp_path / "m.json")
        data = {
            "schema_version": 1,
            "name": "x",
            "totally_unknown_key": "value",
        }
        with open(path, "w") as f:
            json.dump(data, f)

        m = load_manifest(path)
        assert m is not None
        assert m.name == "x"

    def test_manifest_compat_returns_manifest(self):
        """manifest_compat returns a Manifest instance."""
        m = manifest_compat({"schema_version": 1, "name": "y"})
        assert isinstance(m, Manifest)
        assert m.name == "y"

    def test_manifest_compat_all_fields_populated(self):
        """manifest_compat populates all Manifest fields from data."""
        data = {
            "schema_version": 1,
            "name": "full",
            "slug": "full-slug",
            "version": "2.0.0",
            "description": "Full test",
            "language": "go",
            "base_url": "https://full.test",
            "pages": [{"path": "index.md"}],
            "posts": [{"slug": "hello"}],
            "last_gen": "2026-07-05T00:00:00Z",
        }
        m = manifest_compat(data)
        assert m.schema_version == 1
        assert m.name == "full"
        assert m.slug == "full-slug"
        assert m.version == "2.0.0"
        assert m.description == "Full test"
        assert m.language == "go"
        assert m.base_url == "https://full.test"
        assert len(m.pages) == 1
        assert len(m.posts) == 1
        assert m.last_gen == "2026-07-05T00:00:00Z"
