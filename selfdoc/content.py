"""Content directives -- directives that transform body content into styled HTML.

These directives do not need language extractors. They handle callouts
(note, warning, tip, danger, important), the glossary list, and
filesystem/project-metadata directives (list-tree, table-dep, list-features,
list-modules, table-commands, table-directives, table-config-schema, var).
"""

from __future__ import annotations

import ast
import json
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


# -- list-modules directive ----------------------------------------------------


def resolve_list_modules(attrs: dict, config: dict, base_dir: str) -> str:
    """List source modules with file paths and docstring summaries."""
    path = attrs.get("path", "")
    if not path:
        return "> *[selfdoc: list-modules requires a path attribute]*"

    full_path = os.path.join(base_dir, path)
    if not os.path.isdir(full_path):
        return f"> *[selfdoc: directory '{path}' not found]*"

    from selfdoc.extractors import EXTRACTORS

    language = config["language"]
    extractor = EXTRACTORS.get(language)
    if extractor is None:
        return f"> *[selfdoc: unsupported language '{language}']*"

    extensions = set(extractor.file_extensions())

    modules: list[tuple[str, str, str | None]] = []  # (module_name, rel_path, docstring)
    for dirpath, _dirnames, filenames in os.walk(full_path):
        for fname in sorted(filenames):
            _root, ext = os.path.splitext(fname)
            if ext not in extensions:
                continue
            file_path = os.path.join(dirpath, fname)
            rel_path = os.path.relpath(file_path, base_dir)
            module_name = _file_to_module_name(rel_path, language)
            if module_name is None:
                continue
            docstring = _extract_first_line_any(file_path, language)
            modules.append((module_name, rel_path, docstring))

    modules.sort(key=lambda t: t[0])

    if not modules:
        return f"> *[selfdoc: no modules found in '{path}']*"

    lines = []
    for module_name, rel_path, docstring in modules:
        if docstring:
            lines.append(f"- **{module_name}** (`{rel_path}`): {docstring}")
        else:
            lines.append(f"- **{module_name}** (`{rel_path}`)")

    return "\n".join(lines)


def _file_to_module_name(rel_path: str, language: str) -> str | None:
    """Convert a relative file path to a module name.

    For Python: ``selfdoc/config.py`` -> ``selfdoc.config``.
    For Go/TypeScript/JavaScript: ``pkg/handler.go`` -> ``pkg/handler``.
    """
    root, _ext = os.path.splitext(rel_path)
    if language == "python":
        if root.endswith("/__init__") or root == "__init__":
            root = root.rsplit("/__init__", 1)[0] if "/" in root else ""
        if not root:
            return None
        return root.replace(os.sep, ".").replace("/", ".")
    return root.replace(os.sep, "/")


def _extract_first_line_any(file_path: str, language: str) -> str | None:
    """Extract the first line of a module docstring, language-aware.

    For Python, uses AST. For other languages, returns None (no docstring
    convention that can be reliably extracted without parsing).
    """
    if language == "python":
        from selfdoc.utils import extract_module_docstring
        return extract_module_docstring(file_path)
    return None


# -- table-commands directive --------------------------------------------------


def resolve_table_commands(attrs: dict, config: dict, base_dir: str) -> str:
    """Produce a Markdown table of CLI commands from strictcli structure."""
    path = attrs.get("path", "")
    if not path:
        return "> *[selfdoc: table-commands requires a path attribute]*"

    from selfdoc.strictcli_support import read_schema_json

    cli = read_schema_json(base_dir)
    if cli is None:
        return f"> *[selfdoc: no strictcli app found in '{path}']*"

    rows = []
    rows.append("| Command | Description |")
    rows.append("| --- | --- |")

    for cmd in cli.get("commands", []):
        rows.append(f"| `{cmd['name']}` | {cmd.get('help', '')} |")

    for grp in cli.get("groups", []):
        gname = grp["name"]
        ghelp = grp.get("help", "")
        rows.append(f"| **{gname}** | {ghelp} |")
        for cmd in grp.get("commands", []):
            rows.append(f"| `{gname} {cmd['name']}` | {cmd.get('help', '')} |")

    if len(rows) == 2:
        return f"> *[selfdoc: no commands found in '{path}']*"

    return "\n".join(rows)


# -- table-directives directive ------------------------------------------------


def resolve_table_directives() -> str:
    """Produce a Markdown table of all core built-in directives."""
    from selfdoc.catalog import CORE_DIRECTIVES

    rows = []
    rows.append("| Directive | Description |")
    rows.append("| --- | --- |")

    for name in sorted(CORE_DIRECTIVES):
        spec = CORE_DIRECTIVES[name]
        rows.append(f"| `{name}` | {spec.description} |")

    return "\n".join(rows)


# -- table-config-schema directive ---------------------------------------------


def resolve_table_config_schema() -> str:
    """Produce a Markdown table of selfdoc.json configuration fields."""
    from selfdoc.config import CONFIG_SCHEMA

    rows = []
    rows.append("| Field | Required | Description |")
    rows.append("| --- | --- | --- |")

    for spec in CONFIG_SCHEMA:
        if spec.internal:
            continue
        required = "yes" if spec.required else "no"
        rows.append(f"| `{spec.name}` | {required} | {spec.description} |")

    return "\n".join(rows)


# -- var directive -------------------------------------------------------------


def resolve_var(attrs: dict, config: dict, base_dir: str) -> str:
    """Interpolate a project metadata value."""
    key = attrs.get("key", "")
    if not key:
        return "> *[selfdoc: var requires a key attribute]*"

    if key == "project.language":
        return config.get("language", "unknown")

    if key == "project.description":
        desc = config.get("description")
        if desc:
            return desc
        # Fall through to pyproject.toml/package.json
        return _read_project_description(base_dir)

    if key == "project.name":
        return _read_project_field(base_dir, "name")

    if key == "project.version":
        return _read_project_field(base_dir, "version")

    return f"> *[selfdoc: unknown var key '{key}']*"


def _read_project_field(base_dir: str, field: str) -> str:
    """Read a project metadata field from pyproject.toml, package.json, or go.mod."""
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
        # Go doesn't have a version field in go.mod
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


def _read_project_description(base_dir: str) -> str:
    """Read the project description from pyproject.toml or package.json."""
    pyproject = os.path.join(base_dir, "pyproject.toml")
    if os.path.isfile(pyproject):
        try:
            import tomllib
        except ModuleNotFoundError:
            try:
                import tomli as tomllib  # type: ignore[no-redef]
            except ModuleNotFoundError:
                return "unknown"
        try:
            with open(pyproject, "rb") as f:
                data = tomllib.load(f)
            return str(data.get("project", {}).get("description", "unknown"))
        except Exception:
            return "unknown"

    pkg_json = os.path.join(base_dir, "package.json")
    if os.path.isfile(pkg_json):
        try:
            with open(pkg_json, "r", encoding="utf-8") as f:
                data = json.load(f)
            return str(data.get("description", "unknown"))
        except (OSError, json.JSONDecodeError):
            return "unknown"

    return "unknown"


# -- Dispatch -----------------------------------------------------------------

CONTENT_DIRECTIVES: set[str] = {
    "callout-note", "callout-warning", "callout-tip",
    "callout-danger", "callout-important", "list-glossary",
    "list-tree", "table-dep", "list-features",
    "list-modules", "table-commands", "table-directives",
    "table-config-schema", "var",
}


def resolve_content(
    name: str, attrs: dict, body: list[str], base_dir: str = ".",
    *, config: dict | None = None,
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
    if name == "list-modules":
        if config is None:
            return "> *[selfdoc: list-modules requires project config]*"
        return resolve_list_modules(attrs, config, base_dir)
    if name == "table-commands":
        if config is None:
            return "> *[selfdoc: table-commands requires project config]*"
        return resolve_table_commands(attrs, config, base_dir)
    if name == "table-directives":
        return resolve_table_directives()
    if name == "table-config-schema":
        return resolve_table_config_schema()
    if name == "var":
        if config is None:
            return "> *[selfdoc: var requires project config]*"
        return resolve_var(attrs, config, base_dir)
    return None
