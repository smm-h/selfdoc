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
from collections.abc import Iterable
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

# Attribute key="value" pair extractor. Keys may contain hyphens (e.g.
# ``schema-dir``), matching the directive-name character class.
_ATTR_KV_RE = re.compile(r'([\w-]+)="([^"]*)"')

# Directive name: starts with a letter, followed by word chars or hyphens
_DIRECTIVE_NAME = r'[a-zA-Z][\w-]*'

# Inline one-liner: :-: name [attrs] (non-anchored, for pass 2)
_INLINE_RE = re.compile(rf':-:\s+({_DIRECTIVE_NAME})((?:\s+[\w-]+="[^"]*")*)')


class DirectiveError(Exception):
    """Raised when a directive is malformed (e.g. unclosed at EOF)."""


@dataclass
class Directive:
    """A parsed directive block."""

    name: str
    attrs: dict[str, str] = field(default_factory=dict)
    body: list[str] = field(default_factory=list)
    line_number: int = 0
    inline: bool = False
    column: int | None = None


def _parse_attrs(text: str) -> dict[str, str]:
    """Extract all key="value" pairs from a string."""
    return dict(_ATTR_KV_RE.findall(text))


def _validate_directive_name(
    name: str, valid_names: set[str] | None, line_number: int
) -> None:
    """Raise DirectiveError if *name* is not in *valid_names* (when provided)."""
    if valid_names is not None and name not in valid_names:
        raise DirectiveError(
            f"Unknown directive '{name}' at line {line_number}"
        )


_DIRECTIVE_NAME_RE = re.compile(rf"^{_DIRECTIVE_NAME}$")


def validate_directive_names(names: Iterable[str]) -> None:
    """Validate that each *name* matches the directive name format.

    Raises DirectiveError for names that don't match ``[a-zA-Z][\\w-]*``.
    """
    for name in names:
        if not _DIRECTIVE_NAME_RE.match(name):
            raise DirectiveError(
                f"Invalid directive name '{name}': "
                r"must match [a-zA-Z][\w-]*"
            )


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
                _validate_directive_name(name, valid_names, line_num)
                attrs = _parse_attrs(m.group(2))
                yield ("directive", name, attrs, [], line_num)
                continue

            # Check block open: :<: name [attrs]
            m = _BLOCK_OPEN_RE.match(stripped)
            if m:
                block_name = m.group(1)
                _validate_directive_name(block_name, valid_names, line_num)
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
    Includes both standalone (pass 1) and inline (pass 2) directives.
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

    # Pass 2: scan non-directive, non-fenced lines for inline directives.
    # Re-scan from original content with fence tracking to get line numbers.
    if content:
        lines = content.split("\n")
        fence_char: str | None = None
        fence_len: int = 0
        for line_idx, line in enumerate(lines):
            stripped = line.strip()
            fence_match = _FENCE_RE.match(stripped)
            if fence_match:
                marker = fence_match.group(1)
                if fence_char is None:
                    fence_char = marker[0]
                    fence_len = len(marker)
                elif marker[0] == fence_char and len(marker) >= fence_len:
                    fence_char = None
                    fence_len = 0
                continue
            if fence_char is not None:
                continue
            # Skip lines that are standalone directives (handled by pass 1)
            if _ONELINER_RE.match(stripped):
                continue
            # Find inline directives
            directives.extend(find_inline_directives(line, line_idx + 1, valid_names))

    return directives


# Backtick code span: matches `...`, ``...``, ```...```, etc. per CommonMark rules.
# Uses a backreference so the closing delimiter has the same number of backticks.
_BACKTICK_SPAN_RE = re.compile(r"(`+)(?!`)(.+?)(?<!`)\1(?!`)")


def _mask_backtick_spans(line: str) -> tuple[str, list[str]]:
    """Replace backtick code spans with null-byte placeholders.

    Returns (masked_line, placeholders) where placeholders[i] is the original
    text for placeholder i. Handles any backtick-span length (`, ``, ```, etc.)
    per CommonMark rules.
    """
    spans = list(_BACKTICK_SPAN_RE.finditer(line))
    if not spans:
        return line, []

    placeholders: list[str] = [""] * len(spans)
    masked = line
    for idx, match in enumerate(reversed(spans)):
        pos = len(spans) - 1 - idx
        placeholder = f"\x00BTCK{pos}\x00"
        placeholders[pos] = match.group(0)
        masked = masked[:match.start()] + placeholder + masked[match.end():]
    return masked, placeholders


def _unmask_backtick_spans(line: str, placeholders: list[str]) -> str:
    """Restore backtick span placeholders to their original text."""
    for i, original in enumerate(placeholders):
        line = line.replace(f"\x00BTCK{i}\x00", original)
    return line


def find_inline_directives(
    line: str, line_num: int, valid_names: set[str] | None = None
) -> list[Directive]:
    """Find inline :-: directives in a line, skipping backtick code spans.

    Returns Directive objects with inline=True and column set to the match
    position in the original (unmasked) line.
    """
    masked, placeholders = _mask_backtick_spans(line)
    directives: list[Directive] = []
    for match in _INLINE_RE.finditer(masked):
        name = match.group(1)
        _validate_directive_name(name, valid_names, line_num)
        attrs = _parse_attrs(match.group(2))
        # Column in masked line equals column in original line when the match
        # falls outside placeholders (which it does, since backtick spans are
        # masked). Compute original column by counting placeholder length diffs
        # before this position.
        col = match.start()
        offset = 0
        for i, ph_original in enumerate(placeholders):
            ph_text = f"\x00BTCK{i}\x00"
            ph_pos = masked.index(ph_text)
            if ph_pos < match.start():
                offset += len(ph_original) - len(ph_text)
            else:
                break
        directives.append(
            Directive(
                name=name,
                attrs=attrs,
                body=[],
                line_number=line_num,
                inline=True,
                column=col + offset,
            )
        )
    return directives


# Any of the six markers standing at the start of a line, and the
# self-closing marker used inline.  Detection only: no name validation, no
# attribute parsing, no well-formedness requirement -- the question these
# answer is "does this markdown carry directive syntax at all?", which must
# be answerable for a document that was never meant to be resolved.
_MARKER_LINE_RE = re.compile(r"^(:-:|:<:|:@:|:=:|:::|:>:)(\s|$)")
_INLINE_MARKER_RE = re.compile(rf':-:\s+{_DIRECTIVE_NAME}')


def find_directive_markers(content: str) -> list[tuple[int, str]]:
    """Find every directive marker in *content*, by line.

    Returns ``(line_number, marker)`` pairs in document order, with 1-based
    line numbers relative to *content*.  Fenced code blocks and backtick
    code spans are skipped, so a post that writes ``:-: ref`` as an example
    of the syntax carries no marker.

    This is the detection counterpart of :func:`parse_directives`: it
    reports syntax without resolving, validating names, or requiring a
    block to be closed.  A document that declares it holds no directives is
    checked with this, because parsing it would fail on the very markers
    the check exists to report.
    """
    markers: list[tuple[int, str]] = []
    fence_char: str | None = None
    fence_len = 0

    for line_idx, line in enumerate(content.split("\n") if content else []):
        stripped = line.strip()
        fence_match = _FENCE_RE.match(stripped)
        if fence_match:
            fence = fence_match.group(1)
            if fence_char is None:
                fence_char = fence[0]
                fence_len = len(fence)
            elif fence[0] == fence_char and len(fence) >= fence_len:
                fence_char = None
                fence_len = 0
            continue
        if fence_char is not None:
            continue

        masked, _placeholders = _mask_backtick_spans(line)
        line_num = line_idx + 1

        match = _MARKER_LINE_RE.match(masked.strip())
        if match:
            markers.append((line_num, match.group(1)))
            continue

        markers.extend(
            (line_num, ":-:") for _ in _INLINE_MARKER_RE.finditer(masked)
        )

    return markers


def _resolve_line_inline(line: str, resolver: callable) -> str:
    """Resolve inline :-: directives in a single line, skipping backtick spans."""
    masked, placeholders = _mask_backtick_spans(line)

    def _resolve_match(match: re.Match) -> str:
        name = match.group(1)
        attrs = _parse_attrs(match.group(2))
        result = resolver(name, attrs, [])
        if "\n" in result:
            raise RuntimeError(
                f"Inline directive '{name}' returned multi-line output; "
                "only single-line output is allowed for inline directives."
            )
        return result

    resolved = _INLINE_RE.sub(_resolve_match, masked)
    return _unmask_backtick_spans(resolved, placeholders)


def _resolve_inline_pass(
    output: list[str], resolver: callable
) -> list[str]:
    """Pass 2: scan output lines for inline :-: directives and resolve them.

    Skips lines inside fenced code blocks (``` or ~~~), tracked with the same
    _FENCE_RE pattern used by _walk_blocks. Also skips directives inside
    backtick code spans on each line.
    """
    result: list[str] = []
    fence_char: str | None = None
    fence_len: int = 0

    for n, line in enumerate(output, 1):
        stripped = line.strip()
        fence_match = _FENCE_RE.match(stripped)

        if fence_match:
            marker = fence_match.group(1)
            if fence_char is None:
                # Opening a fence
                fence_char = marker[0]
                fence_len = len(marker)
            elif marker[0] == fence_char and len(marker) >= fence_len:
                # Closing the fence
                fence_char = None
                fence_len = 0
            result.append(line)
            continue

        if fence_char is not None:
            # Inside a fenced code block — pass through
            result.append(line)
            continue

        # Detect malformed directive names before resolution: check each
        # :-: token and flag names that start with a letter but don't match
        # the directive name pattern (e.g. "my.directive", "a+b").
        # A token like "name)" is fine (valid name + trailing punctuation),
        # but "my.directive" is malformed (word chars after invalid char).
        # Mask backtick spans so directives inside code spans are skipped.
        if ":-: " in line:
            _check_line, _ = _mask_backtick_spans(line)
            for _malformed_m in re.finditer(r":-:\s+(\S+)", _check_line):
                token = _malformed_m.group(1)
                if not token[0:1].isalpha():
                    continue
                if _DIRECTIVE_NAME_RE.match(token):
                    continue
                # Token starts with a letter but doesn't fully match.
                # Extract the valid prefix and check if the remainder
                # contains word chars (malformed) or is just punctuation.
                prefix_m = re.match(_DIRECTIVE_NAME, token)
                remainder = token[prefix_m.end():]  # type: ignore[union-attr]
                if re.search(r"\w", remainder):
                    raise DirectiveError(
                        f"Malformed directive name '{token}' at line {n}: "
                        r"names must match [a-zA-Z][\w-]*"
                    )

        if _INLINE_RE.search(line):
            line = _resolve_line_inline(line, resolver)
        result.append(line)
    return result


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
            output.extend(resolver(name, attrs, body).split("\n"))
        elif event[0] == "unclosed":
            _, name, _line_num = event
            raise DirectiveError(
                f"Unclosed directive '{name}' during resolution"
            )

    # Pass 2: resolve inline :-: directives in output lines
    output = _resolve_inline_pass(output, resolver)

    return "\n".join(output)
