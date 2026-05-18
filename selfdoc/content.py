"""Content directives -- directives that transform body content into styled HTML.

These directives do not need language extractors. They handle callouts
(note, warning, tip, danger, important), the glossary list, and
filesystem/project-metadata directives (list-tree, table-dep, list-features).
"""

from __future__ import annotations

import ast
import os
import re

# -- Callout directives -------------------------------------------------------

_CALLOUT_TYPES: dict[str, str] = {
    "callout-note": "Note",
    "callout-warning": "Warning",
    "callout-tip": "Tip",
    "callout-danger": "Danger",
    "callout-important": "Important",
}


def _resolve_callout(callout_type: str, title: str, body: list[str]) -> str:
    """Produce HTML for a callout directive."""
    parts = [
        f'<div class="callout {callout_type}">',
        f'<p class="callout-title">{title}</p>',
    ]
    if body:
        text = "\n".join(body)
        parts.append(f"<p>{text}</p>")
    parts.append("</div>")
    return "\n".join(parts)


# -- Glossary directive -------------------------------------------------------


def resolve_glossary(body: list[str]) -> str:
    """Parse glossary body lines and return HTML with <dl>/<dt>/<dd> elements.

    Each non-empty line is expected as ``**Term**: Definition text``.
    The ``**`` markers are stripped and the term/definition are split on
    the first ``: `` separator.

    Returns an HTML string wrapped in ``<div class="glossary">``.
    """
    items = []
    for line in body:
        line = line.strip()
        if not line:
            continue
        # Strip ** markers around the term
        line = re.sub(r"^\*\*(.+?)\*\*", r"\1", line)
        # Split on first ': '
        if ": " in line:
            term, definition = line.split(": ", 1)
        else:
            term = line
            definition = ""
        term = term.strip()
        definition = definition.strip()
        items.append((term, definition))

    if not items:
        return '<div class="glossary"><dl></dl></div>'

    dl_items = []
    for term, definition in items:
        dl_items.append(f"<dt><dfn>{term}</dfn></dt>")
        dl_items.append(f"<dd>{definition}</dd>")

    return (
        '<div class="glossary">\n<dl>\n'
        + "\n".join(dl_items)
        + "\n</dl>\n</div>"
    )


# -- list-tree directive -------------------------------------------------------

# Directories and patterns to exclude from tree listings
_TREE_EXCLUDES: set[str] = {
    "__pycache__", ".pyc", ".git", "node_modules", ".egg-info",
    "docs/_build", ".tox", ".mypy_cache", ".pytest_cache",
}


def _should_exclude(name: str) -> bool:
    """Check if a file or directory name should be excluded from tree output."""
    for excl in _TREE_EXCLUDES:
        if name == excl or name.endswith(excl):
            return True
    return False


def resolve_list_tree(attrs: dict, base_dir: str) -> str:
    """Walk a directory and produce a text tree inside a fenced code block."""
    path = attrs.get("path", "")
    if not path:
        return "> *[selfdoc: list-tree requires a path attribute]*"

    depth_str = attrs.get("depth", "")
    max_depth = int(depth_str) if depth_str.isdigit() else None

    full_path = os.path.join(base_dir, path)
    if not os.path.isdir(full_path):
        return f"> *[selfdoc: directory '{path}' not found]*"

    lines = _build_tree(full_path, "", max_depth, 0)
    # Prepend the root directory name
    root_name = os.path.basename(full_path.rstrip("/")) + "/"
    tree_text = root_name + "\n" + "\n".join(lines)
    return f"```\n{tree_text}\n```"


def _build_tree(
    dir_path: str, prefix: str, max_depth: int | None, current_depth: int
) -> list[str]:
    """Recursively build tree lines for a directory."""
    if max_depth is not None and current_depth >= max_depth:
        return []

    try:
        entries = sorted(os.listdir(dir_path))
    except OSError:
        return []

    # Filter out excluded entries
    entries = [e for e in entries if not _should_exclude(e)]

    lines = []
    for i, entry in enumerate(entries):
        is_last = i == len(entries) - 1
        connector = "└── " if is_last else "├── "
        entry_path = os.path.join(dir_path, entry)

        if os.path.isdir(entry_path):
            lines.append(f"{prefix}{connector}{entry}/")
            extension = "    " if is_last else "│   "
            sub_lines = _build_tree(
                entry_path, prefix + extension, max_depth, current_depth + 1
            )
            lines.extend(sub_lines)
        else:
            lines.append(f"{prefix}{connector}{entry}")

    return lines


# -- table-dep directive -------------------------------------------------------


def resolve_table_dep(attrs: dict, base_dir: str) -> str:
    """Parse pyproject.toml and produce a Markdown dependency table."""
    path = attrs.get("path", "")
    if not path:
        return "> *[selfdoc: table-dep requires a path attribute]*"

    full_path = os.path.join(base_dir, path)
    if not os.path.isfile(full_path):
        return f"> *[selfdoc: file '{path}' not found]*"

    try:
        import tomllib
    except ModuleNotFoundError:
        try:
            import tomli as tomllib  # type: ignore[no-redef]
        except ModuleNotFoundError:
            return "> *[selfdoc: TOML support requires Python 3.11+ or 'tomli']*"

    try:
        with open(full_path, "rb") as f:
            data = tomllib.load(f)
    except Exception as exc:
        return f"> *[selfdoc: cannot parse '{path}': {exc}]*"

    rows = []
    rows.append("| Package | Version Constraint |")
    rows.append("| --- | --- |")

    # Main dependencies
    deps = data.get("project", {}).get("dependencies", [])
    for dep in deps:
        pkg, constraint = _parse_dep_specifier(dep)
        rows.append(f"| `{pkg}` | {constraint} |")

    # Optional dependency groups
    opt_deps = data.get("project", {}).get("optional-dependencies", {})
    for group, group_deps in opt_deps.items():
        rows.append(f"| **[{group}]** | |")
        for dep in group_deps:
            pkg, constraint = _parse_dep_specifier(dep)
            rows.append(f"| `{pkg}` | {constraint} |")

    if len(rows) == 2:
        return "> *[selfdoc: no dependencies found in '{}']*".format(path)

    return "\n".join(rows)


def _parse_dep_specifier(spec: str) -> tuple[str, str]:
    """Split a PEP 508 dependency specifier into (package, constraint).

    Examples:
        "requests>=2.0" -> ("requests", ">=2.0")
        "flask" -> ("flask", "*")
        "black[jupyter]>=23.0,<24.0" -> ("black[jupyter]", ">=23.0,<24.0")
    """
    # Split on the first version comparison operator
    match = re.match(r"^([A-Za-z0-9_\-.\[\]]+)\s*(.*)", spec)
    if match:
        pkg = match.group(1).strip()
        constraint = match.group(2).strip()
        # Strip environment markers (;python_version...)
        if ";" in constraint:
            constraint = constraint.split(";")[0].strip()
        return pkg, constraint if constraint else "*"
    return spec.strip(), "*"


# -- list-features directive ---------------------------------------------------


def resolve_list_features(attrs: dict, base_dir: str) -> str:
    """Scan Python files in a directory and list module docstring first lines."""
    path = attrs.get("path", "")
    if not path:
        return "> *[selfdoc: list-features requires a path attribute]*"

    full_path = os.path.join(base_dir, path)
    if not os.path.isdir(full_path):
        return f"> *[selfdoc: directory '{path}' not found]*"

    items = []
    try:
        entries = sorted(os.listdir(full_path))
    except OSError:
        return f"> *[selfdoc: cannot read directory '{path}']*"

    for entry in entries:
        # Skip non-Python files, __init__.py, test files, __pycache__
        if not entry.endswith(".py"):
            continue
        if entry == "__init__.py":
            continue
        if entry.startswith("test_") or entry.endswith("_test.py"):
            continue
        if entry == "__pycache__":
            continue

        file_path = os.path.join(full_path, entry)
        first_line = _extract_module_first_line(file_path)
        if first_line:
            display_name = entry[:-3]  # strip .py
            items.append(f"- **{display_name}**: {first_line}")

    if not items:
        return f"> *[selfdoc: no documented modules found in '{path}']*"

    return "\n".join(items)


def _extract_module_first_line(file_path: str) -> str:
    """Extract the first line of a Python module's docstring."""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            source = f.read()
    except (OSError, UnicodeDecodeError):
        return ""

    try:
        tree = ast.parse(source, filename=file_path)
    except SyntaxError:
        return ""

    docstring = ast.get_docstring(tree)
    if not docstring:
        return ""

    # Get first line or first sentence
    first_line = docstring.split("\n")[0].strip()
    # If it ends with a period, return as-is; otherwise take first sentence
    if "." in first_line:
        return first_line.split(".")[0].strip() + "."
    return first_line


# -- Dispatch -----------------------------------------------------------------

CONTENT_DIRECTIVES: set[str] = {
    "callout-note", "callout-warning", "callout-tip",
    "callout-danger", "callout-important", "list-glossary",
    "list-tree", "table-dep", "list-features",
}


def resolve_content(
    name: str, attrs: dict, body: list[str], base_dir: str = "."
) -> str | None:
    """Resolve a content directive. Returns None if name is not a content directive."""
    if name in _CALLOUT_TYPES:
        return _resolve_callout(name, _CALLOUT_TYPES[name], body)
    if name == "list-glossary":
        return resolve_glossary(body)
    if name == "list-tree":
        return resolve_list_tree(attrs, base_dir)
    if name == "table-dep":
        return resolve_table_dep(attrs, base_dir)
    if name == "list-features":
        return resolve_list_features(attrs, base_dir)
    return None
