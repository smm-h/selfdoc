"""Standalone Markdown block tokenizer.

Splits Markdown source into a flat list of typed block tokens. Each token
carries 1-based ``start`` and ``end`` line numbers so the caller knows
exactly which source lines produced it.

No imports from selfdoc -- this module is designed for reuse outside the
project.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


# ---------------------------------------------------------------------------
# Token types
# ---------------------------------------------------------------------------

@dataclass(eq=True, slots=True)
class CodeBlock:
    lang: str
    lines: list[str]
    annotations: dict[str, str]
    start: int
    end: int
    run: bool = False
    line_numbers: bool = False
    line_start: int = 1
    # Opt-in semantic validation: the ``validate`` info-string token declares
    # that this block is a self-contained program, so ``selfdoc check`` may
    # hand it to the validator command configured for ``lang``.
    validate: bool = False


@dataclass(eq=True, slots=True)
class Heading:
    level: int
    text: str
    start: int
    end: int


@dataclass(eq=True, slots=True)
class Table:
    rows: list[str]
    start: int
    end: int


@dataclass(eq=True, slots=True)
class UnorderedList:
    items: list[str]
    start: int
    end: int


@dataclass(eq=True, slots=True)
class OrderedList:
    items: list[str]
    start: int
    end: int


@dataclass(eq=True, slots=True)
class Blockquote:
    lines: list[str]
    admonition_type: str | None
    start: int
    end: int


@dataclass(eq=True, slots=True)
class DefinitionList:
    entries: list[tuple[str, list[str]]]
    start: int
    end: int


@dataclass(eq=True, slots=True)
class ThematicBreak:
    start: int
    end: int


@dataclass(eq=True, slots=True)
class BlankLine:
    start: int
    end: int


@dataclass(eq=True, slots=True)
class Directive:
    name: str
    arg: str
    body: list[str]
    start: int
    end: int


@dataclass(eq=True, slots=True)
class Paragraph:
    lines: list[str]
    start: int
    end: int


Block = (
    CodeBlock
    | Heading
    | Table
    | UnorderedList
    | OrderedList
    | Blockquote
    | DefinitionList
    | ThematicBreak
    | BlankLine
    | Directive
    | Paragraph
)


# ---------------------------------------------------------------------------
# Regex helpers (compiled once)
# ---------------------------------------------------------------------------

_RE_THEMATIC_BREAK = re.compile(r"^(---+|\*\*\*+|___+)$")
_RE_HEADING = re.compile(r"^(#{1,6})\s+(.+)$")
_RE_TABLE_ROW = re.compile(r"^\|.+\|$")
_RE_UNORDERED = re.compile(r"^[-*]\s+")
_RE_ORDERED = re.compile(r"^\d+\.\s+")
_RE_ANNOTATION = re.compile(r"^\[(\d+)\]:\s*(.+)$")
_RE_ADMONITION = re.compile(r"^\[!(\w+)\]")
_RE_DIRECTIVE_OPEN = re.compile(r"^:::(\w+)(?:\s+(.+))?$")
_RE_DIRECTIVE_CLOSE = re.compile(r"^:::$")


# ---------------------------------------------------------------------------
# Tokenizer
# ---------------------------------------------------------------------------

def tokenize(content: str) -> list[Block]:
    """Tokenize Markdown *content* into a list of block tokens.

    Line numbers on every token are 1-based (first line of the file is 1).
    The tokens cover every line exactly once -- no gaps and no overlaps.
    """
    lines = content.split("\n")
    n = len(lines)
    tokens: list[Block] = []
    i = 0

    while i < n:
        line = lines[i]

        # 1. Fenced code block
        if line.startswith("```"):
            start = i
            info_string = line[3:].strip()
            # Parse optional flags from the info string (e.g. "python run")
            info_parts = info_string.split()
            lang = info_parts[0] if info_parts else ""
            run_flag = "run" in info_parts[1:]
            validate_flag = "validate" in info_parts[1:]
            # Parse line numbers annotation: "lines" or "lines=N"
            ln_flag = False
            ln_start = 1
            for part in info_parts[1:]:
                if part == "lines":
                    ln_flag = True
                elif part.startswith("lines="):
                    ln_flag = True
                    try:
                        ln_start = int(part[6:])
                    except ValueError:
                        pass
            code_lines: list[str] = []
            i += 1
            while i < n and not lines[i].startswith("```"):
                code_lines.append(lines[i])
                i += 1
            if i < n:
                i += 1  # skip closing ```

            # Greedily consume annotation lines after the fence
            annotations: dict[str, str] = {}
            while i < n:
                m = _RE_ANNOTATION.match(lines[i])
                if not m:
                    break
                annotations[m.group(1)] = m.group(2)
                i += 1

            tokens.append(CodeBlock(
                lang=lang,
                lines=code_lines,
                annotations=annotations,
                start=start + 1,
                end=i,
                run=run_flag,
                line_numbers=ln_flag,
                line_start=ln_start,
                validate=validate_flag,
            ))
            continue

        # 2. Thematic break (before heading -- `---` must not become heading)
        if _RE_THEMATIC_BREAK.match(line):
            tokens.append(ThematicBreak(start=i + 1, end=i + 1))
            i += 1
            continue

        # 3. Heading
        m_heading = _RE_HEADING.match(line)
        if m_heading:
            tokens.append(Heading(
                level=len(m_heading.group(1)),
                text=m_heading.group(2),
                start=i + 1,
                end=i + 1,
            ))
            i += 1
            continue

        # 4. Directive (:::name arg ... :::)
        m_directive = _RE_DIRECTIVE_OPEN.match(line)
        if m_directive:
            start = i
            d_name = m_directive.group(1)
            d_arg = m_directive.group(2) or ""
            d_body: list[str] = []
            i += 1
            while i < n and not _RE_DIRECTIVE_CLOSE.match(lines[i]):
                d_body.append(lines[i])
                i += 1
            if i < n:
                i += 1  # skip closing :::
            tokens.append(Directive(
                name=d_name,
                arg=d_arg,
                body=d_body,
                start=start + 1,
                end=i,
            ))
            continue

        # 5. Table
        if _RE_TABLE_ROW.match(line.strip()):
            start = i
            rows: list[str] = []
            while i < n and _RE_TABLE_ROW.match(lines[i].strip()):
                rows.append(lines[i].strip())
                i += 1
            tokens.append(Table(rows=rows, start=start + 1, end=i))
            continue

        # 6. Unordered list
        if _RE_UNORDERED.match(line):
            start = i
            items: list[str] = []
            while i < n and _RE_UNORDERED.match(lines[i]):
                items.append(_RE_UNORDERED.sub("", lines[i], count=1))
                i += 1
            tokens.append(UnorderedList(items=items, start=start + 1, end=i))
            continue

        # 7. Ordered list
        if _RE_ORDERED.match(line):
            start = i
            items_ol: list[str] = []
            while i < n and _RE_ORDERED.match(lines[i]):
                items_ol.append(_RE_ORDERED.sub("", lines[i], count=1))
                i += 1
            tokens.append(OrderedList(items=items_ol, start=start + 1, end=i))
            continue

        # 8. Blockquote
        if line.startswith(">"):
            start = i
            bq_lines: list[str] = []
            while i < n and lines[i].startswith(">"):
                stripped = re.sub(r"^>\s?", "", lines[i])
                bq_lines.append(stripped)
                i += 1
            admonition: str | None = None
            if bq_lines:
                m_adm = _RE_ADMONITION.match(bq_lines[0])
                if m_adm:
                    admonition = m_adm.group(1)
            tokens.append(Blockquote(
                lines=bq_lines,
                admonition_type=admonition,
                start=start + 1,
                end=i,
            ))
            continue

        # 9. Blank line
        if not line.strip():
            tokens.append(BlankLine(start=i + 1, end=i + 1))
            i += 1
            continue

        # 10. Definition list
        if line.strip() and i + 1 < n and lines[i + 1].startswith(": "):
            start = i
            entries: list[tuple[str, list[str]]] = []
            while i < n:
                term_line = lines[i].strip()
                if not term_line:
                    # Blank line -- might separate groups; peek ahead
                    # Skip blanks and check if the next non-blank starts a
                    # new term + definition pair
                    j = i
                    while j < n and not lines[j].strip():
                        j += 1
                    if (j < n
                            and j + 1 < n
                            and lines[j].strip()
                            and lines[j + 1].startswith(": ")):
                        # Skip the blanks and continue with next pair
                        i = j
                        continue
                    break
                # Must have a definition on the next line
                if i + 1 >= n or not lines[i + 1].startswith(": "):
                    break
                term = term_line
                i += 1
                defs: list[str] = []
                while i < n and lines[i].startswith(": "):
                    defs.append(lines[i][2:])
                    i += 1
                entries.append((term, defs))
            # end includes any trailing blanks between groups that we
            # consumed (they are part of this token)
            tokens.append(DefinitionList(
                entries=entries,
                start=start + 1,
                end=i,
            ))
            continue

        # 11. Paragraph (fallback)
        start = i
        para_lines: list[str] = []
        while i < n:
            current = lines[i]
            if not current.strip():
                break
            if current.startswith("```"):
                break
            if _RE_HEADING.match(current):
                break
            if _RE_THEMATIC_BREAK.match(current):
                break
            if _RE_UNORDERED.match(current):
                break
            if _RE_ORDERED.match(current):
                break
            if _RE_TABLE_ROW.match(current.strip()):
                break
            if current.startswith(">"):
                break
            if _RE_DIRECTIVE_OPEN.match(current):
                break
            # Definition list guard: don't absorb a line whose next line
            # starts a definition
            if i + 1 < n and lines[i + 1].startswith(": "):
                break
            para_lines.append(current)
            i += 1
        tokens.append(Paragraph(lines=para_lines, start=start + 1, end=i))
        continue

    return tokens
