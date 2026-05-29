"""Tests for selfdoc.extractors.base helper functions."""

import json

from selfdoc.extractors.base import (
    _config_from_json,
    _config_from_toml,
    apply_exclude_keys,
    parse_comma_set,
)


# -- parse_comma_set ---------------------------------------------------------


class TestParseCommaSet:
    def test_simple(self):
        assert parse_comma_set("a,b,c") == {"a", "b", "c"}

    def test_whitespace(self):
        assert parse_comma_set("a, b , c") == {"a", "b", "c"}

    def test_single(self):
        assert parse_comma_set("single") == {"single"}

    def test_empty_string(self):
        assert parse_comma_set("") == set()


# -- apply_exclude_keys ------------------------------------------------------


class TestApplyExcludeKeys:
    def test_none_returns_data(self):
        data = {"a": 1, "b": 2}
        assert apply_exclude_keys(data, None, "test.json") is data

    def test_empty_set_returns_data(self):
        data = {"a": 1, "b": 2}
        assert apply_exclude_keys(data, set(), "test.json") is data

    def test_valid_keys(self):
        data = {"a": 1, "b": 2, "c": 3}
        result = apply_exclude_keys(data, {"a", "c"}, "test.json")
        assert result == {"b": 2}

    def test_missing_key(self):
        data = {"a": 1, "b": 2}
        result = apply_exclude_keys(data, {"a", "missing"}, "test.json")
        assert isinstance(result, str)
        assert "selfdoc:" in result
        assert "missing" in result


# -- _config_from_json -------------------------------------------------------


class TestConfigFromJson:
    def test_happy_path(self, tmp_path):
        path = tmp_path / "config.json"
        data = {
            "name": "test",
            "count": 42,
            "enabled": True,
            "items": [1, 2],
            "nested": {"a": 1},
        }
        path.write_text(json.dumps(data))

        result = _config_from_json(str(path), "config.json")
        assert "| Key | Type | Value |" in result
        assert "`name`" in result
        assert "string" in result
        assert "`count`" in result
        assert "integer" in result
        assert "`enabled`" in result
        assert "boolean" in result
        assert "`items`" in result
        assert "array" in result
        assert "`nested`" in result
        assert "object" in result

    def test_non_dict(self, tmp_path):
        path = tmp_path / "list.json"
        path.write_text(json.dumps([1, 2, 3]))

        result = _config_from_json(str(path), "list.json")
        assert "```json" in result

    def test_parse_error(self, tmp_path):
        path = tmp_path / "bad.json"
        path.write_text("{invalid json")

        result = _config_from_json(str(path), "bad.json")
        assert "selfdoc:" in result


# -- _config_from_toml -------------------------------------------------------


class TestConfigFromToml:
    def test_happy_path(self, tmp_path):
        path = tmp_path / "config.toml"
        path.write_text('name = "test"\ncount = 42\n')

        result = _config_from_toml(str(path), "config.toml")
        assert "| Key | Type | Value |" in result
        assert "`name`" in result
        assert "`count`" in result

    def test_nested(self, tmp_path):
        path = tmp_path / "nested.toml"
        path.write_text('[section]\nkey = "value"\n')

        result = _config_from_toml(str(path), "nested.toml")
        assert "`section.key`" in result


# -- _config_from_json with exclude_keys ------------------------------------


class TestConfigFromJsonExclude:
    def test_exclude_filters_key(self, tmp_path):
        path = tmp_path / "config.json"
        data = {"name": "test", "version": "1.0", "count": 42}
        path.write_text(json.dumps(data))

        result = _config_from_json(str(path), "config.json", exclude_keys={"version"})
        assert "`version`" not in result
        assert "`name`" in result
        assert "`count`" in result

    def test_exclude_missing_key_returns_error(self, tmp_path):
        path = tmp_path / "config.json"
        data = {"name": "test", "version": "1.0", "count": 42}
        path.write_text(json.dumps(data))

        result = _config_from_json(str(path), "config.json", exclude_keys={"missing"})
        assert "selfdoc:" in result


# -- _config_from_toml with exclude_keys ------------------------------------


class TestConfigFromTomlExclude:
    def test_exclude_section_drops_all_subkeys(self, tmp_path):
        path = tmp_path / "config.toml"
        path.write_text('name = "test"\n\n[deploy]\nprovider = "cf"\n')

        result = _config_from_toml(str(path), "config.toml", exclude_keys={"deploy"})
        assert "deploy" not in result
        assert "deploy.provider" not in result
        assert "`name`" in result

    def test_exclude_missing_key_returns_error(self, tmp_path):
        path = tmp_path / "config.toml"
        path.write_text('name = "test"\n')

        result = _config_from_toml(str(path), "config.toml", exclude_keys={"missing"})
        assert "selfdoc:" in result
