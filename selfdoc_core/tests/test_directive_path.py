"""Tests for the shared directive path resolver."""

import os

from selfdoc_core.utils import resolve_directive_path


def test_joins_base_and_path():
    assert resolve_directive_path("/proj", "src/x.py") == os.path.join(
        "/proj", "src/x.py"
    )


def test_matches_plain_os_path_join():
    # The helper is the single source of truth; it must stay byte-identical to
    # os.path.join(base_dir, path) so existing directive output does not shift.
    for base, path in [
        (".", "pyproject.toml"),
        ("/a/b", "c/d"),
        ("proj", "."),
        ("proj/", "sub/"),
    ]:
        assert resolve_directive_path(base, path) == os.path.join(base, path)
