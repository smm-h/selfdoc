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


def parse_directives(content: str) -> list[Directive]:
    """Extract all directive blocks from markdown content.

    Returns a list of Directive dataclass instances in document order.
    Directives inside fenced code blocks are ignored.
    Raises DirectiveError if a directive is opened but never closed.
    """
    directives: list[Directive] = []
    lines = content.split("\n") if content else []

    # State: are we inside a fenced code block?
    fence_char: str | None = None  # the char used to open the fence (` or ~)
    fence_len: int = 0  # minimum length needed to close

    # State: are we inside a directive?
    current: Directive | None = None

    for line_idx, line in enumerate(lines):
        line_num = line_idx + 1  # 1-based
        stripped = line.strip()

        # --- code fence tracking ---
        fence_match = _FENCE_RE.match(stripped)
        if fence_match:
            marker = fence_match.group(1)
            if fence_char is None:
                # Opening a fence
                fence_char = marker[0]
                fence_len = len(marker)
            elif marker[0] == fence_char and len(marker) >= fence_len:
                # Closing the fence (same char, at least same length)
                fence_char = None
                fence_len = 0
            # If different char or shorter run, it's not a fence toggle
            continue

        # Inside a code fence: nothing is a directive
        if fence_char is not None:
            if current is not None:
                current.body.append(line)
            continue

        # --- directive parsing (outside code fences) ---
        if current is None:
            # Not inside a directive — look for an opening line
            open_match = _OPEN_RE.match(stripped)
            if open_match:
                name = open_match.group(1)
                arg = (open_match.group(2) or "").strip()
                current = Directive(name=name, arg=arg, line_number=line_num)
        else:
            # Inside a directive — look for closing :::
            if _CLOSE_RE.match(stripped):
                directives.append(current)
                current = None
            else:
                current.body.append(line)

    if current is not None:
        raise DirectiveError(
            f"Unclosed directive ':::{current.name}' opened at line {current.line_number}"
        )

    return directives


def resolve_directives(content: str, resolver: callable) -> str:
    """Replace each directive block with the output of resolver(name, arg, body).

    Non-directive content passes through unchanged. Directives inside fenced
    code blocks are left as-is (they are not directives).
    """
    lines = content.split("\n") if content else []
    output: list[str] = []

    fence_char: str | None = None
    fence_len: int = 0

    current_name: str | None = None
    current_arg: str = ""
    current_body: list[str] = []

    for line in lines:
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
            output.append(line)
            continue

        if fence_char is not None:
            # Inside a code fence — pass through verbatim
            output.append(line)
            continue

        # --- directive handling ---
        if current_name is None:
            open_match = _OPEN_RE.match(stripped)
            if open_match:
                current_name = open_match.group(1)
                current_arg = (open_match.group(2) or "").strip()
                current_body = []
            else:
                output.append(line)
        else:
            if _CLOSE_RE.match(stripped):
                resolved = resolver(current_name, current_arg, current_body)
                output.append(resolved)
                current_name = None
                current_arg = ""
                current_body = []
            else:
                current_body.append(line)

    # Unclosed directive in resolve — same error as parse
    if current_name is not None:
        raise DirectiveError(
            f"Unclosed directive ':::{current_name}' during resolution"
        )

    return "\n".join(output)
