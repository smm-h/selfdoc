"""First-class support for strictcli-based projects.

Provides AST-based detection of strictcli usage, introspection of CLI
structure (App, commands, flags, args, groups), and Markdown page generation
for documentation.
"""

import ast
import os
import re
import stat
import tempfile

from selfdoc.build import _parse_frontmatter


# Matches the default per-command/per-group description templates so we can
# detect when a CLI page still has its auto-generated description (and should
# be recomputed) versus when a user has hand-edited the description (and we
# should preserve it).
#
# Templates produced by _render_command_page / _render_group_page when the
# command/group's help text is shorter than 50 characters:
#   "Reference for the {app_name} {name} command — usage, flags, arguments,
#    and examples for the {name} subcommand of the {app_name} CLI."
#   "Reference for the {app_name} {gname} command group — subcommands, flags,
#    arguments, and usage details for the {gname} group in the {app_name} CLI."
#
# And the CLI index template:
#   "Complete CLI reference for {app_name} — all available commands,
#    subcommands, flags, arguments, and usage examples with detailed
#    descriptions."
_DEFAULT_CLI_COMMAND_DESC_RE = re.compile(
    r"^Reference for the \S+ \S+ command — "
    r"usage, flags, arguments, and examples for the \S+ subcommand "
    r"of the \S+ CLI\.?$"
)
_DEFAULT_CLI_GROUP_DESC_RE = re.compile(
    r"^Reference for the \S+ \S+ command group — "
    r"subcommands, flags, arguments, and usage details "
    r"for the \S+ group in the \S+ CLI\.?$"
)
_DEFAULT_CLI_INDEX_DESC_RE = re.compile(
    r"^Complete CLI reference for \S+ — "
    r"all available commands, subcommands, flags, arguments, "
    r"and usage examples with detailed descriptions\.?$"
)


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------


def uses_strictcli(source_paths, base_dir):
    """Return True if any Python file in *source_paths* imports strictcli.

    Detection is AST-based: only real ``import strictcli`` or
    ``from strictcli import ...`` statements are considered (strings and
    comments are ignored).
    """
    for sp in source_paths:
        root = os.path.join(base_dir, sp.rstrip("/"))
        if not os.path.isdir(root):
            continue
        for dirpath, _dirs, filenames in os.walk(root):
            for fname in filenames:
                if not fname.endswith(".py"):
                    continue
                full = os.path.join(dirpath, fname)
                if _file_imports_strictcli(full):
                    return True
    return False


def _file_imports_strictcli(filepath):
    """Check whether a single Python file imports strictcli via AST."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            source = f.read()
    except OSError:
        return False
    try:
        tree = ast.parse(source, filename=filepath)
    except SyntaxError:
        return False
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "strictcli" or alias.name.startswith("strictcli."):
                    return True
        elif isinstance(node, ast.ImportFrom):
            if node.module and (
                node.module == "strictcli"
                or node.module.startswith("strictcli.")
            ):
                return True
    return False


# ---------------------------------------------------------------------------
# AST helpers
# ---------------------------------------------------------------------------


def _const_value(node):
    """Extract a constant value from an AST node, or return None."""
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        # e.g. ``str``, ``bool`` accessed as module attributes
        return ast.dump(node)
    return None


def _keyword_str(call_node, name):
    """Return the string value of keyword *name* in a Call node, or None."""
    for kw in call_node.keywords:
        if kw.arg == name:
            val = _const_value(kw.value)
            if val is not None:
                return str(val)
    return None


def _keyword_bool(call_node, name, default=None):
    """Return the bool value of keyword *name* in a Call node, or *default*."""
    for kw in call_node.keywords:
        if kw.arg == name:
            val = _const_value(kw.value)
            if isinstance(val, bool):
                return val
    return default


def _positional_str(call_node, index):
    """Return the string value of the positional arg at *index*, or None."""
    if index < len(call_node.args):
        val = _const_value(call_node.args[index])
        if val is not None:
            return str(val)
    return None


def _type_name(node):
    """Extract a human-readable type name from an AST node."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


# ---------------------------------------------------------------------------
# Introspection
# ---------------------------------------------------------------------------


def extract_cli_structure(source_paths, base_dir):
    """Walk Python files and extract the strictcli App structure via AST.

    Returns a dict describing the app, its commands, flags, args, and
    groups -- or None if no ``strictcli.App(...)`` call is found.
    """
    for sp in source_paths:
        root = os.path.join(base_dir, sp.rstrip("/"))
        if not os.path.isdir(root):
            continue
        for dirpath, _dirs, filenames in os.walk(root):
            for fname in sorted(filenames):
                if not fname.endswith(".py"):
                    continue
                full = os.path.join(dirpath, fname)
                result = _extract_from_file(full)
                if result is not None:
                    return result
    return None


def _extract_from_file(filepath):
    """Try to extract the CLI structure from a single Python file."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            source = f.read()
    except OSError:
        return None
    try:
        tree = ast.parse(source, filename=filepath)
    except SyntaxError:
        return None

    # Step 1: find the App(...) assignment to get app name/version/help
    # and figure out which variable name is bound to the App.
    app_info = None
    app_var = None

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name) and isinstance(node.value, ast.Call):
                call = node.value
                if _is_strictcli_app_call(call):
                    app_var = target.id
                    app_info = {
                        "app_name": (
                            _positional_str(call, 0)
                            or _keyword_str(call, "name")
                            or ""
                        ),
                        "app_version": _keyword_str(call, "version") or "",
                        "app_help": _keyword_str(call, "help") or "",
                    }
                    break

    if app_info is None or app_var is None:
        return None

    # Step 2: find group(...) calls on the app variable
    # Map group variable name -> group info dict
    groups = {}
    group_var_to_name = {}

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name) and isinstance(node.value, ast.Call):
                call = node.value
                if _is_method_call(call, app_var, "group"):
                    gname = (
                        _positional_str(call, 0)
                        or _keyword_str(call, "name")
                        or ""
                    )
                    ghelp = _keyword_str(call, "help") or ""
                    group_var_to_name[target.id] = gname
                    groups[gname] = {
                        "name": gname,
                        "help": ghelp,
                        "commands": [],
                    }

    # Step 3: walk top-level statements to find decorated functions
    # (commands registered on app or on group variables)
    commands = []

    for node in ast.iter_child_nodes(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        cmd = _extract_command_from_func(node, app_var, group_var_to_name)
        if cmd is None:
            continue

        owner = cmd.pop("_owner", None)
        if owner is not None and owner in groups:
            groups[owner]["commands"].append(cmd)
        else:
            commands.append(cmd)

    app_info["commands"] = commands
    app_info["groups"] = list(groups.values())
    return app_info


def _is_strictcli_app_call(call_node):
    """Return True if *call_node* is ``strictcli.App(...)``."""
    func = call_node.func
    if isinstance(func, ast.Attribute) and func.attr == "App":
        if isinstance(func.value, ast.Name) and func.value.id == "strictcli":
            return True
    # Also handle ``from strictcli import App; App(...)``
    if isinstance(func, ast.Name) and func.id == "App":
        return True
    return False


def _is_method_call(call_node, obj_name, method_name):
    """Return True if *call_node* is ``obj_name.method_name(...)``."""
    func = call_node.func
    if isinstance(func, ast.Attribute) and func.attr == method_name:
        if isinstance(func.value, ast.Name) and func.value.id == obj_name:
            return True
    return False


def _extract_command_from_func(func_node, app_var, group_var_to_name):
    """Extract command info from a decorated function definition.

    Returns a dict with command info (and ``_owner`` key for group
    assignment), or None if the function is not a command.
    """
    cmd_info = None
    flags = []
    args = []

    for dec in func_node.decorator_list:
        if not isinstance(dec, ast.Call):
            continue

        # @app.command("name", help="...")
        # @group_var.command("name", help="...")
        if isinstance(dec.func, ast.Attribute) and dec.func.attr == "command":
            if isinstance(dec.func.value, ast.Name):
                owner_var = dec.func.value.id
                cname = (
                    _positional_str(dec, 0) or _keyword_str(dec, "name") or ""
                )
                chelp = _keyword_str(dec, "help") or ""

                owner = None
                if owner_var == app_var:
                    owner = None  # top-level command
                elif owner_var in group_var_to_name:
                    owner = group_var_to_name[owner_var]
                else:
                    continue

                cmd_info = {
                    "name": cname,
                    "help": chelp,
                    "_owner": owner,
                }

        # @strictcli.flag("name", type=str, help="...", ...)
        flag = _parse_flag_decorator(dec)
        if flag is not None:
            flags.append(flag)

        # @strictcli.arg("name", help="...", ...)
        arg = _parse_arg_decorator(dec)
        if arg is not None:
            args.append(arg)

    if cmd_info is None:
        return None

    cmd_info["flags"] = flags
    cmd_info["args"] = args
    return cmd_info


def _parse_flag_decorator(dec_call):
    """Parse a ``@strictcli.flag(...)`` or ``@flag(...)`` decorator.

    Returns a flag info dict or None.
    """
    func = dec_call.func
    is_flag = False
    if isinstance(func, ast.Attribute) and func.attr == "flag":
        if isinstance(func.value, ast.Name) and func.value.id == "strictcli":
            is_flag = True
    elif isinstance(func, ast.Name) and func.id == "flag":
        is_flag = True

    if not is_flag:
        return None

    fname = _positional_str(dec_call, 0) or _keyword_str(dec_call, "name") or ""
    fhelp = _keyword_str(dec_call, "help") or ""
    fshort = _keyword_str(dec_call, "short")
    fenv = _keyword_str(dec_call, "env")

    # type
    ftype = "str"
    for kw in dec_call.keywords:
        if kw.arg == "type":
            tname = _type_name(kw.value)
            if tname:
                ftype = tname

    # default
    fdefault = None
    for kw in dec_call.keywords:
        if kw.arg == "default":
            val = _const_value(kw.value)
            if val is not None:
                fdefault = str(val)

    return {
        "name": fname,
        "type": ftype,
        "help": fhelp,
        "short": fshort,
        "default": fdefault,
        "env": fenv,
    }


def _parse_arg_decorator(dec_call):
    """Parse a ``@strictcli.arg(...)`` or ``@arg(...)`` decorator.

    Returns an arg info dict or None.
    """
    func = dec_call.func
    is_arg = False
    if isinstance(func, ast.Attribute) and func.attr == "arg":
        if isinstance(func.value, ast.Name) and func.value.id == "strictcli":
            is_arg = True
    elif isinstance(func, ast.Name) and func.id == "arg":
        is_arg = True

    if not is_arg:
        return None

    aname = _positional_str(dec_call, 0) or _keyword_str(dec_call, "name") or ""
    ahelp = _keyword_str(dec_call, "help") or ""
    arequired = _keyword_bool(dec_call, "required", default=True)

    return {
        "name": aname,
        "help": ahelp,
        "required": arequired,
    }


# ---------------------------------------------------------------------------
# Page generation
# ---------------------------------------------------------------------------


def expected_cli_page_filenames(cli_structure):
    """Return the list of filenames ``generate_cli_pages`` would write.

    Used by the stale-file cleanup pass to know which CLI page names are
    "current" so the generated pages from a prior run are not deleted as
    stale before the new pages have been written.
    """
    if cli_structure is None:
        return []
    names = ["cli-index.md"]
    for cmd in cli_structure.get("commands", []):
        names.append(f"cli-{cmd['name']}.md")
    for grp in cli_structure.get("groups", []):
        names.append(f"cli-{grp['name']}.md")
    return names


def _read_existing_cli_description(filepath, default_pattern):
    """Return the user-customized ``description`` from a CLI page.

    Returns ``None`` if the file does not exist, has no ``description`` key,
    has an empty description, or still has the default auto-generated
    description matching *default_pattern* (in which case the caller should
    recompute it).

    Truncated default descriptions (e.g. ``chelp[:155]`` cut mid-sentence)
    are also treated as default-and-overwritable: they are detected by
    checking whether the existing description is a prefix of the freshly
    computed default. The caller passes the freshly computed default via
    *default_pattern* when it is a plain string, or a compiled regex for the
    fallback template form. To support both, this helper accepts either a
    compiled regex (matched against the value) or a plain string (compared
    as a prefix match against the value).
    """
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
    except OSError:
        return None

    metadata, _ = _parse_frontmatter(content)
    raw = metadata.get("description")
    if raw is None or not isinstance(raw, str):
        return None

    # Strip wrapping quotes (single or double) that may survive the simple
    # parser in build.py.
    value = raw.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        value = value[1:-1].strip()

    if not value:
        return None

    if hasattr(default_pattern, "match"):
        if default_pattern.match(value):
            return None
    else:
        # Plain string: treat as default when the existing value is the
        # current default (exact) OR is a prefix of it (truncated default
        # from a prior ``chelp[:155]`` run). This prevents stale truncated
        # defaults from being treated as handwritten.
        if value == default_pattern or default_pattern.startswith(value):
            return None

    return value


def generate_cli_pages(cli_structure, docs_dir):
    """Generate Markdown documentation pages from *cli_structure*.

    Creates an index page and one page per top-level command group.
    All pages have ``generated: true`` frontmatter and read-only
    permissions (0o444).

    Returns a list of generated filenames (relative to *docs_dir*).
    """
    os.makedirs(docs_dir, exist_ok=True)
    generated = []

    app_name = cli_structure.get("app_name", "")
    app_help = cli_structure.get("app_help", "")
    app_version = cli_structure.get("app_version", "")
    commands = cli_structure.get("commands", [])
    groups = cli_structure.get("groups", [])

    # -- Index page --
    default_index_desc = (
        f"Complete CLI reference for {app_name} — "
        f"all available commands, subcommands, flags, arguments, "
        f"and usage examples with detailed descriptions."
    )
    index_path = os.path.join(docs_dir, "cli-index.md")
    existing_index_desc = _read_existing_cli_description(
        index_path, _DEFAULT_CLI_INDEX_DESC_RE,
    )
    cli_index_desc = (
        existing_index_desc
        if existing_index_desc is not None
        else default_index_desc
    )
    index_lines = [
        "---",
        f"title: {app_name} CLI Reference",
        f'description: "{cli_index_desc}"',
        "generated: true",
        'nav_group: "CLI Reference"',
        "nav_order: 0",
        "order: 91",
        "---",
        "<!-- generated by selfdoc gen (strictcli), do not edit -->",
        "",
        f"# {app_name} CLI Reference",
        "",
    ]
    if app_help:
        index_lines.append(app_help)
        index_lines.append("")
    if app_version:
        index_lines.append(f"Version: {app_version}")
        index_lines.append("")

    if commands:
        index_lines.append("## Commands")
        index_lines.append("")
        for cmd in commands:
            fname = f"cli-{cmd['name']}.html"
            index_lines.append(f"- [{cmd['name']}]({fname}) -- {cmd.get('help', '')}")
        index_lines.append("")

    if groups:
        index_lines.append("## Command Groups")
        index_lines.append("")
        for grp in groups:
            fname = f"cli-{grp['name']}.html"
            index_lines.append(f"- [{grp['name']}]({fname}) -- {grp.get('help', '')}")
        index_lines.append("")

    index_filename = "cli-index.md"
    _write_page(
        os.path.join(docs_dir, index_filename),
        "\n".join(index_lines),
    )
    generated.append(index_filename)

    # Build alphabetical ordering for all command/group pages
    all_names = sorted(
        [cmd["name"] for cmd in commands] + [grp["name"] for grp in groups]
    )
    name_to_nav_order = {name: idx + 1 for idx, name in enumerate(all_names)}

    # -- One page per top-level command --
    for cmd in commands:
        fname = f"cli-{cmd['name']}.md"
        out_path = os.path.join(docs_dir, fname)
        content = _render_command_page(
            cmd, app_name, name_to_nav_order[cmd["name"]],
            existing_path=out_path,
        )
        _write_page(out_path, content)
        generated.append(fname)

    # -- One page per group --
    for grp in groups:
        fname = f"cli-{grp['name']}.md"
        out_path = os.path.join(docs_dir, fname)
        content = _render_group_page(
            grp, app_name, name_to_nav_order[grp["name"]],
            existing_path=out_path,
        )
        _write_page(out_path, content)
        generated.append(fname)

    return generated


def _write_page(filepath, content):
    """Write a generated page atomically with read-only permissions."""
    # Make writable if it already exists with 0o444
    if os.path.isfile(filepath):
        try:
            os.chmod(filepath, stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            pass
    dir_name = os.path.dirname(filepath)
    fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.chmod(tmp_path, 0o444)
        os.replace(tmp_path, filepath)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _render_command_page(cmd, app_name, nav_order, existing_path=None):
    """Render a Markdown page for a single command.

    If *existing_path* points to an existing page whose ``description``
    frontmatter has been hand-edited (i.e. is neither the default
    ``chelp[:155]`` truncation nor the long-form default template), that
    description is preserved instead of recomputing it.
    """
    name = cmd["name"]
    chelp = cmd.get("help", "")
    flags = cmd.get("flags", [])
    args = cmd.get("args", [])

    if chelp and len(chelp) >= 50:
        default_desc = chelp[:155]
        default_pattern = default_desc
    else:
        default_desc = (
            f"Reference for the {app_name} {name} command — "
            f"usage, flags, arguments, and examples for the {name} subcommand "
            f"of the {app_name} CLI."
        )
        default_pattern = _DEFAULT_CLI_COMMAND_DESC_RE

    existing_desc = None
    if existing_path is not None:
        existing_desc = _read_existing_cli_description(
            existing_path, default_pattern,
        )
    cmd_desc = existing_desc if existing_desc is not None else default_desc
    lines = [
        "---",
        f"title: {app_name} {name}",
        f'description: "{cmd_desc}"',
        "generated: true",
        'nav_group: "CLI Reference"',
        f"nav_order: {nav_order}",
        "---",
        "<!-- generated by selfdoc gen (strictcli), do not edit -->",
        "",
        f"# {app_name} {name}",
        "",
    ]
    if chelp:
        lines.append(chelp)
        lines.append("")

    if flags:
        lines.append("## Flags")
        lines.append("")
        lines.append("| Name | Short | Type | Default | Env | Description |")
        lines.append("|------|-------|------|---------|-----|-------------|")
        for fl in flags:
            short = fl.get("short") or ""
            ftype = fl.get("type", "str")
            default = fl.get("default") or ""
            env = fl.get("env") or ""
            desc = fl.get("help", "")
            lines.append(
                f"| `--{fl['name']}` | {_fmt_short(short)} | {ftype} | {default} | {env} | {desc} |"
            )
        lines.append("")

    if args:
        lines.append("## Arguments")
        lines.append("")
        lines.append("| Name | Required | Description |")
        lines.append("|------|----------|-------------|")
        for ar in args:
            req = "yes" if ar.get("required", True) else "no"
            lines.append(f"| `{ar['name']}` | {req} | {ar.get('help', '')} |")
        lines.append("")

    return "\n".join(lines)


def _render_group_page(grp, app_name, nav_order, existing_path=None):
    """Render a Markdown page for a command group and its subcommands.

    If *existing_path* points to an existing page whose ``description``
    frontmatter has been hand-edited (i.e. is neither the default
    ``ghelp[:155]`` truncation nor the long-form default template), that
    description is preserved instead of recomputing it.
    """
    gname = grp["name"]
    ghelp = grp.get("help", "")
    subcmds = grp.get("commands", [])

    if ghelp and len(ghelp) >= 50:
        default_desc = ghelp[:155]
        default_pattern = default_desc
    else:
        default_desc = (
            f"Reference for the {app_name} {gname} command group — "
            f"subcommands, flags, arguments, and usage details "
            f"for the {gname} group in the {app_name} CLI."
        )
        default_pattern = _DEFAULT_CLI_GROUP_DESC_RE

    existing_desc = None
    if existing_path is not None:
        existing_desc = _read_existing_cli_description(
            existing_path, default_pattern,
        )
    grp_desc = existing_desc if existing_desc is not None else default_desc
    lines = [
        "---",
        f"title: {app_name} {gname}",
        f'description: "{grp_desc}"',
        "generated: true",
        'nav_group: "CLI Reference"',
        f"nav_order: {nav_order}",
        "---",
        "<!-- generated by selfdoc gen (strictcli), do not edit -->",
        "",
        f"# {app_name} {gname}",
        "",
    ]
    if ghelp:
        lines.append(ghelp)
        lines.append("")

    for cmd in subcmds:
        cname = cmd["name"]
        chelp = cmd.get("help", "")
        flags = cmd.get("flags", [])
        args = cmd.get("args", [])

        lines.append(f"## {gname} {cname}")
        lines.append("")
        if chelp:
            lines.append(chelp)
            lines.append("")

        if flags:
            lines.append("### Flags")
            lines.append("")
            lines.append("| Name | Short | Type | Default | Env | Description |")
            lines.append("|------|-------|------|---------|-----|-------------|")
            for fl in flags:
                short = fl.get("short") or ""
                ftype = fl.get("type", "str")
                default = fl.get("default") or ""
                env = fl.get("env") or ""
                desc = fl.get("help", "")
                lines.append(
                    f"| `--{fl['name']}` | {_fmt_short(short)} | {ftype} | {default} | {env} | {desc} |"
                )
            lines.append("")

        if args:
            lines.append("### Arguments")
            lines.append("")
            lines.append("| Name | Required | Description |")
            lines.append("|------|----------|-------------|")
            for ar in args:
                req = "yes" if ar.get("required", True) else "no"
                lines.append(f"| `{ar['name']}` | {req} | {ar.get('help', '')} |")
            lines.append("")

    return "\n".join(lines)


def _fmt_short(short):
    """Format a short flag for table display."""
    if short:
        return f"`-{short}`"
    return ""
