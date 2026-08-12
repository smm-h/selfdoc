"""A bad config stops ``selfdoc build`` with a message, not a traceback.

``build`` raises ``ConfigError`` for a config that is present but unusable
(no ``versions``, no ``locales``).  The CLI caught only ``RuntimeError``,
so those two reached the top of the interpreter and printed a traceback --
the one error shape a user is most likely to hit.  The guidance in those
messages also still offered the retired per-version ``indexed`` key, which
the config loader now rejects.
"""

import json
import os
import subprocess
import sys

import pytest

from selfdoc.build import build
from selfdoc_core.config import ConfigError
from conftest import default_config


def _project(tmp_path, config):
    """Write *config* as selfdoc.json into a minimal project tree."""
    with open(os.path.join(tmp_path, "selfdoc.json"), "w") as f:
        json.dump(config, f)
    src_dir = os.path.join(tmp_path, "src")
    os.makedirs(src_dir, exist_ok=True)
    with open(os.path.join(src_dir, "__init__.py"), "w") as f:
        f.write('"""Example package."""\n')
    docs_dir = os.path.join(tmp_path, "docs")
    os.makedirs(docs_dir, exist_ok=True)
    with open(os.path.join(docs_dir, "index.md"), "w") as f:
        f.write("# Test Project\n\nWelcome.\n")
    return str(tmp_path)


def _without(key):
    config = default_config(docs="docs/", output="docs/_build/")
    config.pop(key)
    return config


# -- The guidance names only keys the config loader accepts ----------------


def test_missing_versions_guidance_omits_retired_indexed_key(tmp_path):
    """The 'add versions' guidance no longer offers ``indexed``.

    ``indexed`` was retired and is now rejected by the loader, so following
    the guidance produced a second, different error.
    """
    project = _project(tmp_path, _without("versions"))

    with pytest.raises(ConfigError) as excinfo:
        build(project, config=_without("versions"))

    message = str(excinfo.value)
    assert "versions" in message
    assert "indexed" not in message


def test_missing_locales_raises_config_error(tmp_path):
    """A config with no ``locales`` is a ConfigError, not a crash."""
    project = _project(tmp_path, _without("locales"))

    with pytest.raises(ConfigError) as excinfo:
        build(project, config=_without("locales"))

    assert "locales" in str(excinfo.value)


# -- The CLI prints the message and exits 1 --------------------------------


def _run_build(cwd):
    return subprocess.run(
        [sys.executable, "-m", "selfdoc", "build", "--no-auto-commit"],
        cwd=cwd, capture_output=True, text=True, timeout=180,
    )


def test_cli_build_config_error_is_clean(tmp_path):
    """``selfdoc build`` on a config with no versions exits 1, no traceback."""
    project = _project(tmp_path, _without("versions"))

    result = _run_build(project)

    assert result.returncode == 1
    assert "Traceback" not in result.stderr
    assert "versions" in result.stderr
    assert result.stderr.strip().startswith("Error:")


# -- Every surface that can raise one presents it the same way -------------
#
# ``check`` loaded the config outside any handler, so the same bad file that
# ``build`` reported cleanly ended ``check`` on a traceback. A suppression
# list naming an unknown or unsuppressable code arrives as the same error
# (the loader refuses it there), and a plain build of a project whose pages
# carry site-level directives raises a third exception type entirely.


def _run_check(cwd):
    return subprocess.run(
        [sys.executable, "-m", "selfdoc", "check", "--no-auto-commit"],
        cwd=cwd, capture_output=True, text=True, timeout=180,
    )


def _assert_clean_refusal(result, *fragments):
    assert result.returncode == 1, result.stdout + result.stderr
    assert "Traceback" not in result.stderr, result.stderr
    assert result.stderr.strip().startswith("Error:"), result.stderr
    for fragment in fragments:
        assert fragment in result.stderr, result.stderr


def test_cli_check_config_error_is_clean(tmp_path):
    """``selfdoc check`` on an unloadable config exits 1, no traceback.

    ``check`` loaded the config with no handler at all, so the loader's
    refusal reached the top of the interpreter.
    """
    config = default_config(docs="docs/", output="docs/_build/")
    config["versions"] = "0.1.0"  # a string where a list is required
    project = _project(tmp_path, config)

    _assert_clean_refusal(_run_check(project), "versions")


def test_cli_build_config_type_error_is_clean(tmp_path):
    """The same bad file, the same refusal, from the sibling command."""
    config = default_config(docs="docs/", output="docs/_build/")
    config["versions"] = "0.1.0"
    project = _project(tmp_path, config)

    _assert_clean_refusal(_run_build(project), "versions")


def test_cli_check_unknown_suppression_code_is_clean(tmp_path):
    """A lint_ignore naming a code the registry does not carry."""
    config = default_config(docs="docs/", output="docs/_build/")
    config["lint_ignore"] = ["SEO999"]
    project = _project(tmp_path, config)

    _assert_clean_refusal(_run_check(project), "SEO999")


def test_cli_build_unknown_suppression_code_is_clean(tmp_path):
    config = default_config(docs="docs/", output="docs/_build/")
    config["lint_ignore"] = ["SEO999"]
    project = _project(tmp_path, config)

    _assert_clean_refusal(_run_build(project), "SEO999")


def test_cli_check_unsuppressable_code_is_clean(tmp_path):
    """An error-severity code is not suppressible; saying so is not a crash."""
    config = default_config(docs="docs/", output="docs/_build/")
    config["lint_ignore"] = ["LINK001"]
    project = _project(tmp_path, config)

    _assert_clean_refusal(_run_check(project), "LINK001")


def _with_unknown_directive(tmp_path):
    """A project whose page carries a directive plain selfdoc cannot resolve.

    This is the shape of the home project: its front page carries the
    site-level directives selfblog owns, and ``selfdoc build`` knows nothing
    about them.
    """
    project = _project(tmp_path, default_config(
        docs="docs/", output="docs/_build/",
    ))
    with open(os.path.join(project, "docs", "index.md"), "w") as f:
        f.write(
            "---\ntitle: Front page\n---\n# Front page\n\n"
            ':-: projects-cards\n'
        )
    return project


def test_cli_build_unknown_directive_is_clean(tmp_path):
    """An unresolvable directive is a message, not a DirectiveError dump."""
    project = _with_unknown_directive(tmp_path)

    _assert_clean_refusal(_run_build(project), "projects-cards")


def test_cli_check_unknown_directive_is_clean(tmp_path):
    project = _with_unknown_directive(tmp_path)

    _assert_clean_refusal(_run_check(project), "projects-cards")


# -- selfblog's own check and build, same bug class ------------------------


def _run_selfblog(cwd, *args):
    return subprocess.run(
        [sys.executable, "-m", "selfblog", *args],
        cwd=cwd, capture_output=True, text=True, timeout=180,
    )


def test_selfblog_check_config_error_is_clean(tmp_path):
    config = default_config(docs="docs/", output="docs/_build/")
    config["versions"] = "0.1.0"
    project = _project(tmp_path, config)

    _assert_clean_refusal(
        _run_selfblog(project, "check", "--no-auto-commit"), "versions",
    )


def test_selfblog_build_config_error_is_clean(tmp_path):
    config = default_config(docs="docs/", output="docs/_build/")
    config["versions"] = "0.1.0"
    project = _project(tmp_path, config)

    _assert_clean_refusal(
        _run_selfblog(project, "build", "--target", "posts"), "versions",
    )
