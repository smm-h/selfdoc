"""Shared utility functions for selfdoc."""

import json
import os
import re
import tomllib

from selfdoc_core import effects


def resolve_directive_path(base_dir, path):
    """Resolve a directive's ``path`` attribute against the project base_dir.

    Single source of truth for filesystem directive path resolution. Every
    directive that reads a ``path`` attribute (list-tree, table-dep,
    list-modules, table-endpoint, table-config) resolves it through here so the
    behavior stays identical and any future normalization or sandboxing lives
    in one place.
    """
    return os.path.join(base_dir, path)


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


def atomic_write(filepath, content, permissions=None):
    """Write *content* to *filepath* atomically.

    Writes to a temporary file in the same directory, then replaces the
    target.  Optionally sets file permissions after writing.

    Re-export of the effects chokepoint's primitive: under a command's
    ``--dry-run`` the write is recorded instead of performed.
    """
    effects.atomic_write(filepath, content, permissions=permissions)


def detect_project_version(base_dir: str, fallback: str = "") -> str:
    """Detect project version from manifest files.

    A source language declared in base_dir's selfdoc.json picks the manifest
    the version is read from (go -> VERSION, python -> pyproject.toml,
    js/node -> package.json), so a polyglot repo's incidental manifests --
    e.g. a private browser-test-harness package.json at the root of a Go
    project, whose version field is conventionally 0.0.0 -- cannot win. This
    is the version counterpart of the same rule ``_read_project_field``
    applies to the project name.

    Without a declaration, or when the picked manifest is absent or carries
    no version, the original lookup chain applies:
    1. pyproject.toml [project].version
    2. package.json "version"
    3. VERSION file (plain text)

    Returns *fallback* if no version is found.
    """
    lang = _declared_source_language(base_dir)
    if lang:
        if lang == "python":
            version = _read_pyproject_version(base_dir)
        elif lang == "go":
            version = _read_version_file(base_dir)
        elif lang in ("js", "javascript", "node", "typescript"):
            version = _read_package_json_version(base_dir)
        else:
            version = ""
        if version:
            return version
        # Declared language without a readable version: fall through.

    for reader in (
        _read_pyproject_version,
        _read_package_json_version,
        _read_version_file,
    ):
        version = reader(base_dir)
        if version:
            return version

    return fallback


def _read_pyproject_version(base_dir: str) -> str:
    """The [project].version of base_dir's pyproject.toml, or "" if unreadable."""
    path = os.path.join(base_dir, "pyproject.toml")
    if not os.path.isfile(path):
        return ""
    try:
        with open(path, "rb") as f:
            data = tomllib.load(f)
        return data.get("project", {}).get("version") or ""
    except (OSError, tomllib.TOMLDecodeError, KeyError):
        return ""


def _read_package_json_version(base_dir: str) -> str:
    """The "version" of base_dir's package.json, or "" if unreadable."""
    path = os.path.join(base_dir, "package.json")
    if not os.path.isfile(path):
        return ""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("version") or ""
    except (OSError, json.JSONDecodeError, KeyError):
        return ""


def _read_version_file(base_dir: str) -> str:
    """The stripped contents of base_dir's VERSION file, or "" if unreadable."""
    path = os.path.join(base_dir, "VERSION")
    if not os.path.isfile(path):
        return ""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""


def _declared_source_language(base_dir: str) -> str:
    """The first declared source language in base_dir's selfdoc.json, or ""."""
    config = os.path.join(base_dir, "selfdoc.json")
    try:
        with open(config, "r", encoding="utf-8") as f:
            data = json.load(f)
        sources = data.get("source") or []
        if sources and isinstance(sources[0], dict):
            return str(sources[0].get("language", "")).lower()
    except (OSError, json.JSONDecodeError):
        pass
    return ""


def _read_package_json_field(base_dir: str, field: str) -> str:
    pkg_json = os.path.join(base_dir, "package.json")
    if os.path.isfile(pkg_json):
        try:
            with open(pkg_json, "r", encoding="utf-8") as f:
                data = json.load(f)
            return str(data.get(field, "unknown"))
        except (OSError, json.JSONDecodeError):
            return "unknown"
    return "unknown"


def _read_go_mod_name(base_dir: str) -> str:
    go_mod = os.path.join(base_dir, "go.mod")
    if os.path.isfile(go_mod):
        try:
            with open(go_mod, "r", encoding="utf-8") as f:
                for line in f:
                    m = re.match(r"^module\s+(.+)", line.strip())
                    if m:
                        return m.group(1).strip()
        except OSError:
            pass
    return "unknown"


def _read_project_field(base_dir: str, field: str) -> str:
    """Read a project metadata field from the project's manifest.

    A source language declared in base_dir's selfdoc.json picks the manifest
    (go -> go.mod, python -> pyproject.toml, js/node -> package.json), so a
    polyglot repo's incidental manifests — e.g. a browser-test harness's
    package.json at the root of a Go project — cannot win. Without a
    declaration, or when the picked manifest is absent or unreadable, the
    original lookup chain applies: pyproject.toml, then package.json, then
    go.mod.
    """
    # For version, delegate to the shared utility
    if field == "version":
        return detect_project_version(base_dir, fallback="unknown")

    lang = _declared_source_language(base_dir)
    if lang:
        if lang == "python":
            pyproject = os.path.join(base_dir, "pyproject.toml")
            if os.path.isfile(pyproject):
                import tomllib
                return _read_toml_field(pyproject, field, tomllib)
        elif lang == "go":
            if field == "name":
                name = _read_go_mod_name(base_dir)
                if name != "unknown":
                    return name
        elif lang in ("js", "javascript", "node", "typescript"):
            name = _read_package_json_field(base_dir, field)
            if name != "unknown":
                return name
        # Declared language without a readable manifest: fall through.

    # The original lookup chain
    pyproject = os.path.join(base_dir, "pyproject.toml")
    if os.path.isfile(pyproject):
        import tomllib
        return _read_toml_field(pyproject, field, tomllib)

    if os.path.isfile(os.path.join(base_dir, "package.json")):
        return _read_package_json_field(base_dir, field)

    go_mod = os.path.join(base_dir, "go.mod")
    if os.path.isfile(go_mod):
        if field == "name":
            return _read_go_mod_name(base_dir)
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
