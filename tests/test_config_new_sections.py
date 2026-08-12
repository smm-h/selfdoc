"""Tests for posts, topology, and assembly config sections."""

import json
import os

import pytest

from selfdoc.config import ConfigError, load_config


@pytest.fixture()
def config_dir(tmp_path):
    """Return a temp directory; write selfdoc.json via the helper."""
    return tmp_path


#: The declared facts every config carries, filled in by the writer below
#: when a test does not name them.  A test about one field should not have to
#: restate the required ones -- and a test about a required field states it
#: itself, which overrides these.
_REQUIRED = {
    "search_engine": "pagefind",
    "author": {"name": "Test Author", "url": "https://author.example"},
}


def _write_config(directory, data):
    """Write *data* as selfdoc.json inside *directory*, required keys filled."""
    path = os.path.join(directory, "selfdoc.json")
    payload = {**_REQUIRED, **data}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f)


_BASE = {
    "source": [{"path": "src/", "language": "python"}],
    "base_url": "https://example.com",
}


def _cfg(**extra):
    """Return a valid base config merged with *extra* keys."""
    return {**_BASE, **extra}


# -- posts --


def test_posts_valid_dir(config_dir):
    """posts with a valid dir string passes validation."""
    _write_config(config_dir, _cfg(posts={"dir": ".selfdoc/posts/"}))
    cfg = load_config(str(config_dir))
    assert cfg["posts"]["dir"] == ".selfdoc/posts/"


def test_posts_invalid_dir_type(config_dir):
    """posts.dir with wrong type (int) raises ConfigError."""
    _write_config(config_dir, _cfg(posts={"dir": 123}))
    with pytest.raises(ConfigError):
        load_config(str(config_dir))


def test_posts_defaults_when_fields_omitted(config_dir):
    """posts as empty dict passes validation; result is a dict."""
    _write_config(config_dir, _cfg(posts={}))
    cfg = load_config(str(config_dir))
    assert isinstance(cfg["posts"], dict)


def test_posts_missing_when_absent(config_dir):
    """Config without posts key has cfg['posts'] as None."""
    _write_config(config_dir, _cfg())
    cfg = load_config(str(config_dir))
    assert cfg["posts"] is None


# -- assembly --


def test_assembly_valid_repo(config_dir):
    """assembly with a valid repo string passes validation."""
    _write_config(config_dir, _cfg(assembly={"repo": "smm-h/docs-assembly"}))
    cfg = load_config(str(config_dir))
    assert cfg["assembly"]["repo"] == "smm-h/docs-assembly"


def test_assembly_missing_when_absent(config_dir):
    """Config without assembly key has cfg['assembly'] as None."""
    _write_config(config_dir, _cfg())
    cfg = load_config(str(config_dir))
    assert cfg["assembly"] is None


# -- topology --


def test_topology_empty_dict(config_dir):
    """topology as empty dict passes validation."""
    _write_config(config_dir, _cfg(topology={}))
    cfg = load_config(str(config_dir))
    assert isinstance(cfg["topology"], dict)


def test_topology_missing_when_absent(config_dir):
    """Config without topology key has cfg['topology'] as None."""
    _write_config(config_dir, _cfg())
    cfg = load_config(str(config_dir))
    assert cfg["topology"] is None
