"""The single authority for which source paths a project's docs cover.

Every source walk in selfdoc -- page generation, coverage counting, and the
``list-modules`` directive -- decides the same way which files and directories
are part of the documented project. Keeping the patterns and the matcher here
means a path excluded from the generated pages cannot be advertised by a
listing directive, and vice versa.

The inputs are two: ``DEFAULT_EXCLUDES``, applied everywhere, and the
``gen.exclude`` list from ``selfdoc.json``, which a project adds to it.
``SKIP_DIRS`` is separate and unconditional: environment and build directories
that are never source, pruned from ``os.walk`` before any pattern is tested.
"""

import fnmatch
import os

# Default exclusion patterns (always applied in addition to user-configured
# ones). These are matched against both the full relative path and the
# basename, so ``test_*`` will match ``test_core.py`` at any depth.
DEFAULT_EXCLUDES = [
    "test_*",
    "*_test.*",
    "__pycache__",
    "tests",
]

# Directories that should ALWAYS be pruned from os.walk during source walks.
# Modifying dirs[:] in-place prevents os.walk from descending into these.
SKIP_DIRS = {
    ".venv", "venv", "node_modules", "__pycache__", ".git", ".hg",
    ".svn", "dist", "build", "_build", ".tox", ".mypy_cache",
    ".pytest_cache", ".ruff_cache", ".zig-cache", "zig-cache",
}


def should_skip_dir(dirname):
    """Return True if a directory name should be pruned during source walks."""
    if dirname in SKIP_DIRS:
        return True
    # Also skip directories ending in .egg-info (e.g. mylib.egg-info)
    if dirname.endswith(".egg-info"):
        return True
    return False


def is_excluded(rel_path, exclude_patterns):
    """Check whether a relative path matches any exclusion glob pattern.

    Supports ``**/`` prefix as "match at any depth" by stripping the
    prefix and testing against every path component and the basename.
    Plain patterns are matched against the full path, the basename, and
    each directory component.
    """
    # Normalise to forward slashes for consistent matching
    normalized = rel_path.replace(os.sep, "/")
    parts = normalized.split("/")
    basename = parts[-1]
    dir_parts = parts[:-1]
    for pattern in exclude_patterns:
        # Strip leading **/ for "any depth" semantics
        stripped = pattern
        while stripped.startswith("**/"):
            stripped = stripped[3:]

        if fnmatch.fnmatch(normalized, stripped):
            return True
        if fnmatch.fnmatch(basename, stripped):
            return True
        # Check each directory component
        for part in dir_parts:
            if fnmatch.fnmatch(part, stripped):
                return True
        # Also try the original pattern against the full path
        if pattern != stripped and fnmatch.fnmatch(normalized, pattern):
            return True
    return False


def exclude_patterns_for(config):
    """The full exclusion pattern list for a project: defaults + gen.exclude."""
    gen_config = config.get("gen") or {}
    return list(DEFAULT_EXCLUDES) + list(gen_config.get("exclude", []))
