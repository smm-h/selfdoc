"""Tests for custom directive plugin system."""

import os

import pytest

from selfdoc.resolver import make_resolver


def _make_config(**overrides):
    """Create a minimal valid config dict with optional overrides."""
    base = {
        "source": [{"path": "src/", "language": "python"}],
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
        "def resolve(attrs, config, body):\n"
        "    return f'API for {attrs.get(\"path\", \"\")}'\n"
    ))
    config = _make_config(directives={"api": rel})
    resolver = make_resolver(config, str(tmp_path))
    result = resolver("api", {"path": "v2"}, [])
    assert result == "API for v2"


# -- custom directive returns markdown --


def test_custom_directive_returns_markdown(tmp_path):
    """The markdown returned by a custom directive is included as-is."""
    rel = _write_script(tmp_path, "table_gen.py", (
        "def resolve(attrs, config, body):\n"
        "    return '| Col A | Col B |\\n|---|---|\\n| 1 | 2 |'\n"
    ))
    config = _make_config(directives={"table": rel})
    resolver = make_resolver(config, str(tmp_path))
    result = resolver("table", {}, [])
    assert "| Col A | Col B |" in result
    assert "| 1 | 2 |" in result


# -- missing script file --


def test_missing_script_produces_error(tmp_path):
    """A missing script file should produce an error message, not crash."""
    config = _make_config(directives={"bad": "nonexistent.py"})
    resolver = make_resolver(config, str(tmp_path))
    result = resolver("bad", {}, [])
    assert "selfdoc:" in result
    assert "custom directive 'bad' failed" in result
    assert "not found" in result


# -- custom directive overrides built-in --


def test_custom_directive_overrides_builtin(tmp_path):
    """A custom directive with the same name as a built-in should take priority."""
    # 'ref' is a built-in directive for Python projects
    rel = _write_script(tmp_path, "my_module.py", (
        "def resolve(attrs, config, body):\n"
        "    return f'CUSTOM module: {attrs.get(\"path\", \"\")}'\n"
    ))
    config = _make_config(directives={"ref": rel})
    resolver = make_resolver(config, str(tmp_path))
    result = resolver("ref", {"path": "selfdoc.config"}, [])
    assert result == "CUSTOM module: selfdoc.config"
    # Confirm it did NOT go through the built-in Python extractor
    assert "CUSTOM" in result


# -- script that raises an exception --


def test_script_exception_produces_error(tmp_path):
    """A script that raises should produce an error message, not crash."""
    rel = _write_script(tmp_path, "broken.py", (
        "def resolve(attrs, config, body):\n"
        "    raise ValueError('something went wrong')\n"
    ))
    config = _make_config(directives={"broken": rel})
    resolver = make_resolver(config, str(tmp_path))
    result = resolver("broken", {}, [])
    assert "selfdoc:" in result
    assert "custom directive 'broken' failed" in result
    assert "something went wrong" in result


# -- script receives config --


def test_script_receives_full_config(tmp_path):
    """The custom directive script should receive the full config dict."""
    rel = _write_script(tmp_path, "check_config.py", (
        "def resolve(attrs, config, body):\n"
        "    return f'lang={config[\"language\"]}'\n"
    ))
    config = _make_config(language="go", directives={"check": rel})
    resolver = make_resolver(config, str(tmp_path))
    result = resolver("check", {}, [])
    assert result == "lang=go"


# -- script receives body --


def test_script_receives_body(tmp_path):
    """The custom directive script should receive the body lines."""
    rel = _write_script(tmp_path, "with_body.py", (
        "def resolve(attrs, config, body):\n"
        "    return '\\n'.join(body)\n"
    ))
    config = _make_config(directives={"echo": rel})
    resolver = make_resolver(config, str(tmp_path))
    result = resolver("echo", {}, ["line1", "line2"])
    assert result == "line1\nline2"


# -- script missing resolve function --


def test_script_missing_resolve_function(tmp_path):
    """A script without a resolve() callable should produce an error."""
    rel = _write_script(tmp_path, "no_resolve.py", (
        "def something_else():\n"
        "    pass\n"
    ))
    config = _make_config(directives={"nope": rel})
    resolver = make_resolver(config, str(tmp_path))
    result = resolver("nope", {}, [])
    assert "selfdoc:" in result
    assert "custom directive 'nope' failed" in result
    assert "no callable 'resolve'" in result


# -- non-custom directives still work --


def test_non_custom_directive_falls_through(tmp_path):
    """Directives not in config["directives"] should fall through to built-in."""
    config = _make_config(directives={})
    resolver = make_resolver(config, str(tmp_path))
    # 'ref' is a built-in Python directive; it won't find actual source
    # files in tmp_path, but it should NOT produce a "custom directive failed"
    # error -- it should go through the Python extractor path
    result = resolver("ref", {"path": "nonexistent.module"}, [])
    assert "custom directive" not in result


# -- language-agnostic dispatch --


def test_unknown_language_uses_stub_extractor(tmp_path):
    """An unsupported language uses StubExtractor and returns error on extract."""
    config = _make_config(source=[{"path": "src/", "language": "rust"}])
    resolver = make_resolver(config, str(tmp_path))
    result = resolver("ref", {"path": "foo"}, [])
    assert "no extractor for 'rust'" in result


def test_unknown_directive_produces_error(tmp_path):
    """An unknown directive name should produce an error from the extractor."""
    config = _make_config()
    resolver = make_resolver(config, str(tmp_path))
    result = resolver("nonexistent-directive", {}, [])
    assert "unknown directive" in result


def test_list_glossary_works(tmp_path):
    """list-glossary should produce HTML glossary output."""
    config = _make_config()
    resolver = make_resolver(config, str(tmp_path))
    result = resolver("list-glossary", {}, [
        "**Term1**: Definition one",
        "**Term2**: Definition two",
    ])
    assert '<div class="glossary">' in result
    assert "<dt><dfn>Term1</dfn></dt>" in result
    assert "<dd>Definition one</dd>" in result
    assert "<dt><dfn>Term2</dfn></dt>" in result
    assert "<dd>Definition two</dd>" in result


def test_list_glossary_empty_body(tmp_path):
    """list-glossary with empty body should produce empty glossary."""
    config = _make_config()
    resolver = make_resolver(config, str(tmp_path))
    result = resolver("list-glossary", {}, [])
    assert '<div class="glossary"><dl></dl></div>' in result


def test_new_directive_names_dispatch(tmp_path):
    """New directive names should dispatch correctly through the extractor."""
    config = _make_config(language="python")
    resolver = make_resolver(config, str(tmp_path))

    # These all go through the Python extractor but won't find real files;
    # the important thing is they dispatch to the right handler (not "unknown directive")
    ref_result = resolver("ref", {"path": "some.module"}, [])
    assert "not found" in ref_result  # module not found, but handler was invoked

    test_result = resolver("code-test", {"path": "test_file.py"}, [])
    assert "not found" in test_result  # file not found, but handler was invoked

    schema_result = resolver("table-schema", {"path": "schema.json"}, [])
    assert "not found" in schema_result  # file not found, but handler was invoked

    help_result = resolver("code-help", {"path": "cli_module"}, [])
    assert "not found" in help_result  # module not found, but handler was invoked

    config_result = resolver("table-config", {"path": "config.json"}, [])
    assert "not found" in config_result  # file not found, but handler was invoked
