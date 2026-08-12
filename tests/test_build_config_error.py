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
