"""Shared utility functions for selfdoc."""

import ast
import json
import os
import re
import tempfile
import tomllib


def parse_frontmatter(content):
    """Parse YAML-like frontmatter from markdown content (Feature 34).

    If the content starts with '---', extracts key: value pairs until the
    closing '---'. Returns (metadata_dict, remaining_content). If no
    frontmatter is found, returns ({}, original_content).

    Simple parser: splits on ':' (first occurrence), strips whitespace.
    No YAML library needed.
    """
    if not content.startswith("---"):
        return {}, content

    lines = content.split("\n")
    # Find closing ---
    end_idx = None
    for idx in range(1, len(lines)):
        if lines[idx].strip() == "---":
            end_idx = idx
            break

    if end_idx is None:
        return {}, content

    metadata = {}
    for line in lines[1:end_idx]:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        colon_pos = line.find(":")
        if colon_pos == -1:
            continue
        key = line[:colon_pos].strip()
        value = line[colon_pos + 1:].strip()
        # Strip wrapping quotes (single or double) from string values
        if (
            len(value) >= 2
            and value[0] == value[-1]
            and value[0] in ('"', "'")
        ):
            value = value[1:-1]
        # Bracket-delimited lists: [a, b, c] -> ["a", "b", "c"]
        if value.startswith("[") and value.endswith("]"):
            inner = value[1:-1]
            value = [item.strip() for item in inner.split(",") if item.strip()]
        # Convert boolean-like strings
        elif value.lower() == "true":
            value = True
        elif value.lower() == "false":
            value = False
        else:
            # Try to convert numeric values
            try:
                value = int(value)
            except ValueError:
                try:
                    value = float(value)
                except ValueError:
                    pass
        metadata[key] = value

    remaining = "\n".join(lines[end_idx + 1:]).lstrip("\n")
    return metadata, remaining


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


def _read_project_field(base_dir: str, field: str) -> str:
    """Read a project metadata field from pyproject.toml, package.json, or go.mod."""
    # For version, delegate to the shared utility
    if field == "version":
        return detect_project_version(base_dir, fallback="unknown")

    # For other fields (e.g. "name"), use the original lookup chain
    # Try pyproject.toml
    pyproject = os.path.join(base_dir, "pyproject.toml")
    if os.path.isfile(pyproject):
        try:
            import tomllib
        except ModuleNotFoundError:
            try:
                import tomli as tomllib  # type: ignore[no-redef]
            except ModuleNotFoundError:
                pass
            else:
                return _read_toml_field(pyproject, field, tomllib)
        else:
            return _read_toml_field(pyproject, field, tomllib)

    # Try package.json
    pkg_json = os.path.join(base_dir, "package.json")
    if os.path.isfile(pkg_json):
        try:
            with open(pkg_json, "r", encoding="utf-8") as f:
                data = json.load(f)
            return str(data.get(field, "unknown"))
        except (OSError, json.JSONDecodeError):
            return "unknown"

    # Try go.mod (only for "name")
    go_mod = os.path.join(base_dir, "go.mod")
    if os.path.isfile(go_mod):
        if field == "name":
            try:
                with open(go_mod, "r", encoding="utf-8") as f:
                    for line in f:
                        m = re.match(r"^module\s+(.+)", line.strip())
                        if m:
                            return m.group(1).strip()
            except OSError:
                pass
        return "unknown"

    return "unknown"


def _read_toml_field(path: str, field: str, tomllib) -> str:
    """Read a field from pyproject.toml's [project] table."""
    try:
        with open(path, "rb") as f:
            data = tomllib.load(f)
        return str(data.get("project", {}).get(field, "unknown"))
    except Exception:
        return "unknown"
