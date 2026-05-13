"""Resolver factory -- dispatches directives to language-specific extractors."""

import importlib.util
import os
import re

from selfdoc.extractors import EXTRACTORS


def _resolve_glossary(body):
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


def _load_custom_directive(script_path, name):
    """Dynamically import a custom directive script and return its module.

    Args:
        script_path: Absolute path to the Python script.
        name: Directive name (used as the module name for importlib).

    Returns:
        The loaded module, or None if loading fails.

    Raises:
        FileNotFoundError: If the script file does not exist.
        AttributeError: If the module has no 'resolve' callable.
        Exception: Any other import/load error.
    """
    if not os.path.isfile(script_path):
        raise FileNotFoundError(f"custom directive script not found: {script_path}")

    spec = importlib.util.spec_from_file_location(
        f"selfdoc_custom_{name}", script_path
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    if not callable(getattr(module, "resolve", None)):
        raise AttributeError(
            f"custom directive script '{script_path}' has no callable 'resolve'"
        )

    return module


def make_resolver(config, base_dir="."):
    """Create a resolver function for the project's language.

    Custom directives from config["directives"] take priority over built-in
    language extractors. Each entry maps a directive name to a relative path
    (from project root) of a Python script that exports resolve(attrs, config, body).

    Args:
        config: Validated config dict from selfdoc.json.
        base_dir: Project root directory (for resolving relative paths).

    Returns:
        A callable(name, attrs, body) -> str that resolves directives to markdown.
    """
    language = config["language"]
    source_paths = config["source"]
    custom_directives = config.get("directives", {})
    # Normalize base_dir to absolute for consistent path resolution
    base_dir = os.path.abspath(base_dir)

    # Look up the language extractor from the registry
    extractor = EXTRACTORS.get(language)

    def resolve(name, attrs, body):
        # Custom directives take priority over built-in names
        if name in custom_directives:
            script_rel = custom_directives[name]
            script_path = os.path.join(base_dir, script_rel)
            try:
                module = _load_custom_directive(script_path, name)
                return module.resolve(attrs, config, body)
            except Exception as exc:
                return (
                    f"> *[selfdoc: custom directive '{name}' failed: {exc}]*"
                )

        # Built-in content-formatting directives (not language-specific)
        if name == "list-glossary":
            return _resolve_glossary(body)

        # Dispatch to the language extractor
        if extractor is None:
            return (
                f"> *[selfdoc: unsupported language '{language}' "
                f"for :::{name}]*"
            )

        return extractor.extract(name, attrs, body, source_paths, base_dir)

    return resolve
