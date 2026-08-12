"""Tests for versions, locales, and unified config fields."""

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
    "version": "1.0.0",
}


def _cfg(**extra):
    """Return a valid base config merged with *extra* keys."""
    return {**_BASE, **extra}


# -- all three absent --


def test_all_new_fields_absent(config_dir):
    """Config without versions, locales, unified loads with None values."""
    _write_config(config_dir, _cfg())
    cfg = load_config(str(config_dir))
    assert cfg["versions"] is None
    assert cfg["locales"] is None
    assert cfg["unified"] is None


# -- versions: happy path --


def test_versions_valid(config_dir):
    """Config with valid versions list loads correctly."""
    _write_config(config_dir, _cfg(versions=[
        {"version": "1.0"},
        {"version": "2.0", "projects": {"core": "2.0.1"}},
    ]))
    cfg = load_config(str(config_dir))
    assert len(cfg["versions"]) == 2
    assert cfg["versions"][0]["version"] == "1.0"
    assert cfg["versions"][1]["projects"]["core"] == "2.0.1"


# -- versions: errors --


def test_versions_duplicate_version_strings(config_dir):
    """Duplicate version strings raise ConfigError."""
    _write_config(config_dir, _cfg(versions=[
        {"version": "1.0"},
        {"version": "1.0"},
    ]))
    with pytest.raises(ConfigError, match="duplicate version string '1.0'"):
        load_config(str(config_dir))


def test_versions_entry_rejects_indexed(config_dir):
    """The per-version 'indexed' flag is gone: whether a version is an archive
    subsumes it, so declaring the key is a hard error rather than a no-op."""
    _write_config(config_dir, _cfg(versions=[
        {"version": "1.0", "indexed": True},
    ]))
    with pytest.raises(ConfigError, match="indexed"):
        load_config(str(config_dir))


def test_versions_entry_missing_version(config_dir):
    """Version entry missing 'version' raises ConfigError."""
    _write_config(config_dir, _cfg(versions=[
        {"projects": {"core": "1.0"}},
    ]))
    with pytest.raises(ConfigError, match="versions\\[0\\].version.*required"):
        load_config(str(config_dir))


def test_versions_entry_unknown_key(config_dir):
    """Unknown key in version entry is rejected (strict_keys)."""
    _write_config(config_dir, _cfg(versions=[
        {"version": "1.0", "bogus": "val"},
    ]))
    with pytest.raises(ConfigError, match="invalid.*key 'bogus'"):
        load_config(str(config_dir))


# -- locales: happy path --


def test_locales_valid(config_dir):
    """Config with valid locales list loads correctly."""
    _write_config(config_dir, _cfg(locales=[
        {"code": "en", "label": "English", "default": True},
        {"code": "fa", "label": "Farsi", "rtl": True},
    ]))
    cfg = load_config(str(config_dir))
    assert len(cfg["locales"]) == 2
    assert cfg["locales"][0]["code"] == "en"
    assert cfg["locales"][0]["default"] is True
    assert cfg["locales"][1]["rtl"] is True


def test_locales_with_script_subtag(config_dir):
    """Locale code with script subtag (e.g. zh-Hans) is accepted."""
    _write_config(config_dir, _cfg(locales=[
        {"code": "zh-Hans", "label": "Simplified Chinese"},
    ]))
    cfg = load_config(str(config_dir))
    assert cfg["locales"][0]["code"] == "zh-Hans"


def test_locales_with_region_subtag(config_dir):
    """Locale code with region subtag (e.g. pt-BR) is accepted."""
    _write_config(config_dir, _cfg(locales=[
        {"code": "pt-BR", "label": "Brazilian Portuguese"},
    ]))
    cfg = load_config(str(config_dir))
    assert cfg["locales"][0]["code"] == "pt-BR"


def test_locales_with_script_and_region(config_dir):
    """Locale code with both script and region (e.g. zh-Hans-CN) is accepted."""
    _write_config(config_dir, _cfg(locales=[
        {"code": "zh-Hans-CN", "label": "Chinese (Simplified, China)"},
    ]))
    cfg = load_config(str(config_dir))
    assert cfg["locales"][0]["code"] == "zh-Hans-CN"


# -- locales: errors --


def test_locales_duplicate_codes(config_dir):
    """Duplicate locale codes raise ConfigError."""
    _write_config(config_dir, _cfg(locales=[
        {"code": "en", "label": "English"},
        {"code": "en", "label": "English (US)"},
    ]))
    with pytest.raises(ConfigError, match="duplicate locale code 'en'"):
        load_config(str(config_dir))


def test_locales_two_defaults(config_dir):
    """Two locales with default=true raises ConfigError."""
    _write_config(config_dir, _cfg(locales=[
        {"code": "en", "label": "English", "default": True},
        {"code": "fr", "label": "French", "default": True},
    ]))
    with pytest.raises(ConfigError, match="at most one locale may have 'default: true'"):
        load_config(str(config_dir))


def test_locales_entry_missing_code(config_dir):
    """Locale entry missing 'code' raises ConfigError."""
    _write_config(config_dir, _cfg(locales=[
        {"label": "English"},
    ]))
    with pytest.raises(ConfigError, match="locales\\[0\\].code.*required"):
        load_config(str(config_dir))


def test_locales_entry_missing_label(config_dir):
    """Locale entry missing 'label' raises ConfigError."""
    _write_config(config_dir, _cfg(locales=[
        {"code": "en"},
    ]))
    with pytest.raises(ConfigError, match="locales\\[0\\].label.*required"):
        load_config(str(config_dir))


def test_locales_invalid_code_pattern(config_dir):
    """Locale code not matching BCP 47 pattern raises ConfigError."""
    _write_config(config_dir, _cfg(locales=[
        {"code": "en_US", "label": "English US"},
    ]))
    with pytest.raises(ConfigError, match="invalid locales\\[0\\].code"):
        load_config(str(config_dir))


# -- unified: happy path --


def test_unified_valid(config_dir):
    """Config with valid unified dict loads correctly."""
    _write_config(config_dir, _cfg(unified={
        "projects": [
            {"path": "packages/core", "slug": "core", "nav_title": "Core"},
            {"path": "packages/cli"},
        ],
        "exclude": ["*.test.*"],
    }))
    cfg = load_config(str(config_dir))
    assert len(cfg["unified"]["projects"]) == 2
    assert cfg["unified"]["projects"][0]["slug"] == "core"
    assert cfg["unified"]["exclude"] == ["*.test.*"]


def test_unified_slug_derived_from_path(config_dir):
    """When slug is absent, it derives from path basename for uniqueness check."""
    _write_config(config_dir, _cfg(unified={
        "projects": [
            {"path": "packages/core"},
            {"path": "packages/cli"},
        ],
    }))
    cfg = load_config(str(config_dir))
    assert len(cfg["unified"]["projects"]) == 2


# -- unified: errors --


def test_unified_duplicate_slugs_explicit(config_dir):
    """Duplicate explicit slugs in unified.projects raise ConfigError."""
    _write_config(config_dir, _cfg(unified={
        "projects": [
            {"path": "a", "slug": "same"},
            {"path": "b", "slug": "same"},
        ],
    }))
    with pytest.raises(ConfigError, match="duplicate project slug 'same'"):
        load_config(str(config_dir))


def test_unified_duplicate_slugs_derived(config_dir):
    """Duplicate derived slugs (same path basename) raise ConfigError."""
    _write_config(config_dir, _cfg(unified={
        "projects": [
            {"path": "org1/core"},
            {"path": "org2/core"},
        ],
    }))
    with pytest.raises(ConfigError, match="duplicate project slug 'core'"):
        load_config(str(config_dir))


def test_unified_project_missing_path(config_dir):
    """Unified project entry missing 'path' raises ConfigError."""
    _write_config(config_dir, _cfg(unified={
        "projects": [
            {"slug": "core"},
        ],
    }))
    with pytest.raises(ConfigError, match="unified.projects\\[0\\].path.*required"):
        load_config(str(config_dir))


def test_unified_unknown_key(config_dir):
    """Unknown key in unified dict is rejected (strict_keys)."""
    _write_config(config_dir, _cfg(unified={
        "projects": [{"path": "a"}],
        "bogus": True,
    }))
    with pytest.raises(ConfigError, match="invalid unified key 'bogus'"):
        load_config(str(config_dir))


def test_unified_project_unknown_key(config_dir):
    """Unknown key in unified project entry is rejected (strict_keys)."""
    _write_config(config_dir, _cfg(unified={
        "projects": [{"path": "a", "bogus": True}],
    }))
    with pytest.raises(ConfigError, match="invalid.*key 'bogus'"):
        load_config(str(config_dir))


# -- redirects: happy path --


def test_redirects_valid(config_dir):
    """Valid redirects list is accepted."""
    _write_config(config_dir, _cfg(redirects=[
        {"from": "edit-release", "to": "release/edit"},
        {"from": "old-page", "to": "new-page"},
    ]))
    cfg = load_config(str(config_dir))
    assert len(cfg["redirects"]) == 2
    assert cfg["redirects"][0]["from"] == "edit-release"
    assert cfg["redirects"][0]["to"] == "release/edit"


def test_redirects_empty_list(config_dir):
    """Empty redirects list is accepted."""
    _write_config(config_dir, _cfg(redirects=[]))
    cfg = load_config(str(config_dir))
    assert cfg["redirects"] == []


def test_redirects_absent(config_dir):
    """Absent redirects defaults to empty list."""
    _write_config(config_dir, _cfg())
    cfg = load_config(str(config_dir))
    assert cfg["redirects"] == []


# -- redirects: validation errors --


def test_redirects_missing_from(config_dir):
    """Redirect entry missing 'from' raises ConfigError."""
    _write_config(config_dir, _cfg(redirects=[
        {"to": "new-page"},
    ]))
    with pytest.raises(ConfigError, match="redirects\\[0\\].from.*required"):
        load_config(str(config_dir))


def test_redirects_missing_to(config_dir):
    """Redirect entry missing 'to' raises ConfigError."""
    _write_config(config_dir, _cfg(redirects=[
        {"from": "old-page"},
    ]))
    with pytest.raises(ConfigError, match="redirects\\[0\\].to.*required"):
        load_config(str(config_dir))


def test_redirects_unknown_key(config_dir):
    """Unknown key in redirect entry is rejected (strict_keys)."""
    _write_config(config_dir, _cfg(redirects=[
        {"from": "a", "to": "b", "bogus": True},
    ]))
    with pytest.raises(ConfigError, match="invalid.*key 'bogus'"):
        load_config(str(config_dir))


# -- examples: per-language validator command templates --


def test_examples_absent(config_dir):
    """Config without 'examples' loads with None (feature off)."""
    _write_config(config_dir, _cfg())
    cfg = load_config(str(config_dir))
    assert cfg["examples"] is None


def test_examples_valid(config_dir):
    """A language -> command template mapping loads verbatim."""
    _write_config(config_dir, _cfg(examples={
        "python": "uv run --directory python python {file}",
        "go": "scripts/validate-example-go.sh {file}",
    }))
    cfg = load_config(str(config_dir))
    assert cfg["examples"] == {
        "python": "uv run --directory python python {file}",
        "go": "scripts/validate-example-go.sh {file}",
    }


def test_examples_missing_file_placeholder(config_dir):
    """A command template without '{file}' is rejected at load."""
    _write_config(config_dir, _cfg(examples={"python": "python -c pass"}))
    with pytest.raises(ConfigError, match=r"examples\.python.*\{file\}"):
        load_config(str(config_dir))


def test_examples_non_string_command(config_dir):
    """A non-string command template is rejected at load."""
    _write_config(config_dir, _cfg(examples={"python": ["python", "{file}"]}))
    with pytest.raises(ConfigError, match=r"examples\.python.*string"):
        load_config(str(config_dir))


def test_examples_empty_command(config_dir):
    """An empty command template is rejected at load."""
    _write_config(config_dir, _cfg(examples={"python": ""}))
    with pytest.raises(ConfigError, match=r"examples\.python"):
        load_config(str(config_dir))


def test_examples_malformed_language_key(config_dir):
    """A malformed language key is rejected at load (strict keys)."""
    _write_config(config_dir, _cfg(examples={"Python 3!": "python {file}"}))
    with pytest.raises(ConfigError, match="examples.*key"):
        load_config(str(config_dir))


def test_examples_not_an_object(config_dir):
    """'examples' must be an object, not a list."""
    _write_config(config_dir, _cfg(examples=["python"]))
    with pytest.raises(ConfigError, match="'examples' must be an object"):
        load_config(str(config_dir))
