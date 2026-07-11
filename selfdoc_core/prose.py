"""Shared prose unit-pickers for extracting complete linguistic units.

Every summary selfdoc emits (bullet text, frontmatter ``description``,
llms.txt / Atom-feed entries, auto-extracted meta descriptions) is a
*complete linguistic unit*: a whole first sentence or a whole first
paragraph. There are no character caps, no ellipses, and no synthesized
punctuation -- the text is never truncated mid-word and never gains a
period it did not already have.

Two granularities:

- :func:`first_sentence` -- the first sentence of the first paragraph.
- :func:`first_paragraph` -- the whole first paragraph, soft-wrapped
  lines joined into a single line.

:func:`join_wrapped_lines` normalizes source-wrapped prose (Go/JSDoc/KDoc
doc comments wrap at ~75 columns) by joining soft-wrapped lines within a
paragraph while leaving code blocks, list items, and doctest lines verbatim.
"""

# Abbreviations whose trailing period must NOT be treated as a sentence
# boundary. Matched case-insensitively against the whitespace-delimited token
# ending at the candidate period (the token includes the period itself).
_ABBREVIATIONS = frozenset({
    "e.g.", "i.e.", "etc.", "vs.", "cf.", "al.", "esp.", "approx.",
    "dr.", "mr.", "mrs.", "ms.", "prof.", "sr.", "jr.", "st.",
    "vol.", "no.", "nos.", "fig.", "figs.", "eq.", "ref.", "refs.",
    "inc.", "ltd.", "co.", "corp.", "dept.", "univ.",
})


def _find_sentence_end(text: str) -> int | None:
    """Return the index just past the first sentence terminator, or ``None``.

    A terminator is ``.``, ``!``, or ``?`` followed by whitespace or the end
    of the text. Decimals and versions (``3.14``, ``v1.0``) are naturally
    excluded because their internal period is followed by a digit, not
    whitespace. Known abbreviations (``e.g.``, ``etc.``, ``vs.``, ``Dr.`` ...)
    are guarded so their period does not split the sentence.
    """
    n = len(text)
    for i, ch in enumerate(text):
        if ch not in ".!?":
            continue
        # Must be followed by whitespace or end-of-text.
        if i + 1 < n and not text[i + 1].isspace():
            continue
        if ch == ".":
            # Extract the whitespace-delimited token ending at this period.
            k = i - 1
            while k >= 0 and not text[k].isspace():
                k -= 1
            token = text[k + 1 : i + 1]
            if token.lower() in _ABBREVIATIONS:
                continue
        return i + 1
    return None


def first_paragraph(text: str) -> str:
    """Return the first paragraph of *text* as a single joined line.

    Leading blank lines are skipped; the paragraph ends at the next blank
    line. Soft-wrapped physical lines within the paragraph are joined with a
    single space so the result is one complete linguistic unit. No caps, no
    ellipsis, no synthesized punctuation.
    """
    if not text:
        return ""
    para: list[str] = []
    for line in text.split("\n"):
        if line.strip() == "":
            if para:
                break
            continue
        para.append(line.strip())
    return " ".join(para)


def first_sentence(text: str) -> str:
    """Return the first sentence of the first paragraph of *text*.

    The sentence includes its terminating ``.``, ``!``, or ``?``. When the
    paragraph contains no sentence terminator, the whole paragraph is
    returned unchanged (a complete unit is always emitted; punctuation is
    never synthesized).
    """
    para = first_paragraph(text)
    if not para:
        return ""
    end = _find_sentence_end(para)
    if end is None:
        return para
    return para[:end]


def _is_list_item(stripped: str) -> bool:
    """Check whether a stripped line begins a markdown-style list item."""
    if stripped[:2] in ("- ", "* ", "+ "):
        return True
    # Ordered list: "1." / "1)" followed by a space.
    i = 0
    while i < len(stripped) and stripped[i].isdigit():
        i += 1
    return i > 0 and stripped[i : i + 2] in (". ", ") ")


def join_wrapped_lines(text: str) -> str:
    """Join soft-wrapped physical lines within paragraphs of *text*.

    Doc comments (Go, JSDoc, KDoc) wrap at ~75 columns, so a single sentence
    spans multiple physical lines. This joins those lines within a paragraph
    so downstream unit-pickers see whole sentences. Preserved verbatim:

    - blank-line paragraph breaks
    - fenced code blocks (``` / ~~~)
    - indented preformatted blocks (Go doc convention)
    - list items (``-``, ``*``, ``+``, ``1.``)
    - doctest lines (``>>>`` / ``...``)

    Idempotent: joining already-joined prose is a no-op.
    """
    if not text:
        return text
    lines = text.split("\n")
    out: list[str] = []
    para: list[str] = []
    in_fence = False

    def flush() -> None:
        if para:
            out.append(" ".join(para))
            para.clear()

    for line in lines:
        stripped = line.strip()

        if stripped.startswith("```") or stripped.startswith("~~~"):
            flush()
            in_fence = not in_fence
            out.append(line)
            continue
        if in_fence:
            out.append(line)
            continue

        if not stripped:
            flush()
            out.append("")
            continue

        indented = line[:1].isspace()
        is_list = _is_list_item(stripped)
        is_doctest = stripped.startswith(">>>") or stripped.startswith("...")
        if indented or is_list or is_doctest:
            flush()
            out.append(line)
            continue

        para.append(stripped)

    flush()
    return "\n".join(out)
