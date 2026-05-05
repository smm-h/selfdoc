"""Tests for selfdoc.config."""

import json
import os

import pytest

from selfdoc.config import ConfigError, load_config


@pytest.fixture()
def config_dir(tmp_path):
    """Return a temp directory; write selfdoc.json via the helper."""
    return tmp_path


def _write_config(directory, data):
    """Write *data* as selfdoc.json inside *directory*."""
    path = os.path.join(directory, "selfdoc.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)


# -- happy path --


def test_valid_config_loads(config_dir):
    _write_config(config_dir, {
        "language": "python",
        "source": ["src/"],
        "docs": "docs/",
        "output": "docs/_build/",
        "deploy": {"provider": "github-pages"},
        "directives": {},
    })
    cfg = load_config(str(config_dir))
    assert cfg is not None
    assert cfg["language"] == "python"
    assert cfg["source"] == ["src/"]
    assert cfg["deploy"]["provider"] == "github-pages"


def test_defaults_applied(config_dir):
    """Optional fields get their defaults when omitted."""
    _write_config(config_dir, {
        "language": "go",
        "source": ["pkg/"],
    })
    cfg = load_config(str(config_dir))
    assert cfg["docs"] == "docs/"
    assert cfg["output"] == "docs/_build/"
    assert cfg["deploy"] is None
    assert cfg["directives"] == {}


# -- missing file --


def test_missing_file_returns_none(tmp_path):
    assert load_config(str(tmp_path)) is None


# -- required fields --


def test_missing_language(config_dir):
    _write_config(config_dir, {"source": ["src/"]})
    with pytest.raises(ConfigError, match="missing required field 'language'"):
        load_config(str(config_dir))


def test_missing_source(config_dir):
    _write_config(config_dir, {"language": "python"})
    with pytest.raises(ConfigError, match="missing required field 'source'"):
        load_config(str(config_dir))


# -- invalid values --


def test_invalid_language(config_dir):
    _write_config(config_dir, {"language": "ruby", "source": ["lib/"]})
    with pytest.raises(ConfigError, match="invalid language"):
        load_config(str(config_dir))


def test_source_not_a_list(config_dir):
    _write_config(config_dir, {"language": "python", "source": "src/"})
    with pytest.raises(ConfigError, match="'source' must be a non-empty list"):
        load_config(str(config_dir))


def test_source_empty_list(config_dir):
    _write_config(config_dir, {"language": "python", "source": []})
    with pytest.raises(ConfigError, match="'source' must be a non-empty list"):
        load_config(str(config_dir))


# -- deploy validation --


def test_invalid_deploy_provider(config_dir):
    _write_config(config_dir, {
        "language": "typescript",
        "source": ["src/"],
        "deploy": {"provider": "netlify"},
    })
    with pytest.raises(ConfigError, match="invalid deploy provider"):
        load_config(str(config_dir))


def test_cloudflare_requires_project(config_dir):
    _write_config(config_dir, {
        "language": "javascript",
        "source": ["lib/"],
        "deploy": {"provider": "cloudflare-pages"},
    })
    with pytest.raises(ConfigError, match="'deploy.project' is required"):
        load_config(str(config_dir))


def test_cloudflare_with_project(config_dir):
    _write_config(config_dir, {
        "language": "javascript",
        "source": ["lib/"],
        "deploy": {"provider": "cloudflare-pages", "project": "my-docs"},
    })
    cfg = load_config(str(config_dir))
    assert cfg["deploy"]["provider"] == "cloudflare-pages"
    assert cfg["deploy"]["project"] == "my-docs"


def test_invalid_json(config_dir):
    path = os.path.join(str(config_dir), "selfdoc.json")
    with open(path, "w") as f:
        f.write("{bad json")
    with pytest.raises(ConfigError, match="not valid JSON"):
        load_config(str(config_dir))
