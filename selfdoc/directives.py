"""Directive parser for :::name arg blocks in markdown files.

Directive syntax:
    :::name arg
    optional body lines
    :::

Directives inside fenced code blocks (``` or ~~~) are ignored.
Unclosed directives at EOF raise DirectiveError.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# Matches an opening directive line: :::word optionalArg
_OPEN_RE = re.compile(r"^:::(\w+)(?:\s+(.*))?$")

# Matches a closing directive line: exactly ::: with nothing else
_CLOSE_RE = re.compile(r"^:::$")

# Matches a fenced code block delimiter (``` or ~~~, optionally with info string)
_FENCE_RE = re.compile(r"^(`{3,}|~{3,})")


class DirectiveError(Exception):
    """Raised when a directive is malformed (e.g. unclosed at EOF)."""


@dataclass
class Directive:
    """A parsed directive block."""

    name: str
    arg: str
    body: list[str] = field(default_factory=list)
    line_number: int = 0


def _walk_blocks(content: str):
    """Shared state machine for fence-tracking and directive detection.

    Yields one of three event types per logical unit:
      ("line", line)                         — non-directive line (may be inside a fence)
      ("directive", name, arg, body, line_num) — a complete directive block
      ("unclosed", name, line_num)           — unclosed directive at EOF
    """
    lines = content.split("\n") if content else []

    fence_char: str | None = None  # char used to open the fence (` or ~)
    fence_len: int = 0  # length needed to close

    # Directive accumulation state
    dir_name: str | None = None
    dir_arg: str = ""
    dir_body: list[str] = []
    dir_line: int = 0

    for line_idx, line in enumerate(lines):
        line_num = line_idx + 1  # 1-based
        stripped = line.strip()

        # --- code fence tracking ---
        fence_match = _FENCE_RE.match(stripped)
        if fence_match:
            marker = fence_match.group(1)
            if fence_char is None:
                fence_char = marker[0]
                fence_len = len(marker)
            elif marker[0] == fence_char and len(marker) >= fence_len:
                fence_char = None
                fence_len = 0
            # Fence delimiters are always non-directive content
            yield ("line", line)
            continue

        if fence_char is not None:
            # Inside a code fence — always non-directive
            yield ("line", line)
            continue

        # --- directive parsing (outside code fences) ---
        if dir_name is None:
            open_match = _OPEN_RE.match(stripped)
            if open_match:
                dir_name = open_match.group(1)
                dir_arg = (open_match.group(2) or "").strip()
                dir_body = []
                dir_line = line_num
            else:
                yield ("line", line)
        else:
            if _CLOSE_RE.match(stripped):
                yield ("directive", dir_name, dir_arg, dir_body, dir_line)
                dir_name = None
                dir_arg = ""
                dir_body = []
            else:
                dir_body.append(line)

    if dir_name is not None:
        yield ("unclosed", dir_name, dir_line)


def parse_directives(content: str) -> list[Directive]:
    """Extract all directive blocks from markdown content.

    Returns a list of Directive dataclass instances in document order.
    Directives inside fenced code blocks are ignored.
    Raises DirectiveError if a directive is opened but never closed.
    """
    directives: list[Directive] = []
    for event in _walk_blocks(content):
        if event[0] == "directive":
            _, name, arg, body, line_num = event
            directives.append(Directive(name=name, arg=arg, body=body, line_number=line_num))
        elif event[0] == "unclosed":
            _, name, line_num = event
            raise DirectiveError(
                f"Unclosed directive ':::{name}' opened at line {line_num}"
            )
    return directives


def resolve_directives(content: str, resolver: callable) -> str:
    """Replace each directive block with the output of resolver(name, arg, body).

    Non-directive content passes through unchanged. Directives inside fenced
    code blocks are left as-is (they are not directives).
    """
    output: list[str] = []
    for event in _walk_blocks(content):
        if event[0] == "line":
            output.append(event[1])
        elif event[0] == "directive":
            _, name, arg, body, _line_num = event
            output.append(resolver(name, arg, body))
        elif event[0] == "unclosed":
            _, name, _line_num = event
            raise DirectiveError(
                f"Unclosed directive ':::{name}' during resolution"
            )
    return "\n".join(output)
