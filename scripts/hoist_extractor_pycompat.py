#!/usr/bin/env python3
"""Point each language extractor's Python-semantics helpers at internal/util.

Every extractor carried its own isPySpace predicate and its own str.strip
wrappers, plus -- in the four whose patterns compose whitespace into a larger
character class -- its own copy of the \\s and \\w class members. This rewrites
all of them onto internal/util, which is the one authority for what Python's
whitespace and word classes denote.

The helper NAMES stay: `strip`, `pyStrip`, `rstrip` and friends are what a
hundred-odd call sites in the scanners read, and the name is this package's
short spelling of a util function rather than a second implementation of it.

Usage: hoist_extractor_pycompat.py --dry-run | --apply
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

UTIL = '"github.com/smm-h/selfdoc/internal/util"'

# The rewrites, in the order they are applied to each file.
BODIES = [
    ("strings.TrimFunc(s, isPySpace)", "util.PythonStrip(s)"),
    ("strings.TrimLeftFunc(s, isPySpace)", "util.PythonLStrip(s)"),
    ("strings.TrimRightFunc(s, isPySpace)", "util.PythonRStrip(s)"),
    ("strings.FieldsFunc(s, isPySpace)", "util.PythonFields(s)"),
    ("strings.TrimLeftFunc(rest[i:], isPySpace)", "util.PythonLStrip(rest[i:])"),
    ("strings.TrimLeftFunc(s, isPySpace)", "util.PythonLStrip(s)"),
    ("strings.TrimLeftFunc(text, isPySpace)", "util.PythonLStrip(text)"),
    ("strings.TrimRightFunc(line, isPySpace)", "util.PythonRStrip(line)"),
    ("strings.TrimRightFunc(sig, isPySpace)", "util.PythonRStrip(sig)"),
    ("strings.FieldsFunc(namePart, isPySpace)", "util.PythonFields(namePart)"),
    ("isPySpace(rune(b))", "util.IsPythonSpace(rune(b))"),
    ("isPySpace(r)", "util.IsPythonSpace(r)"),
]

# The class-member copies, replaced by the util constants they duplicate.
CLASS_MEMBERS = (
    """	wordChars  = `\\p{L}\\p{N}_`
	spaceChars = `\\t\\n\\v\\f\\r \\x{001c}-\\x{001f}\\x{0085}\\x{00a0}\\x{1680}` +
		`\\x{2000}-\\x{200a}\\x{2028}\\x{2029}\\x{202f}\\x{205f}\\x{3000}`
""",
    """	wordChars  = util.PythonWordChars
	spaceChars = util.PythonSpaceChars
""",
)

ISPYSPACE = re.compile(
    r"// isPySpace reports whether r is whitespace[^\n]*\n(?://[^\n]*\n)*"
    r"func isPySpace\(r rune\) bool \{\n(?:\t[^\n]*\n)*\}\n\n"
)

FILES = [
    "internal/extractors/dart/details.go",
    "internal/extractors/dart/parse.go",
    "internal/extractors/golang/strings.go",
    "internal/extractors/kotlin/parse.go",
    "internal/extractors/python/strings.go",
    "internal/extractors/sql/lexical.go",
    "internal/extractors/svelte/pycompat.go",
    "internal/extractors/swift/details.go",
    "internal/extractors/swift/parse.go",
    "internal/extractors/typescript/pycompat.go",
    "internal/extractors/zig/pycompat.go",
]


def rewrite(path: Path) -> str:
    text = original = path.read_text()
    changes: list[str] = []

    if CLASS_MEMBERS[0] in text:
        text = text.replace(*CLASS_MEMBERS)
        changes.append("class members -> util")

    text, dropped = ISPYSPACE.subn("", text)
    if dropped:
        changes.append(f"isPySpace definition dropped ({dropped})")

    for old, new in BODIES:
        hits = text.count(old)
        if hits:
            text = text.replace(old, new)
            changes.append(f"{old} -> {new} x{hits}")

    if "isPySpace" in text:
        raise SystemExit(f"{path}: an isPySpace reference is left behind")

    if text != original and UTIL not in text:
        match = re.search(r"^import \(\n(.*?)^\)\n", text, re.S | re.M)
        if not match:
            raise SystemExit(f"{path}: no grouped import block")
        block = match.group(1)
        if "github.com/" in block:
            insert = block.index('\t"github.com/')
            block = block[:insert] + "\t" + UTIL + "\n" + block[insert:]
        else:
            block = block.rstrip("\n") + "\n\n\t" + UTIL + "\n"
        text = text[: match.start(1)] + block + text[match.end(1) :]
        changes.append("util import added")

    print(f"{path}: " + ("; ".join(changes) if changes else "no change"))
    return text


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in {"--dry-run", "--apply"}:
        raise SystemExit(__doc__)
    plan = {Path(name): rewrite(Path(name)) for name in FILES}
    if sys.argv[1] == "--dry-run":
        print("dry run: nothing written")
        return 0
    for path, text in plan.items():
        path.write_text(text)
    print(f"wrote {len(plan)} file(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
