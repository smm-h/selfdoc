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
        "source": [{"path": "src/", "language": "python"}],
        "base_url": "https://example.com",
        "version": "1.0.0",
        "docs": "docs/",
        "output": "docs/_build/",
        "deploy": {"provider": "github-pages"},
        "directives": {},
    })
    cfg = load_config(str(config_dir))
    assert cfg is not None
    assert cfg["source"] == [{"path": "src/", "language": "python"}]
    assert cfg["deploy"]["provider"] == "github-pages"


def test_defaults_applied(config_dir):
    """Optional fields get their defaults when omitted."""
    _write_config(config_dir, {
        "source": [{"path": "pkg/", "language": "go"}],
        "base_url": "https://example.com",
        "version": "1.0.0",
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


def test_missing_source_is_a_codeless_project(config_dir):
    """A config with no 'source' key is a codeless project, not an error."""
    _write_config(config_dir, {"base_url": "https://example.com"})
    config = load_config(str(config_dir))
    assert config["source"] == []


def test_missing_base_url(config_dir):
    _write_config(config_dir, {"source": [{"path": "src/", "language": "python"}]})
    with pytest.raises(ConfigError, match="missing required field 'base_url'"):
        load_config(str(config_dir))


def test_empty_base_url(config_dir):
    _write_config(config_dir, {
        "source": [{"path": "src/", "language": "python"}],
        "base_url": "",
    })
    with pytest.raises(ConfigError, match="'base_url' must be a non-empty string"):
        load_config(str(config_dir))


# -- invalid values --


def test_unsupported_language_accepted_in_config(config_dir):
    """Unsupported language in a source entry is accepted by config loader."""
    _write_config(config_dir, {
        "source": [{"path": "lib/", "language": "ruby"}],
        "base_url": "https://example.com",
        "version": "1.0.0",
    })
    config = load_config(str(config_dir))
    assert config is not None
    assert config["source"][0]["language"] == "ruby"


def test_source_not_a_list(config_dir):
    _write_config(config_dir, {"source": "src/"})
    with pytest.raises(ConfigError, match="'source' must be a list"):
        load_config(str(config_dir))


def test_source_empty_list(config_dir):
    """An explicitly empty 'source' says the same thing as omitting it."""
    _write_config(
        config_dir, {"source": [], "base_url": "https://example.com"},
    )
    config = load_config(str(config_dir))
    assert config["source"] == []


def test_source_item_plain_string_migration_error(config_dir):
    """Source item as a plain string triggers migration error."""
    _write_config(config_dir, {"source": ["src/"], "base_url": "https://example.com"})
    with pytest.raises(ConfigError, match="source\\[0\\] is a plain string"):
        load_config(str(config_dir))


def test_top_level_language_migration_error(config_dir):
    """Top-level 'language' key triggers migration error."""
    _write_config(config_dir, {
        "language": "python",
        "source": [{"path": "src/", "language": "python"}],
        "base_url": "https://example.com",
    })
    with pytest.raises(ConfigError, match="Top-level 'language' field is no longer supported"):
        load_config(str(config_dir))


def test_source_entry_missing_language(config_dir):
    """Source entry missing 'language' raises ConfigError."""
    _write_config(config_dir, {
        "source": [{"path": "src/"}],
        "base_url": "https://example.com",
    })
    with pytest.raises(ConfigError, match="source\\[0\\].language.*required"):
        load_config(str(config_dir))


def test_source_entry_missing_path(config_dir):
    """Source entry missing 'path' raises ConfigError."""
    _write_config(config_dir, {
        "source": [{"language": "python"}],
        "base_url": "https://example.com",
    })
    with pytest.raises(ConfigError, match="source\\[0\\].path.*required"):
        load_config(str(config_dir))


def test_multi_language_source(config_dir):
    """Config with multiple source entries using different languages loads."""
    _write_config(config_dir, {
        "source": [
            {"path": "src/", "language": "python"},
            {"path": "pkg/", "language": "go"},
        ],
        "base_url": "https://example.com",
        "version": "1.0.0",
    })
    cfg = load_config(str(config_dir))
    assert len(cfg["source"]) == 2
    assert cfg["source"][0]["language"] == "python"
    assert cfg["source"][1]["language"] == "go"


# -- deploy validation --


def test_invalid_deploy_provider(config_dir):
    _write_config(config_dir, {
        "source": [{"path": "src/", "language": "typescript"}],
        "base_url": "https://example.com",
        "deploy": {"provider": "netlify"},
    })
    with pytest.raises(ConfigError, match="invalid deploy.provider"):
        load_config(str(config_dir))


def test_cloudflare_requires_project(config_dir):
    _write_config(config_dir, {
        "source": [{"path": "lib/", "language": "typescript"}],
        "base_url": "https://example.com",
        "version": "1.0.0",
        "deploy": {"provider": "cloudflare-pages"},
    })
    with pytest.raises(ConfigError, match="'deploy.project' is required"):
        load_config(str(config_dir))


def test_cloudflare_with_project(config_dir):
    _write_config(config_dir, {
        "source": [{"path": "lib/", "language": "typescript"}],
        "base_url": "https://example.com",
        "version": "1.0.0",
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
        "source": [{"path": "src/", "language": "python"}],
        "base_url": "https://example.com",
        "version": "1.0.0",
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
        "source": [{"path": "src/", "language": "python"}],
        "base_url": "https://example.com",
        "version": "1.0.0",
    })
    cfg = load_config(str(config_dir))
    assert cfg["lang"] is None
    assert cfg["author"] is None
    assert cfg["description"] is None


def test_invalid_lang_empty_string(config_dir):
    _write_config(config_dir, {
        "source": [{"path": "src/", "language": "python"}],
        "base_url": "https://example.com",
        "lang": "",
    })
    with pytest.raises(ConfigError, match="'lang' must be a non-empty string"):
        load_config(str(config_dir))


def test_invalid_author_not_dict(config_dir):
    _write_config(config_dir, {
        "source": [{"path": "src/", "language": "python"}],
        "base_url": "https://example.com",
        "author": "Jane Doe",
    })
    with pytest.raises(ConfigError, match="'author' must be an object"):
        load_config(str(config_dir))


def test_author_missing_name(config_dir):
    _write_config(config_dir, {
        "source": [{"path": "src/", "language": "python"}],
        "base_url": "https://example.com",
        "author": {"url": "https://jane.dev"},
    })
    with pytest.raises(ConfigError, match="'author.name' is required"):
        load_config(str(config_dir))


def test_author_invalid_type(config_dir):
    _write_config(config_dir, {
        "source": [{"path": "src/", "language": "python"}],
        "base_url": "https://example.com",
        "author": {"name": "Jane", "type": "Bot"},
    })
    with pytest.raises(ConfigError, match="invalid author.type"):
        load_config(str(config_dir))


def test_invalid_description_empty_string(config_dir):
    _write_config(config_dir, {
        "source": [{"path": "src/", "language": "python"}],
        "base_url": "https://example.com",
        "description": "",
    })
    with pytest.raises(ConfigError, match="'description' must be a non-empty string"):
        load_config(str(config_dir))


def test_author_name_only(config_dir):
    """Author with only name (no url/type) loads correctly."""
    _write_config(config_dir, {
        "source": [{"path": "src/", "language": "python"}],
        "base_url": "https://example.com",
        "version": "1.0.0",
        "author": {"name": "Jane Doe"},
    })
    cfg = load_config(str(config_dir))
    assert cfg["author"] == {"name": "Jane Doe"}


# -- twitter field --


def test_twitter_in_author(config_dir):
    """Twitter handle in author section is returned in config."""
    _write_config(config_dir, {
        "source": [{"path": "src/", "language": "python"}],
        "base_url": "https://example.com",
        "version": "1.0.0",
        "author": {"name": "Test", "twitter": "@test"},
    })
    cfg = load_config(str(config_dir))
    assert cfg["twitter"] == "@test"


def test_twitter_top_level(config_dir):
    """Top-level twitter handle is returned when author.twitter is absent."""
    _write_config(config_dir, {
        "source": [{"path": "src/", "language": "python"}],
        "base_url": "https://example.com",
        "version": "1.0.0",
        "twitter": "@test",
    })
    cfg = load_config(str(config_dir))
    assert cfg["twitter"] == "@test"


def test_twitter_author_takes_precedence(config_dir):
    """author.twitter takes precedence over top-level twitter."""
    _write_config(config_dir, {
        "source": [{"path": "src/", "language": "python"}],
        "base_url": "https://example.com",
        "version": "1.0.0",
        "author": {"name": "Test", "twitter": "@author_handle"},
        "twitter": "@top_handle",
    })
    cfg = load_config(str(config_dir))
    assert cfg["twitter"] == "@author_handle"


def test_twitter_invalid(config_dir):
    """Twitter handle not starting with '@' raises ConfigError."""
    _write_config(config_dir, {
        "source": [{"path": "src/", "language": "python"}],
        "base_url": "https://example.com",
        "twitter": "test",
    })
    with pytest.raises(ConfigError, match="invalid twitter"):
        load_config(str(config_dir))


# -- BCP 47 lang validation --


@pytest.mark.parametrize("tag", ["en", "en-US", "pt-BR", "zh-Hans"])
def test_valid_bcp47_lang_tags(config_dir, tag):
    """Valid BCP 47 language tags are accepted."""
    _write_config(config_dir, {
        "source": [{"path": "src/", "language": "python"}],
        "base_url": "https://example.com",
        "version": "1.0.0",
        "lang": tag,
    })
    cfg = load_config(str(config_dir))
    assert cfg["lang"] == tag


@pytest.mark.parametrize("tag", ["foobar123", "e", "en_US", "123"])
def test_invalid_bcp47_lang_tags(config_dir, tag):
    """Invalid BCP 47 language tags raise ConfigError."""
    _write_config(config_dir, {
        "source": [{"path": "src/", "language": "python"}],
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
        "source": [{"path": "src/", "language": "python"}],
        "base_url": "https://example.com",
        "version": "1.0.0",
        "search": value,
    })
    cfg = load_config(str(config_dir))
    assert cfg["search"] == value


def test_search_absent_is_none(config_dir):
    """Missing search field defaults to None."""
    _write_config(config_dir, {
        "source": [{"path": "src/", "language": "python"}],
        "base_url": "https://example.com",
        "version": "1.0.0",
    })
    cfg = load_config(str(config_dir))
    assert cfg["search"] is None


def test_search_invalid_value(config_dir):
    """Invalid search value raises ConfigError."""
    _write_config(config_dir, {
        "source": [{"path": "src/", "language": "python"}],
        "base_url": "https://example.com",
        "search": "fullscreen",
    })
    with pytest.raises(ConfigError, match="invalid search value"):
        load_config(str(config_dir))


def test_search_non_string(config_dir):
    """Non-string search value raises ConfigError."""
    _write_config(config_dir, {
        "source": [{"path": "src/", "language": "python"}],
        "base_url": "https://example.com",
        "search": 42,
    })
    with pytest.raises(ConfigError, match="invalid search value"):
        load_config(str(config_dir))


# -- feedback field --


def test_feedback_absent_is_none(config_dir):
    """Missing feedback field defaults to None."""
    _write_config(config_dir, {
        "source": [{"path": "src/", "language": "python"}],
        "base_url": "https://example.com",
        "version": "1.0.0",
    })
    cfg = load_config(str(config_dir))
    assert cfg["feedback"] is None


def test_feedback_webhook_only(config_dir):
    """Feedback with only webhook is valid."""
    _write_config(config_dir, {
        "source": [{"path": "src/", "language": "python"}],
        "base_url": "https://example.com",
        "version": "1.0.0",
        "feedback": {"webhook": "https://hooks.example.com/fb"},
    })
    cfg = load_config(str(config_dir))
    assert cfg["feedback"]["webhook"] == "https://hooks.example.com/fb"


def test_feedback_ga_only(config_dir):
    """Feedback with only ga is valid."""
    _write_config(config_dir, {
        "source": [{"path": "src/", "language": "python"}],
        "base_url": "https://example.com",
        "version": "1.0.0",
        "feedback": {"ga": "G-ABCDEF1234"},
    })
    cfg = load_config(str(config_dir))
    assert cfg["feedback"]["ga"] == "G-ABCDEF1234"


def test_feedback_both_keys(config_dir):
    """Feedback with both webhook and ga is valid."""
    _write_config(config_dir, {
        "source": [{"path": "src/", "language": "python"}],
        "base_url": "https://example.com",
        "version": "1.0.0",
        "feedback": {"webhook": "https://hooks.example.com/fb", "ga": "G-ABCDEF1234"},
    })
    cfg = load_config(str(config_dir))
    assert cfg["feedback"]["webhook"] == "https://hooks.example.com/fb"
    assert cfg["feedback"]["ga"] == "G-ABCDEF1234"


def test_feedback_empty_object(config_dir):
    """Empty feedback object raises ConfigError."""
    _write_config(config_dir, {
        "source": [{"path": "src/", "language": "python"}],
        "base_url": "https://example.com",
        "version": "1.0.0",
        "feedback": {},
    })
    with pytest.raises(ConfigError, match="at least one of 'webhook' or 'ga'"):
        load_config(str(config_dir))


def test_feedback_not_object(config_dir):
    """Non-object feedback raises ConfigError."""
    _write_config(config_dir, {
        "source": [{"path": "src/", "language": "python"}],
        "base_url": "https://example.com",
        "feedback": "yes",
    })
    with pytest.raises(ConfigError, match="'feedback' must be an object"):
        load_config(str(config_dir))


def test_feedback_webhook_non_string(config_dir):
    """Non-string webhook raises ConfigError."""
    _write_config(config_dir, {
        "source": [{"path": "src/", "language": "python"}],
        "base_url": "https://example.com",
        "feedback": {"webhook": 123},
    })
    with pytest.raises(ConfigError, match="'feedback.webhook' must be a string"):
        load_config(str(config_dir))


def test_feedback_webhook_empty_string(config_dir):
    """Empty string webhook raises ConfigError."""
    _write_config(config_dir, {
        "source": [{"path": "src/", "language": "python"}],
        "base_url": "https://example.com",
        "feedback": {"webhook": ""},
    })
    with pytest.raises(ConfigError, match="'feedback.webhook' must be a non-empty string"):
        load_config(str(config_dir))


def test_feedback_ga_non_string(config_dir):
    """Non-string ga raises ConfigError."""
    _write_config(config_dir, {
        "source": [{"path": "src/", "language": "python"}],
        "base_url": "https://example.com",
        "feedback": {"ga": 42},
    })
    with pytest.raises(ConfigError, match="'feedback.ga' must be a string"):
        load_config(str(config_dir))


def test_feedback_ga_empty_string(config_dir):
    """Empty string ga raises ConfigError."""
    _write_config(config_dir, {
        "source": [{"path": "src/", "language": "python"}],
        "base_url": "https://example.com",
        "feedback": {"ga": ""},
    })
    with pytest.raises(ConfigError, match="'feedback.ga' must be a non-empty string"):
        load_config(str(config_dir))


# -- branch field --


def test_branch_valid(config_dir):
    """Valid branch string is accepted."""
    _write_config(config_dir, {
        "source": [{"path": "src/", "language": "python"}],
        "base_url": "https://example.com",
        "version": "1.0.0",
        "branch": "main",
    })
    cfg = load_config(str(config_dir))
    assert cfg["branch"] == "main"


def test_branch_absent_is_none(config_dir):
    """Missing branch field defaults to None."""
    _write_config(config_dir, {
        "source": [{"path": "src/", "language": "python"}],
        "base_url": "https://example.com",
        "version": "1.0.0",
    })
    cfg = load_config(str(config_dir))
    assert cfg["branch"] is None


def test_branch_empty_string(config_dir):
    """Empty string branch raises ConfigError."""
    _write_config(config_dir, {
        "source": [{"path": "src/", "language": "python"}],
        "base_url": "https://example.com",
        "branch": "",
    })
    with pytest.raises(ConfigError, match="'branch' must be a non-empty string"):
        load_config(str(config_dir))


def test_branch_non_string(config_dir):
    """Non-string branch raises ConfigError."""
    _write_config(config_dir, {
        "source": [{"path": "src/", "language": "python"}],
        "base_url": "https://example.com",
        "branch": 42,
    })
    with pytest.raises(ConfigError, match="'branch' must be a string"):
        load_config(str(config_dir))


# -- search_engine field --


@pytest.mark.parametrize("value", ["builtin", "fuse", "minisearch"])
def test_search_engine_valid_values(config_dir, value):
    """Each valid search_engine value is accepted."""
    _write_config(config_dir, {
        "source": [{"path": "src/", "language": "python"}],
        "base_url": "https://example.com",
        "version": "1.0.0",
        "search_engine": value,
    })
    cfg = load_config(str(config_dir))
    assert cfg["search_engine"] == value


def test_search_engine_invalid_value(config_dir):
    """Invalid search_engine value raises ConfigError."""
    _write_config(config_dir, {
        "source": [{"path": "src/", "language": "python"}],
        "base_url": "https://example.com",
        "search_engine": "algolia",
    })
    with pytest.raises(ConfigError, match="invalid search_engine value"):
        load_config(str(config_dir))


def test_search_engine_default_none(config_dir):
    """Missing search_engine defaults to None."""
    _write_config(config_dir, {
        "source": [{"path": "src/", "language": "python"}],
        "base_url": "https://example.com",
        "version": "1.0.0",
    })
    cfg = load_config(str(config_dir))
    assert cfg["search_engine"] is None


# -- branding field --


def test_branding_valid_full(config_dir):
    """Complete branding config with all keys including features."""
    _write_config(config_dir, {
        "source": [{"path": "src/", "language": "python"}],
        "base_url": "https://example.com",
        "version": "1.0.0",
        "branding": {
            "tagline": "Build docs fast",
            "cta_text": "Get Started",
            "cta_link": "/quickstart",
            "logo": "assets/logo.svg",
            "secondary_cta_text": "Learn More",
            "secondary_cta_link": "/guide",
            "features": [
                {"title": "Fast", "description": "Lightning-fast builds"},
                {"title": "Simple", "description": "Zero config needed"},
            ],
        },
    })
    cfg = load_config(str(config_dir))
    assert cfg["branding"]["tagline"] == "Build docs fast"
    assert cfg["branding"]["cta_text"] == "Get Started"
    assert cfg["branding"]["logo"] == "assets/logo.svg"
    assert len(cfg["branding"]["features"]) == 2
    assert cfg["branding"]["features"][0]["title"] == "Fast"


def test_branding_valid_minimal(config_dir):
    """Branding with only tagline is valid."""
    _write_config(config_dir, {
        "source": [{"path": "src/", "language": "python"}],
        "base_url": "https://example.com",
        "version": "1.0.0",
        "branding": {"tagline": "Docs made easy"},
    })
    cfg = load_config(str(config_dir))
    assert cfg["branding"]["tagline"] == "Docs made easy"
    assert "features" not in cfg["branding"]


def test_branding_invalid_not_dict(config_dir):
    """Non-dict branding raises ConfigError."""
    _write_config(config_dir, {
        "source": [{"path": "src/", "language": "python"}],
        "base_url": "https://example.com",
        "branding": "fancy",
    })
    with pytest.raises(ConfigError, match="'branding' must be an object"):
        load_config(str(config_dir))


def test_branding_features_invalid_item(config_dir):
    """Feature item missing title raises ConfigError."""
    _write_config(config_dir, {
        "source": [{"path": "src/", "language": "python"}],
        "base_url": "https://example.com",
        "branding": {
            "features": [
                {"description": "No title here"},
            ],
        },
    })
    with pytest.raises(ConfigError, match="branding.features\\[0\\].title"):
        load_config(str(config_dir))


def test_branding_features_missing_description(config_dir):
    """Feature item missing description raises ConfigError."""
    _write_config(config_dir, {
        "source": [{"path": "src/", "language": "python"}],
        "base_url": "https://example.com",
        "branding": {
            "features": [
                {"title": "Fast"},
            ],
        },
    })
    with pytest.raises(ConfigError, match="branding.features\\[0\\].description"):
        load_config(str(config_dir))


def test_branding_default_none(config_dir):
    """Missing branding defaults to None."""
    _write_config(config_dir, {
        "source": [{"path": "src/", "language": "python"}],
        "base_url": "https://example.com",
        "version": "1.0.0",
    })
    cfg = load_config(str(config_dir))
    assert cfg["branding"] is None


# -- min_coverage removed (now hardcoded to 100%) --


def test_min_coverage_rejected(config_dir):
    """min_coverage is no longer a valid config key."""
    _write_config(config_dir, {
        "source": [{"path": "src/", "language": "python"}],
        "base_url": "https://example.com",
        "min_coverage": 80,
    })
    with pytest.raises(ConfigError, match="unknown config key"):
        load_config(str(config_dir))


# -- glossary field --


def test_glossary_default_true(config_dir):
    """Config without glossary key loads with glossary=True."""
    _write_config(config_dir, {
        "source": [{"path": "src/", "language": "python"}],
        "base_url": "https://example.com",
        "version": "1.0.0",
    })
    cfg = load_config(str(config_dir))
    assert cfg["glossary"] is True


def test_glossary_false(config_dir):
    """Config with glossary=false loads correctly."""
    _write_config(config_dir, {
        "source": [{"path": "src/", "language": "python"}],
        "base_url": "https://example.com",
        "version": "1.0.0",
        "glossary": False,
    })
    cfg = load_config(str(config_dir))
    assert cfg["glossary"] is False


# -- feed_max_entries field --


def test_feed_max_entries_valid(config_dir):
    """Valid integer for feed_max_entries loads correctly."""
    _write_config(config_dir, {
        "source": [{"path": "src/", "language": "python"}],
        "base_url": "https://example.com",
        "version": "1.0.0",
        "feed_max_entries": 10,
    })
    cfg = load_config(str(config_dir))
    assert cfg["feed_max_entries"] == 10


def test_feed_max_entries_zero(config_dir):
    """feed_max_entries=0 is rejected (min_val=1)."""
    _write_config(config_dir, {
        "source": [{"path": "src/", "language": "python"}],
        "base_url": "https://example.com",
        "feed_max_entries": 0,
    })
    with pytest.raises(ConfigError, match="'feed_max_entries' must be an integer"):
        load_config(str(config_dir))


def test_feed_max_entries_default_none(config_dir):
    """Missing feed_max_entries defaults to None."""
    _write_config(config_dir, {
        "source": [{"path": "src/", "language": "python"}],
        "base_url": "https://example.com",
        "version": "1.0.0",
    })
    cfg = load_config(str(config_dir))
    assert cfg["feed_max_entries"] is None


# -- gen_data field --


def test_gen_data_passed_through(config_dir):
    """gen_data with valid scripts is accepted."""
    _write_config(config_dir, {
        "source": [{"path": "src/", "language": "python"}],
        "base_url": "https://example.com",
        "version": "1.0.0",
        "gen_data": {
            "scripts": [
                {"command": "python gen.py", "output": "data/api.json", "mounts": ["/src"]},
            ],
        },
    })
    cfg = load_config(str(config_dir))
    assert cfg["gen_data"]["scripts"][0]["command"] == "python gen.py"


def test_gen_data_absent_is_none(config_dir):
    """Missing gen_data defaults to None."""
    _write_config(config_dir, {
        "source": [{"path": "src/", "language": "python"}],
        "base_url": "https://example.com",
        "version": "1.0.0",
    })
    cfg = load_config(str(config_dir))
    assert cfg["gen_data"] is None


def test_gen_data_not_dict(config_dir):
    """Non-dict gen_data raises ConfigError."""
    _write_config(config_dir, {
        "source": [{"path": "src/", "language": "python"}],
        "base_url": "https://example.com",
        "gen_data": "bad",
    })
    with pytest.raises(ConfigError, match="'gen_data' must be an object"):
        load_config(str(config_dir))


def test_gen_data_scripts_not_list(config_dir):
    """Non-list gen_data.scripts raises ConfigError."""
    _write_config(config_dir, {
        "source": [{"path": "src/", "language": "python"}],
        "base_url": "https://example.com",
        "gen_data": {"scripts": "bad"},
    })
    with pytest.raises(ConfigError, match="'gen_data.scripts' must be a list"):
        load_config(str(config_dir))


def test_gen_data_script_missing_command(config_dir):
    """Script missing 'command' raises ConfigError."""
    _write_config(config_dir, {
        "source": [{"path": "src/", "language": "python"}],
        "base_url": "https://example.com",
        "gen_data": {
            "scripts": [
                {"output": "out.json", "mounts": ["/src"]},
            ],
        },
    })
    with pytest.raises(ConfigError, match="gen_data.scripts\\[0\\].command.*required"):
        load_config(str(config_dir))


def test_gen_data_script_missing_output(config_dir):
    """Script missing 'output' raises ConfigError."""
    _write_config(config_dir, {
        "source": [{"path": "src/", "language": "python"}],
        "base_url": "https://example.com",
        "gen_data": {
            "scripts": [
                {"command": "echo hi", "mounts": ["/src"]},
            ],
        },
    })
    with pytest.raises(ConfigError, match="gen_data.scripts\\[0\\].output.*required"):
        load_config(str(config_dir))


def test_gen_data_script_missing_mounts(config_dir):
    """Script missing 'mounts' raises ConfigError."""
    _write_config(config_dir, {
        "source": [{"path": "src/", "language": "python"}],
        "base_url": "https://example.com",
        "gen_data": {
            "scripts": [
                {"command": "echo hi", "output": "out.json"},
            ],
        },
    })
    with pytest.raises(ConfigError, match="gen_data.scripts\\[0\\].mounts.*required"):
        load_config(str(config_dir))


def test_gen_data_script_command_not_string(config_dir):
    """Non-string command raises ConfigError."""
    _write_config(config_dir, {
        "source": [{"path": "src/", "language": "python"}],
        "base_url": "https://example.com",
        "gen_data": {
            "scripts": [
                {"command": 42, "output": "out.json", "mounts": ["/src"]},
            ],
        },
    })
    with pytest.raises(ConfigError, match="gen_data.scripts\\[0\\].command.*must be a string"):
        load_config(str(config_dir))


def test_gen_data_script_mounts_not_list(config_dir):
    """Non-list mounts raises ConfigError."""
    _write_config(config_dir, {
        "source": [{"path": "src/", "language": "python"}],
        "base_url": "https://example.com",
        "gen_data": {
            "scripts": [
                {"command": "echo hi", "output": "out.json", "mounts": "/src"},
            ],
        },
    })
    with pytest.raises(ConfigError, match="gen_data.scripts\\[0\\].mounts.*must be a list"):
        load_config(str(config_dir))


def test_gen_data_script_mounts_item_not_string(config_dir):
    """Non-string item in mounts raises ConfigError."""
    _write_config(config_dir, {
        "source": [{"path": "src/", "language": "python"}],
        "base_url": "https://example.com",
        "gen_data": {
            "scripts": [
                {"command": "echo hi", "output": "out.json", "mounts": [123]},
            ],
        },
    })
    with pytest.raises(ConfigError, match="mounts.*must be a string"):
        load_config(str(config_dir))


# -- gen field --


def test_gen_valid(config_dir):
    """Valid gen config with exclude list is accepted."""
    _write_config(config_dir, {
        "source": [{"path": "src/", "language": "python"}],
        "base_url": "https://example.com",
        "version": "1.0.0",
        "gen": {"exclude": ["test_*.py", "__pycache__"]},
    })
    cfg = load_config(str(config_dir))
    assert cfg["gen"]["exclude"] == ["test_*.py", "__pycache__"]


def test_gen_absent_is_none(config_dir):
    """Missing gen defaults to None."""
    _write_config(config_dir, {
        "source": [{"path": "src/", "language": "python"}],
        "base_url": "https://example.com",
        "version": "1.0.0",
    })
    cfg = load_config(str(config_dir))
    assert cfg["gen"] is None


def test_gen_not_dict(config_dir):
    """Non-dict gen raises ConfigError."""
    _write_config(config_dir, {
        "source": [{"path": "src/", "language": "python"}],
        "base_url": "https://example.com",
        "gen": "bad",
    })
    with pytest.raises(ConfigError, match="'gen' must be an object"):
        load_config(str(config_dir))


def test_gen_exclude_not_list(config_dir):
    """Non-list gen.exclude raises ConfigError."""
    _write_config(config_dir, {
        "source": [{"path": "src/", "language": "python"}],
        "base_url": "https://example.com",
        "gen": {"exclude": "*.pyc"},
    })
    with pytest.raises(ConfigError, match="'gen.exclude' must be a list"):
        load_config(str(config_dir))


def test_gen_exclude_item_not_string(config_dir):
    """Non-string item in gen.exclude raises ConfigError."""
    _write_config(config_dir, {
        "source": [{"path": "src/", "language": "python"}],
        "base_url": "https://example.com",
        "gen": {"exclude": [42]},
    })
    with pytest.raises(ConfigError, match="gen.exclude\\[0\\].*must be a string"):
        load_config(str(config_dir))


def test_gen_invalid_key(config_dir):
    """Unknown keys in gen are rejected."""
    _write_config(config_dir, {
        "source": [{"path": "src/", "language": "python"}],
        "base_url": "https://example.com",
        "gen": {"exclude": [], "bogus": True},
    })
    with pytest.raises(ConfigError, match="invalid gen key 'bogus'"):
        load_config(str(config_dir))


def test_gen_data_invalid_key(config_dir):
    """Unknown keys in gen_data are rejected."""
    _write_config(config_dir, {
        "source": [{"path": "src/", "language": "python"}],
        "base_url": "https://example.com",
        "gen_data": {"scripts": [], "timeout": 30},
    })
    with pytest.raises(ConfigError, match="invalid gen_data key 'timeout'"):
        load_config(str(config_dir))


# -- top-level name key --


def test_top_level_name_accepted(config_dir):
    """An explicit top-level ``name`` key loads and round-trips."""
    _write_config(config_dir, {
        "source": [{"path": "src/", "language": "python"}],
        "base_url": "https://example.com",
        "version": "1.0.0",
        "name": "MyProject",
    })
    cfg = load_config(str(config_dir))
    assert cfg["name"] == "MyProject"


def test_name_optional_defaults_none(config_dir):
    """``name`` is optional; when omitted it is absent/None, not required."""
    _write_config(config_dir, {
        "source": [{"path": "src/", "language": "python"}],
        "base_url": "https://example.com",
        "version": "1.0.0",
    })
    cfg = load_config(str(config_dir))
    assert cfg.get("name") is None


# -- unknown top-level keys --


def test_unknown_top_level_key(config_dir):
    """Unknown top-level key raises ConfigError mentioning the key name."""
    _write_config(config_dir, {
        "source": [{"path": "src/", "language": "python"}],
        "base_url": "https://example.com",
        "foo": "bar",
    })
    with pytest.raises(ConfigError, match="foo"):
        load_config(str(config_dir))


def test_name_does_not_disable_unknown_key_rejection(config_dir):
    """Adding ``name`` does not weaken unknown-key rejection."""
    _write_config(config_dir, {
        "source": [{"path": "src/", "language": "python"}],
        "base_url": "https://example.com",
        "name": "MyProject",
        "bogus": 1,
    })
    with pytest.raises(ConfigError, match="bogus"):
        load_config(str(config_dir))


# -- root_files field --


def test_root_files_valid(config_dir):
    """Valid root_files list is accepted and present in loaded config."""
    _write_config(config_dir, {
        "source": [{"path": "src/", "language": "python"}],
        "base_url": "https://example.com",
        "version": "1.0.0",
        "root_files": ["docs/_CLAUDE.md"],
    })
    cfg = load_config(str(config_dir))
    assert isinstance(cfg["root_files"], list)
    assert cfg["root_files"] == ["docs/_CLAUDE.md"]


def test_root_files_invalid_item(config_dir):
    """Non-string item in root_files raises ConfigError."""
    _write_config(config_dir, {
        "source": [{"path": "src/", "language": "python"}],
        "base_url": "https://example.com",
        "root_files": [123],
    })
    with pytest.raises(ConfigError):
        load_config(str(config_dir))


# -- lint_ignore field --


def test_lint_ignore_registered_codes_load(config_dir):
    """A suppression list of registered lint codes loads unchanged."""
    _write_config(config_dir, {
        "source": [{"path": "src/", "language": "python"}],
        "base_url": "https://example.com",
        "lint_ignore": ["SEO007", "SEO008"],
    })
    cfg = load_config(str(config_dir))
    assert cfg["lint_ignore"] == ["SEO007", "SEO008"]


def test_lint_ignore_unregistered_code_is_a_hard_error(config_dir):
    """A code the registry does not carry would suppress nothing -- refuse it."""
    _write_config(config_dir, {
        "source": [{"path": "src/", "language": "python"}],
        "base_url": "https://example.com",
        "lint_ignore": ["SEO007", "SEO0O8"],
    })
    with pytest.raises(ConfigError) as excinfo:
        load_config(str(config_dir))
    assert "SEO0O8" in str(excinfo.value)
    assert "lint_ignore" in str(excinfo.value)


# -- cross-project config validation --

_CROSS_PROJECT_CONFIGS = [
    "/home/m/Projects/claudestream/selfdoc.json",
    "/home/m/Projects/claudewheel/selfdoc.json",
    "/home/m/Projects/codehome/selfdoc.json",
    "/home/m/Projects/go-toml-edit/selfdoc.json",
    "/home/m/Projects/howmuchleft/selfdoc.json",
    "/home/m/Projects/predraw/selfdoc.json",
    "/home/m/Projects/rlsbl/selfdoc.json",
    "/home/m/Projects/safegit/selfdoc.json",
    "/home/m/Projects/saferm/selfdoc.json",
    "/home/m/Projects/selfdoc/selfdoc.json",
    "/home/m/Projects/WWW/selfdoc.json",
]


@pytest.mark.parametrize(
    "config_path",
    _CROSS_PROJECT_CONFIGS,
    ids=[os.path.basename(os.path.dirname(p)) for p in _CROSS_PROJECT_CONFIGS],
)
def test_cross_project_config_loads(config_path):
    """Each real selfdoc.json across all consumer projects loads without error."""
    if not os.path.isfile(config_path):
        pytest.skip(f"{config_path} not found")
    # Skip projects that haven't migrated to multi-language source format yet
    with open(config_path, "r", encoding="utf-8") as f:
        import json as _json
        raw = _json.load(f)
    if "language" in raw:
        pytest.skip(f"{config_path} still uses old top-level 'language' format")
    if "assembly" in (raw.get("topology") or {}):
        pytest.skip(f"{config_path} still uses the retired 'topology.assembly' key")
    if any("indexed" in entry for entry in (raw.get("versions") or [])):
        pytest.skip(
            f"{config_path} still declares the retired per-version 'indexed' "
            f"flag; the fleet sweep removes it"
        )
    cfg = load_config(os.path.dirname(config_path))
    assert isinstance(cfg, dict)


# -- version field --


def test_version_valid(config_dir):
    """Valid semver version string is accepted."""
    _write_config(config_dir, {
        "source": [{"path": "src/", "language": "python"}],
        "base_url": "https://example.com",
        "version": "1.2.3",
    })
    cfg = load_config(str(config_dir))
    assert cfg["version"] == "1.2.3"


def test_version_absent_is_none(config_dir):
    """Missing version field defaults to None."""
    _write_config(config_dir, {
        "source": [{"path": "src/", "language": "python"}],
        "base_url": "https://example.com",
    })
    cfg = load_config(str(config_dir))
    assert cfg["version"] is None


def test_version_invalid_pattern(config_dir):
    """Version not matching semver pattern raises ConfigError."""
    _write_config(config_dir, {
        "source": [{"path": "src/", "language": "python"}],
        "base_url": "https://example.com",
        "version": "abc",
    })
    with pytest.raises(ConfigError, match="invalid version"):
        load_config(str(config_dir))


def test_version_non_string(config_dir):
    """Non-string version raises ConfigError."""
    _write_config(config_dir, {
        "source": [{"path": "src/", "language": "python"}],
        "base_url": "https://example.com",
        "version": 123,
    })
    with pytest.raises(ConfigError, match="'version' must be a string"):
        load_config(str(config_dir))


# -- coverage_threshold --


def test_coverage_threshold_default(config_dir):
    """coverage_threshold defaults to 1.0 when omitted."""
    _write_config(config_dir, {
        "source": [{"path": "src/", "language": "python"}],
        "base_url": "https://example.com",
    })
    cfg = load_config(str(config_dir))
    assert cfg["coverage_threshold"] == 1.0


def test_coverage_threshold_valid_float(config_dir):
    """coverage_threshold accepts a float between 0.0 and 1.0."""
    _write_config(config_dir, {
        "source": [{"path": "src/", "language": "python"}],
        "base_url": "https://example.com",
        "coverage_threshold": 0.7,
    })
    cfg = load_config(str(config_dir))
    assert cfg["coverage_threshold"] == 0.7


def test_coverage_threshold_accepts_int_zero(config_dir):
    """coverage_threshold accepts integer 0 (coerced to 0.0)."""
    _write_config(config_dir, {
        "source": [{"path": "src/", "language": "python"}],
        "base_url": "https://example.com",
        "coverage_threshold": 0,
    })
    cfg = load_config(str(config_dir))
    assert cfg["coverage_threshold"] == 0.0


def test_coverage_threshold_accepts_int_one(config_dir):
    """coverage_threshold accepts integer 1 (coerced to 1.0)."""
    _write_config(config_dir, {
        "source": [{"path": "src/", "language": "python"}],
        "base_url": "https://example.com",
        "coverage_threshold": 1,
    })
    cfg = load_config(str(config_dir))
    assert cfg["coverage_threshold"] == 1.0


def test_coverage_threshold_too_high(config_dir):
    """coverage_threshold > 1.0 raises ConfigError."""
    _write_config(config_dir, {
        "source": [{"path": "src/", "language": "python"}],
        "base_url": "https://example.com",
        "coverage_threshold": 1.5,
    })
    with pytest.raises(ConfigError, match="must be a number between"):
        load_config(str(config_dir))


def test_coverage_threshold_negative(config_dir):
    """coverage_threshold < 0.0 raises ConfigError."""
    _write_config(config_dir, {
        "source": [{"path": "src/", "language": "python"}],
        "base_url": "https://example.com",
        "coverage_threshold": -0.1,
    })
    with pytest.raises(ConfigError, match="must be a number between"):
        load_config(str(config_dir))


def test_coverage_threshold_not_a_number(config_dir):
    """coverage_threshold as string raises ConfigError."""
    _write_config(config_dir, {
        "source": [{"path": "src/", "language": "python"}],
        "base_url": "https://example.com",
        "coverage_threshold": "high",
    })
    with pytest.raises(ConfigError, match="must be a number"):
        load_config(str(config_dir))


def test_coverage_threshold_bool_rejected(config_dir):
    """coverage_threshold as bool raises ConfigError (bool is not a number)."""
    _write_config(config_dir, {
        "source": [{"path": "src/", "language": "python"}],
        "base_url": "https://example.com",
        "coverage_threshold": True,
    })
    with pytest.raises(ConfigError, match="must be a number"):
        load_config(str(config_dir))


