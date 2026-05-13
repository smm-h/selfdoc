"""Content directives -- directives that transform body content into styled HTML.

These directives do not need language extractors. They handle callouts
(note, warning, tip, danger, important) and the glossary list.
"""

from __future__ import annotations

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


# -- Dispatch -----------------------------------------------------------------

CONTENT_DIRECTIVES: set[str] = {
    "callout-note", "callout-warning", "callout-tip",
    "callout-danger", "callout-important", "list-glossary",
}


def resolve_content(name: str, attrs: dict, body: list[str]) -> str | None:
    """Resolve a content directive. Returns None if name is not a content directive."""
    if name in _CALLOUT_TYPES:
        return _resolve_callout(name, _CALLOUT_TYPES[name], body)
    if name == "list-glossary":
        return resolve_glossary(body)
    return None
