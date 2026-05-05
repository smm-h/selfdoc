"""Tests for custom directive plugin system."""

import os

import pytest

from selfdoc.resolver import make_resolver


def _make_config(**overrides):
    """Create a minimal valid config dict with optional overrides."""
    base = {
        "language": "python",
        "source": ["src/"],
        "docs": "docs/",
        "output": "docs/_build/",
        "deploy": None,
        "directives": {},
    }
    base.update(overrides)
    return base


def _write_script(directory, filename, content):
    """Write a Python script into *directory* and return its path relative to directory."""
    path = os.path.join(directory, filename)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return filename


# -- custom directive calls the script --


def test_custom_directive_calls_script(tmp_path):
    """A custom directive in config should call the script's resolve()."""
    rel = _write_script(tmp_path, "extract_api.py", (
        "def resolve(arg, config):\n"
        "    return f'API for {arg}'\n"
    ))
    config = _make_config(directives={"api": rel})
    resolver = make_resolver(config, str(tmp_path))
    result = resolver("api", "v2", [])
    assert result == "API for v2"


# -- custom directive returns markdown --


def test_custom_directive_returns_markdown(tmp_path):
    """The markdown returned by a custom directive is included as-is."""
    rel = _write_script(tmp_path, "table_gen.py", (
        "def resolve(arg, config):\n"
        "    return '| Col A | Col B |\\n|---|---|\\n| 1 | 2 |'\n"
    ))
    config = _make_config(directives={"table": rel})
    resolver = make_resolver(config, str(tmp_path))
    result = resolver("table", "", [])
    assert "| Col A | Col B |" in result
    assert "| 1 | 2 |" in result


# -- missing script file --


def test_missing_script_produces_error(tmp_path):
    """A missing script file should produce an error message, not crash."""
    config = _make_config(directives={"bad": "nonexistent.py"})
    resolver = make_resolver(config, str(tmp_path))
    result = resolver("bad", "arg", [])
    assert "selfdoc:" in result
    assert "custom directive 'bad' failed" in result
    assert "not found" in result


# -- custom directive overrides built-in --


def test_custom_directive_overrides_builtin(tmp_path):
    """A custom directive with the same name as a built-in should take priority."""
    # 'module' is a built-in directive for Python projects
    rel = _write_script(tmp_path, "my_module.py", (
        "def resolve(arg, config):\n"
        "    return f'CUSTOM module: {arg}'\n"
    ))
    config = _make_config(directives={"module": rel})
    resolver = make_resolver(config, str(tmp_path))
    result = resolver("module", "selfdoc.config", [])
    assert result == "CUSTOM module: selfdoc.config"
    # Confirm it did NOT go through the built-in Python extractor
    assert "CUSTOM" in result


# -- script that raises an exception --


def test_script_exception_produces_error(tmp_path):
    """A script that raises should produce an error message, not crash."""
    rel = _write_script(tmp_path, "broken.py", (
        "def resolve(arg, config):\n"
        "    raise ValueError('something went wrong')\n"
    ))
    config = _make_config(directives={"broken": rel})
    resolver = make_resolver(config, str(tmp_path))
    result = resolver("broken", "x", [])
    assert "selfdoc:" in result
    assert "custom directive 'broken' failed" in result
    assert "something went wrong" in result


# -- script receives config --


def test_script_receives_full_config(tmp_path):
    """The custom directive script should receive the full config dict."""
    rel = _write_script(tmp_path, "check_config.py", (
        "def resolve(arg, config):\n"
        "    return f'lang={config[\"language\"]}'\n"
    ))
    config = _make_config(language="go", directives={"check": rel})
    resolver = make_resolver(config, str(tmp_path))
    result = resolver("check", "", [])
    assert result == "lang=go"


# -- script missing resolve function --


def test_script_missing_resolve_function(tmp_path):
    """A script without a resolve() callable should produce an error."""
    rel = _write_script(tmp_path, "no_resolve.py", (
        "def something_else():\n"
        "    pass\n"
    ))
    config = _make_config(directives={"nope": rel})
    resolver = make_resolver(config, str(tmp_path))
    result = resolver("nope", "", [])
    assert "selfdoc:" in result
    assert "custom directive 'nope' failed" in result
    assert "no callable 'resolve'" in result


# -- non-custom directives still work --


def test_non_custom_directive_falls_through(tmp_path):
    """Directives not in config["directives"] should fall through to built-in."""
    config = _make_config(directives={})
    resolver = make_resolver(config, str(tmp_path))
    # 'module' is a built-in Python directive; it won't find actual source
    # files in tmp_path, but it should NOT produce a "custom directive failed"
    # error -- it should go through the Python extractor path
    result = resolver("module", "nonexistent.module", [])
    assert "custom directive" not in result
