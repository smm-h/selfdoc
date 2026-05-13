"""Directive parser for selfdoc's structured marker syntax.

Directive syntax:
    One-liner:   :-: name key="value" ...
    Block open:  :<: name [key="value" ...]
    Attr line:   :@: key="value"
    Body sep:    :=:
    Body line:   ::: content
    Block close: :>:

Directives inside fenced code blocks (``` or ~~~) are ignored.
Unclosed block directives at EOF raise DirectiveError.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# -- Marker regexes ----------------------------------------------------------

# One-liner: :-: name [attrs]
_ONELINER_RE = re.compile(r"^:-:\s+(\S+)(.*)$")

# Block open: :<: name [attrs]
_BLOCK_OPEN_RE = re.compile(r"^:<:\s+(\S+)(.*)$")

# Attribute line: :@: key="value"
_ATTR_LINE_RE = re.compile(r"^:@:\s+(.+)$")

# Body separator: :=:
_BODY_SEP_RE = re.compile(r"^:=:$")

# Body line: ::: content (strip 4-char prefix "::: "), or bare ::: for empty body line
_BODY_LINE_RE = re.compile(r"^::: (.*)$")
_BODY_LINE_EMPTY_RE = re.compile(r"^:::$")

# Block close: :>:
_BLOCK_CLOSE_RE = re.compile(r"^:>:$")

# Fenced code block delimiter (``` or ~~~, optionally with info string)
_FENCE_RE = re.compile(r"^(`{3,}|~{3,})")

# Attribute key="value" pair extractor
_ATTR_KV_RE = re.compile(r'(\w+)="([^"]*)"')


class DirectiveError(Exception):
    """Raised when a directive is malformed (e.g. unclosed at EOF)."""


@dataclass
class Directive:
    """A parsed directive block."""

    name: str
    attrs: dict[str, str] = field(default_factory=dict)
    body: list[str] = field(default_factory=list)
    line_number: int = 0


def _parse_attrs(text: str) -> dict[str, str]:
    """Extract all key="value" pairs from a string."""
    return dict(_ATTR_KV_RE.findall(text))


def _walk_blocks(content: str, valid_names: set[str] | None = None):
    """Shared state machine for fence-tracking and directive detection.

    Yields one of three event types per logical unit:
      ("line", line)                              -- non-directive line
      ("directive", name, attrs, body, line_num)  -- a complete directive
      ("unclosed", name, line_num)                -- unclosed block at EOF
    """
    lines = content.split("\n") if content else []

    # Fence tracking
    fence_char: str | None = None
    fence_len: int = 0

    # State machine: "idle", "in_fence", "in_block_attrs", "in_block_body"
    state = "idle"

    # Block accumulation
    block_name: str = ""
    block_attrs: dict[str, str] = {}
    block_body: list[str] = []
    block_line: int = 0

    def _validate_name(name: str, line_num: int) -> None:
        if valid_names is not None and name not in valid_names:
            raise DirectiveError(
                f"Unknown directive '{name}' at line {line_num}"
            )

    for line_idx, line in enumerate(lines):
        line_num = line_idx + 1
        stripped = line.strip()

        # -- Fence tracking (applies in idle and in_fence) --
        if state in ("idle", "in_fence"):
            fence_match = _FENCE_RE.match(stripped)
            if fence_match:
                marker = fence_match.group(1)
                if state == "idle":
                    fence_char = marker[0]
                    fence_len = len(marker)
                    state = "in_fence"
                    yield ("line", line)
                    continue
                else:  # in_fence
                    if marker[0] == fence_char and len(marker) >= fence_len:
                        state = "idle"
                        fence_char = None
                        fence_len = 0
                    yield ("line", line)
                    continue

        if state == "in_fence":
            yield ("line", line)
            continue

        # -- Outside fences: directive parsing --

        if state == "idle":
            # Check one-liner: :-: name [attrs]
            m = _ONELINER_RE.match(stripped)
            if m:
                name = m.group(1)
                _validate_name(name, line_num)
                attrs = _parse_attrs(m.group(2))
                yield ("directive", name, attrs, [], line_num)
                continue

            # Check block open: :<: name [attrs]
            m = _BLOCK_OPEN_RE.match(stripped)
            if m:
                block_name = m.group(1)
                _validate_name(block_name, line_num)
                block_attrs = _parse_attrs(m.group(2))
                block_body = []
                block_line = line_num
                state = "in_block_attrs"
                continue

            # Regular line
            yield ("line", line)

        elif state == "in_block_attrs":
            # :@: key="value"
            m = _ATTR_LINE_RE.match(stripped)
            if m:
                block_attrs.update(_parse_attrs(m.group(1)))
                continue

            # :=: separator -> transition to body
            if _BODY_SEP_RE.match(stripped):
                state = "in_block_body"
                continue

            # :>: close block (no body)
            if _BLOCK_CLOSE_RE.match(stripped):
                yield ("directive", block_name, dict(block_attrs), list(block_body), block_line)
                state = "idle"
                continue

            # Anything else is an error
            raise DirectiveError(
                f"Unexpected line inside directive block at line {line_num}: {stripped!r}"
            )

        elif state == "in_block_body":
            # ::: content (strip 4-char prefix), or bare ::: for empty body line
            m = _BODY_LINE_RE.match(stripped)
            if m:
                block_body.append(m.group(1))
                continue
            if _BODY_LINE_EMPTY_RE.match(stripped):
                block_body.append("")
                continue

            # :>: close block
            if _BLOCK_CLOSE_RE.match(stripped):
                yield ("directive", block_name, dict(block_attrs), list(block_body), block_line)
                state = "idle"
                continue

            # Anything else is an error
            raise DirectiveError(
                f"Unexpected line inside directive block at line {line_num}: {stripped!r}"
            )

    # EOF handling
    if state in ("in_block_attrs", "in_block_body"):
        yield ("unclosed", block_name, block_line)


def parse_directives(content: str, valid_names: set[str] | None = None) -> list[Directive]:
    """Extract all directive blocks from markdown content.

    Returns a list of Directive dataclass instances in document order.
    Directives inside fenced code blocks are ignored.
    Raises DirectiveError if a directive is opened but never closed,
    or if a directive name is not in valid_names (when provided).
    """
    directives: list[Directive] = []
    for event in _walk_blocks(content, valid_names=valid_names):
        if event[0] == "directive":
            _, name, attrs, body, line_num = event
            directives.append(
                Directive(name=name, attrs=attrs, body=body, line_number=line_num)
            )
        elif event[0] == "unclosed":
            _, name, line_num = event
            raise DirectiveError(
                f"Unclosed directive '{name}' opened at line {line_num}"
            )
    return directives


def resolve_directives(
    content: str, resolver: callable, valid_names: set[str] | None = None
) -> str:
    """Replace each directive with the output of resolver(name, attrs, body).

    Non-directive content passes through unchanged. Directives inside fenced
    code blocks are left as-is (they are not directives).
    """
    output: list[str] = []
    for event in _walk_blocks(content, valid_names=valid_names):
        if event[0] == "line":
            output.append(event[1])
        elif event[0] == "directive":
            _, name, attrs, body, _line_num = event
            output.append(resolver(name, attrs, body))
        elif event[0] == "unclosed":
            _, name, _line_num = event
            raise DirectiveError(
                f"Unclosed directive '{name}' during resolution"
            )
    return "\n".join(output)
