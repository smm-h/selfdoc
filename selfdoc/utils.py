"""Shared utility functions for selfdoc."""

import ast
import json
import os
import re
import tempfile
import tomllib


def extract_module_docstring(filepath):
    """Extract the first line of a Python module's docstring.

    Uses ``ast.parse`` and ``ast.get_docstring`` to read the module-level
    docstring.  Returns the first sentence (up to the first period followed
    by whitespace/end, or the first newline), truncated to 155 characters.
    Returns ``None`` if the file is not Python, cannot be parsed, or has
    no module docstring.
    """
    if not filepath.endswith(".py"):
        return None
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            source = f.read()
    except OSError:
        return None
    try:
        tree = ast.parse(source, filename=filepath)
    except SyntaxError:
        return None
    docstring = ast.get_docstring(tree)
    if not docstring:
        return None
    # Take the first line
    first_line = docstring.split("\n", 1)[0].strip()
    if not first_line:
        return None
    # Take up to the first sentence-ending period (period followed by
    # whitespace or end-of-string)
    match = re.search(r"\.\s", first_line)
    if match:
        first_line = first_line[: match.start() + 1]
    elif first_line.endswith("."):
        pass  # already ends with period
    # Truncate to 155 chars
    if len(first_line) > 155:
        first_line = first_line[:152] + "..."
    return first_line


def atomic_write(filepath, content, permissions=None):
    """Write *content* to *filepath* atomically.

    Writes to a temporary file in the same directory, then replaces the
    target.  Optionally sets file permissions after writing.
    """
    dir_name = os.path.dirname(filepath)
    fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        if permissions is not None:
            os.chmod(tmp_path, permissions)
        os.replace(tmp_path, filepath)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def detect_project_version(base_dir: str, fallback: str = "") -> str:
    """Detect project version from manifest files.

    Checks sources in order:
    1. pyproject.toml [project].version
    2. package.json "version"
    3. VERSION file (plain text)

    Returns *fallback* if no version is found.
    """
    # Try pyproject.toml
    pyproject_path = os.path.join(base_dir, "pyproject.toml")
    if os.path.isfile(pyproject_path):
        try:
            with open(pyproject_path, "rb") as f:
                data = tomllib.load(f)
            version = data.get("project", {}).get("version")
            if version:
                return version
        except (OSError, tomllib.TOMLDecodeError, KeyError):
            pass

    # Try package.json
    package_path = os.path.join(base_dir, "package.json")
    if os.path.isfile(package_path):
        try:
            with open(package_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            version = data.get("version")
            if version:
                return version
        except (OSError, json.JSONDecodeError, KeyError):
            pass

    # Try VERSION file
    version_path = os.path.join(base_dir, "VERSION")
    if os.path.isfile(version_path):
        try:
            with open(version_path, "r", encoding="utf-8") as f:
                version = f.read().strip()
            if version:
                return version
        except OSError:
            pass

    return fallback
