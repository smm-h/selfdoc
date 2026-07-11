"""Content directives -- re-export shim + table-commands registration.

The core content directive implementation lives in selfdoc_core.content.
This module re-exports everything from core and adds the table-commands
directive, which depends on selfdoc.strictcli_support (and therefore
cannot live in core, which must not import from selfdoc).

The table-commands directive is registered via the directive registry
so that selfdoc_core.content.resolve_content() can dispatch to it.
"""

from __future__ import annotations

import os

from selfdoc_core.content import *  # noqa: F401,F403
from selfdoc_core.content import CONTENT_DIRECTIVES as _CORE_CONTENT_DIRECTIVES
from selfdoc_core.tables import render_markdown_table


# -- table-commands directive (selfdoc-specific) ------------------------------


def resolve_table_commands(attrs: dict, config: dict, base_dir: str) -> str:
    """Produce a Markdown table of CLI commands from strictcli structure.

    The ``.strictcli/schema.json`` is discovered automatically by walking the
    project root. When exactly one schema is found it is used. Zero or multiple
    matches are hard errors (:class:`SchemaDiscoveryError`); pass
    ``schema-dir="<dir>"`` to select one explicitly when discovery is ambiguous.
    """
    from selfdoc.strictcli_support import (
        SchemaDiscoveryError,
        discover_schema_dirs,
        read_schema_json,
    )

    schema_dir = attrs.get("schema-dir")
    if schema_dir:
        target_dir = schema_dir
        cli = read_schema_json(os.path.join(base_dir, target_dir))
        if cli is None:
            raise SchemaDiscoveryError(
                f"table-commands: no .strictcli/schema.json found in "
                f'schema-dir="{target_dir}" (relative to project root).'
            )
    else:
        candidates = discover_schema_dirs(base_dir)
        if not candidates:
            raise SchemaDiscoveryError(
                "table-commands: no .strictcli/schema.json found under the "
                "project root. Generate one with '<app> --dump-schema', or "
                'select it with schema-dir="<dir>".'
            )
        if len(candidates) > 1:
            listed = ", ".join(candidates)
            raise SchemaDiscoveryError(
                "table-commands: multiple .strictcli/schema.json found "
                f"({listed}). Disambiguate with "
                'schema-dir="<dir>" naming the directory that contains the '
                ".strictcli/ folder."
            )
        target_dir = candidates[0]
        cli = read_schema_json(os.path.join(base_dir, target_dir))
        if cli is None:
            # discover_schema_dirs already confirmed the file exists.
            raise SchemaDiscoveryError(
                f"table-commands: failed to read .strictcli/schema.json in "
                f"'{target_dir}'."
            )

    headers = ["Command", "Description"]
    rows = []

    for cmd in cli.get("commands", []):
        rows.append([f"`{cmd['name']}`", cmd.get("help", "")])

    for grp in cli.get("groups", []):
        gname = grp["name"]
        ghelp = grp.get("help", "")
        rows.append([f"**{gname}**", ghelp])
        for cmd in grp.get("commands", []):
            rows.append([f"`{gname} {cmd['name']}`", cmd.get("help", "")])

    if not rows:
        return f"> *[selfdoc: no commands found in '{target_dir}']*"

    return render_markdown_table(headers, rows)


def _table_commands_resolver(name, attrs, body, base_dir, *, config=None):
    """Directive registry adapter for table-commands."""
    if config is None:
        return "> *[selfdoc: table-commands requires project config]*"
    return resolve_table_commands(attrs, config, base_dir)


# Extended CONTENT_DIRECTIVES including table-commands
CONTENT_DIRECTIVES = _CORE_CONTENT_DIRECTIVES | {"table-commands"}


# -- Register table-commands in the directive registry ------------------------

from selfdoc_core import register_directive as _register_directive  # noqa: E402

try:
    _register_directive("table-commands", _table_commands_resolver)
except ValueError:
    # Already registered (e.g. module imported twice)
    pass
