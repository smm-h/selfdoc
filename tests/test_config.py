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
        "base_url": "https://example.com",
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
        "base_url": "https://example.com",
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


def test_missing_base_url(config_dir):
    _write_config(config_dir, {"language": "python", "source": ["src/"]})
    with pytest.raises(ConfigError, match="'base_url' is required"):
        load_config(str(config_dir))


def test_empty_base_url(config_dir):
    _write_config(config_dir, {"language": "python", "source": ["src/"], "base_url": ""})
    with pytest.raises(ConfigError, match="'base_url' must be a non-empty string"):
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
        "base_url": "https://example.com",
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


# -- lang, author, description fields --


def test_all_new_fields_present(config_dir):
    """Config with lang, author, and description loads correctly."""
    _write_config(config_dir, {
        "language": "python",
        "source": ["src/"],
        "base_url": "https://example.com",
        "lang": "en",
        "author": {"name": "Jane Doe", "url": "https://jane.dev", "type": "Person"},
        "description": "A great project",
    })
    cfg = load_config(str(config_dir))
    assert cfg["lang"] == "en"
    assert cfg["author"]["name"] == "Jane Doe"
    assert cfg["author"]["url"] == "https://jane.dev"
    assert cfg["author"]["type"] == "Person"
    assert cfg["description"] == "A great project"


def test_new_fields_absent_backward_compat(config_dir):
    """Config without lang, author, description still loads (all None)."""
    _write_config(config_dir, {
        "language": "python",
        "source": ["src/"],
        "base_url": "https://example.com",
    })
    cfg = load_config(str(config_dir))
    assert cfg["lang"] is None
    assert cfg["author"] is None
    assert cfg["description"] is None


def test_invalid_lang_empty_string(config_dir):
    _write_config(config_dir, {
        "language": "python",
        "source": ["src/"],
        "base_url": "https://example.com",
        "lang": "",
    })
    with pytest.raises(ConfigError, match="'lang' must be a non-empty string"):
        load_config(str(config_dir))


def test_invalid_author_not_dict(config_dir):
    _write_config(config_dir, {
        "language": "python",
        "source": ["src/"],
        "base_url": "https://example.com",
        "author": "Jane Doe",
    })
    with pytest.raises(ConfigError, match="'author' must be an object"):
        load_config(str(config_dir))


def test_author_missing_name(config_dir):
    _write_config(config_dir, {
        "language": "python",
        "source": ["src/"],
        "base_url": "https://example.com",
        "author": {"url": "https://jane.dev"},
    })
    with pytest.raises(ConfigError, match="'author.name' is required"):
        load_config(str(config_dir))


def test_author_invalid_type(config_dir):
    _write_config(config_dir, {
        "language": "python",
        "source": ["src/"],
        "base_url": "https://example.com",
        "author": {"name": "Jane", "type": "Bot"},
    })
    with pytest.raises(ConfigError, match="'author.type' must be 'Person' or 'Organization'"):
        load_config(str(config_dir))


def test_invalid_description_empty_string(config_dir):
    _write_config(config_dir, {
        "language": "python",
        "source": ["src/"],
        "base_url": "https://example.com",
        "description": "",
    })
    with pytest.raises(ConfigError, match="'description' must be a non-empty string"):
        load_config(str(config_dir))


def test_author_name_only(config_dir):
    """Author with only name (no url/type) loads correctly."""
    _write_config(config_dir, {
        "language": "python",
        "source": ["src/"],
        "base_url": "https://example.com",
        "author": {"name": "Jane Doe"},
    })
    cfg = load_config(str(config_dir))
    assert cfg["author"] == {"name": "Jane Doe"}


# -- twitter field --


def test_twitter_in_author(config_dir):
    """Twitter handle in author section is returned in config."""
    _write_config(config_dir, {
        "language": "python",
        "source": ["src/"],
        "base_url": "https://example.com",
        "author": {"name": "Test", "twitter": "@test"},
    })
    cfg = load_config(str(config_dir))
    assert cfg["twitter"] == "@test"


def test_twitter_top_level(config_dir):
    """Top-level twitter handle is returned when author.twitter is absent."""
    _write_config(config_dir, {
        "language": "python",
        "source": ["src/"],
        "base_url": "https://example.com",
        "twitter": "@test",
    })
    cfg = load_config(str(config_dir))
    assert cfg["twitter"] == "@test"


def test_twitter_author_takes_precedence(config_dir):
    """author.twitter takes precedence over top-level twitter."""
    _write_config(config_dir, {
        "language": "python",
        "source": ["src/"],
        "base_url": "https://example.com",
        "author": {"name": "Test", "twitter": "@author_handle"},
        "twitter": "@top_handle",
    })
    cfg = load_config(str(config_dir))
    assert cfg["twitter"] == "@author_handle"


def test_twitter_invalid(config_dir):
    """Twitter handle not starting with '@' raises ConfigError."""
    _write_config(config_dir, {
        "language": "python",
        "source": ["src/"],
        "base_url": "https://example.com",
        "twitter": "test",
    })
    with pytest.raises(ConfigError, match="'twitter' must start with '@'"):
        load_config(str(config_dir))


# -- BCP 47 lang validation --


@pytest.mark.parametrize("tag", ["en", "en-US", "pt-BR", "zh-Hans"])
def test_valid_bcp47_lang_tags(config_dir, tag):
    """Valid BCP 47 language tags are accepted."""
    _write_config(config_dir, {
        "language": "python",
        "source": ["src/"],
        "base_url": "https://example.com",
        "lang": tag,
    })
    cfg = load_config(str(config_dir))
    assert cfg["lang"] == tag


@pytest.mark.parametrize("tag", ["foobar123", "e", "en_US", "123"])
def test_invalid_bcp47_lang_tags(config_dir, tag):
    """Invalid BCP 47 language tags raise ConfigError."""
    _write_config(config_dir, {
        "language": "python",
        "source": ["src/"],
        "base_url": "https://example.com",
        "lang": tag,
    })
    with pytest.raises(ConfigError, match="invalid lang"):
        load_config(str(config_dir))


# -- search field --


@pytest.mark.parametrize("value", ["icon", "bar", "hidden"])
def test_search_valid_values(config_dir, value):
    """Valid search values are accepted."""
    _write_config(config_dir, {
        "language": "python",
        "source": ["src/"],
        "base_url": "https://example.com",
        "search": value,
    })
    cfg = load_config(str(config_dir))
    assert cfg["search"] == value


def test_search_absent_is_none(config_dir):
    """Missing search field defaults to None."""
    _write_config(config_dir, {
        "language": "python",
        "source": ["src/"],
        "base_url": "https://example.com",
    })
    cfg = load_config(str(config_dir))
    assert cfg["search"] is None


def test_search_invalid_value(config_dir):
    """Invalid search value raises ConfigError."""
    _write_config(config_dir, {
        "language": "python",
        "source": ["src/"],
        "base_url": "https://example.com",
        "search": "fullscreen",
    })
    with pytest.raises(ConfigError, match="invalid search value"):
        load_config(str(config_dir))


def test_search_non_string(config_dir):
    """Non-string search value raises ConfigError."""
    _write_config(config_dir, {
        "language": "python",
        "source": ["src/"],
        "base_url": "https://example.com",
        "search": 42,
    })
    with pytest.raises(ConfigError, match="invalid search value"):
        load_config(str(config_dir))


# -- feedback field --


def test_feedback_absent_is_none(config_dir):
    """Missing feedback field defaults to None."""
    _write_config(config_dir, {
        "language": "python",
        "source": ["src/"],
        "base_url": "https://example.com",
    })
    cfg = load_config(str(config_dir))
    assert cfg["feedback"] is None


def test_feedback_webhook_only(config_dir):
    """Feedback with only webhook is valid."""
    _write_config(config_dir, {
        "language": "python",
        "source": ["src/"],
        "base_url": "https://example.com",
        "feedback": {"webhook": "https://hooks.example.com/fb"},
    })
    cfg = load_config(str(config_dir))
    assert cfg["feedback"]["webhook"] == "https://hooks.example.com/fb"


def test_feedback_ga_only(config_dir):
    """Feedback with only ga is valid."""
    _write_config(config_dir, {
        "language": "python",
        "source": ["src/"],
        "base_url": "https://example.com",
        "feedback": {"ga": "G-ABCDEF1234"},
    })
    cfg = load_config(str(config_dir))
    assert cfg["feedback"]["ga"] == "G-ABCDEF1234"


def test_feedback_both_keys(config_dir):
    """Feedback with both webhook and ga is valid."""
    _write_config(config_dir, {
        "language": "python",
        "source": ["src/"],
        "base_url": "https://example.com",
        "feedback": {"webhook": "https://hooks.example.com/fb", "ga": "G-ABCDEF1234"},
    })
    cfg = load_config(str(config_dir))
    assert cfg["feedback"]["webhook"] == "https://hooks.example.com/fb"
    assert cfg["feedback"]["ga"] == "G-ABCDEF1234"


def test_feedback_empty_object(config_dir):
    """Empty feedback object raises ConfigError."""
    _write_config(config_dir, {
        "language": "python",
        "source": ["src/"],
        "base_url": "https://example.com",
        "feedback": {},
    })
    with pytest.raises(ConfigError, match="at least one of 'webhook' or 'ga'"):
        load_config(str(config_dir))


def test_feedback_not_object(config_dir):
    """Non-object feedback raises ConfigError."""
    _write_config(config_dir, {
        "language": "python",
        "source": ["src/"],
        "base_url": "https://example.com",
        "feedback": "yes",
    })
    with pytest.raises(ConfigError, match="'feedback' must be an object"):
        load_config(str(config_dir))


def test_feedback_webhook_non_string(config_dir):
    """Non-string webhook raises ConfigError."""
    _write_config(config_dir, {
        "language": "python",
        "source": ["src/"],
        "base_url": "https://example.com",
        "feedback": {"webhook": 123},
    })
    with pytest.raises(ConfigError, match="'feedback.webhook' must be a non-empty string"):
        load_config(str(config_dir))


def test_feedback_webhook_empty_string(config_dir):
    """Empty string webhook raises ConfigError."""
    _write_config(config_dir, {
        "language": "python",
        "source": ["src/"],
        "base_url": "https://example.com",
        "feedback": {"webhook": ""},
    })
    with pytest.raises(ConfigError, match="'feedback.webhook' must be a non-empty string"):
        load_config(str(config_dir))


def test_feedback_ga_non_string(config_dir):
    """Non-string ga raises ConfigError."""
    _write_config(config_dir, {
        "language": "python",
        "source": ["src/"],
        "base_url": "https://example.com",
        "feedback": {"ga": 42},
    })
    with pytest.raises(ConfigError, match="'feedback.ga' must be a non-empty string"):
        load_config(str(config_dir))


def test_feedback_ga_empty_string(config_dir):
    """Empty string ga raises ConfigError."""
    _write_config(config_dir, {
        "language": "python",
        "source": ["src/"],
        "base_url": "https://example.com",
        "feedback": {"ga": ""},
    })
    with pytest.raises(ConfigError, match="'feedback.ga' must be a non-empty string"):
        load_config(str(config_dir))


# -- branch field --


def test_branch_valid(config_dir):
    """Valid branch string is accepted."""
    _write_config(config_dir, {
        "language": "python",
        "source": ["src/"],
        "base_url": "https://example.com",
        "branch": "main",
    })
    cfg = load_config(str(config_dir))
    assert cfg["branch"] == "main"


def test_branch_absent_is_none(config_dir):
    """Missing branch field defaults to None."""
    _write_config(config_dir, {
        "language": "python",
        "source": ["src/"],
        "base_url": "https://example.com",
    })
    cfg = load_config(str(config_dir))
    assert cfg["branch"] is None


def test_branch_empty_string(config_dir):
    """Empty string branch raises ConfigError."""
    _write_config(config_dir, {
        "language": "python",
        "source": ["src/"],
        "base_url": "https://example.com",
        "branch": "",
    })
    with pytest.raises(ConfigError, match="'branch' must be a non-empty string"):
        load_config(str(config_dir))


def test_branch_non_string(config_dir):
    """Non-string branch raises ConfigError."""
    _write_config(config_dir, {
        "language": "python",
        "source": ["src/"],
        "base_url": "https://example.com",
        "branch": 42,
    })
    with pytest.raises(ConfigError, match="'branch' must be a non-empty string"):
        load_config(str(config_dir))
