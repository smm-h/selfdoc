"""Tests for topology config schema validation."""

import json
import os

import pytest

from selfdoc.config import ConfigError, load_config


@pytest.fixture()
def config_dir(tmp_path):
    """Return a temp directory for config files."""
    return tmp_path


def _write_config(directory, data):
    """Write *data* as selfdoc.json inside *directory*."""
    path = os.path.join(directory, "selfdoc.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)


_BASE = {
    "source": [{"path": "src/", "language": "python"}],
    "base_url": "https://example.com",
}


def _cfg(**extra):
    """Return a valid base config merged with *extra* keys."""
    return {**_BASE, **extra}


class TestTopologyAbsent:
    """Topology absent or empty."""

    def test_missing_when_absent(self, config_dir):
        _write_config(config_dir, _cfg())
        cfg = load_config(str(config_dir))
        assert cfg["topology"] is None

    def test_empty_dict(self, config_dir):
        _write_config(config_dir, _cfg(topology={}))
        cfg = load_config(str(config_dir))
        assert isinstance(cfg["topology"], dict)


class TestTopologySlug:
    """topology.slug validation."""

    def test_valid_slug(self, config_dir):
        _write_config(config_dir, _cfg(topology={"slug": "selfdoc"}))
        cfg = load_config(str(config_dir))
        assert cfg["topology"]["slug"] == "selfdoc"

    def test_slug_wrong_type(self, config_dir):
        _write_config(config_dir, _cfg(topology={"slug": 123}))
        with pytest.raises(ConfigError):
            load_config(str(config_dir))


class TestTopologyDocsBase:
    """topology.docs_base validation and trailing slash transform."""

    def test_valid_docs_base(self, config_dir):
        _write_config(config_dir, _cfg(topology={"docs_base": "https://docs.smmh.dev"}))
        cfg = load_config(str(config_dir))
        assert cfg["topology"]["docs_base"] == "https://docs.smmh.dev"

    def test_strips_trailing_slash(self, config_dir):
        _write_config(config_dir, _cfg(topology={"docs_base": "https://docs.smmh.dev/"}))
        cfg = load_config(str(config_dir))
        assert cfg["topology"]["docs_base"] == "https://docs.smmh.dev"

    def test_docs_base_wrong_type(self, config_dir):
        _write_config(config_dir, _cfg(topology={"docs_base": 42}))
        with pytest.raises(ConfigError):
            load_config(str(config_dir))


class TestTopologyPostsBase:
    """topology.posts_base validation and trailing slash transform."""

    def test_valid_posts_base(self, config_dir):
        _write_config(config_dir, _cfg(topology={"posts_base": "https://docs.smmh.dev/blog"}))
        cfg = load_config(str(config_dir))
        assert cfg["topology"]["posts_base"] == "https://docs.smmh.dev/blog"

    def test_strips_trailing_slash(self, config_dir):
        _write_config(config_dir, _cfg(topology={"posts_base": "https://docs.smmh.dev/blog/"}))
        cfg = load_config(str(config_dir))
        assert cfg["topology"]["posts_base"] == "https://docs.smmh.dev/blog"


class TestTopologyAssembly:
    """topology.assembly string validation."""

    def test_valid_assembly(self, config_dir):
        _write_config(config_dir, _cfg(topology={"assembly": "smm-h/docs-assembly"}))
        cfg = load_config(str(config_dir))
        assert cfg["topology"]["assembly"] == "smm-h/docs-assembly"


class TestTopologyProjects:
    """topology.projects dict validation."""

    def test_valid_projects(self, config_dir):
        _write_config(config_dir, _cfg(topology={
            "projects": {
                "rlsbl": "https://docs.smmh.dev/rlsbl",
                "strictcli": "https://docs.smmh.dev/strictcli",
            }
        }))
        cfg = load_config(str(config_dir))
        assert cfg["topology"]["projects"]["rlsbl"] == "https://docs.smmh.dev/rlsbl"
        assert cfg["topology"]["projects"]["strictcli"] == "https://docs.smmh.dev/strictcli"

    def test_empty_projects_dict(self, config_dir):
        _write_config(config_dir, _cfg(topology={"projects": {}}))
        cfg = load_config(str(config_dir))
        assert cfg["topology"]["projects"] == {}

    def test_projects_wrong_type(self, config_dir):
        _write_config(config_dir, _cfg(topology={"projects": "not-a-dict"}))
        with pytest.raises(ConfigError):
            load_config(str(config_dir))


class TestTopologyFull:
    """Full topology config with all fields."""

    def test_all_fields_present(self, config_dir):
        _write_config(config_dir, _cfg(topology={
            "assembly": "smm-h/docs-assembly",
            "slug": "selfdoc",
            "docs_base": "https://docs.smmh.dev",
            "posts_base": "https://docs.smmh.dev/blog",
            "projects": {"rlsbl": "https://docs.smmh.dev/rlsbl"},
        }))
        cfg = load_config(str(config_dir))
        topo = cfg["topology"]
        assert topo["assembly"] == "smm-h/docs-assembly"
        assert topo["slug"] == "selfdoc"
        assert topo["docs_base"] == "https://docs.smmh.dev"
        assert topo["posts_base"] == "https://docs.smmh.dev/blog"
        assert topo["projects"]["rlsbl"] == "https://docs.smmh.dev/rlsbl"

    def test_unknown_keys_allowed(self, config_dir):
        """topology is not strict_keys, so extra keys should be accepted."""
        _write_config(config_dir, _cfg(topology={
            "slug": "selfdoc",
            "custom_field": "allowed",
        }))
        cfg = load_config(str(config_dir))
        assert cfg["topology"]["custom_field"] == "allowed"
