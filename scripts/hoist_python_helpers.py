#!/usr/bin/env python3
"""Rewrite call sites of a package-private Python-semantics helper onto internal/util.

The Go rewrite left one private copy of each Python-semantics helper (repr, str,
strip, splitlines, the \\s/\\S/\\w classes) in every package that needed one,
because their authors could not edit internal/util. This script performs the
call-site half of hoisting them: it rewrites `helper(` into `util.Helper(` in
the named Go files, asserts the expected occurrence count, and adds the util
import when the file does not already carry it.

Deleting the private definition itself is a separate, reviewed edit -- a
definition usually sits in a comment block that says why it exists, and that
prose belongs in internal/util or nowhere.

Usage:
    hoist_python_helpers.py --dry-run <old>=<new>:<count> [...] -- <file> [...]
    hoist_python_helpers.py --apply   <old>=<new>:<count> [...] -- <file> [...]

<count> is the total number of occurrences expected across every named file; a
mismatch aborts before anything is written, so a mistyped helper name cannot
silently rewrite nothing.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

UTIL_IMPORT = '\t"github.com/smm-h/selfdoc/internal/util"\n'


def parse_rule(raw: str) -> tuple[str, str, int]:
    mapping, _, count = raw.rpartition(":")
    old, _, new = mapping.partition("=")
    if not (old and new and count.isdigit()):
        raise SystemExit(f"bad rule {raw!r}; want old=new:count")
    return old, new, int(count)


def ensure_util_import(text: str) -> str:
    if UTIL_IMPORT in text:
        return text
    match = re.search(r"^import \(\n(.*?)^\)\n", text, re.S | re.M)
    if not match:
        raise SystemExit("no grouped import block to extend")
    block = match.group(1)
    lines = [line for line in block.split("\n") if line.strip()]
    third_party = [line for line in lines if '"github.com/' in line]
    if third_party:
        insert_at = block.index(third_party[0])
        new_block = block[:insert_at] + UTIL_IMPORT + block[insert_at:]
    else:
        new_block = block.rstrip("\n") + "\n\n" + UTIL_IMPORT
    return text[: match.start(1)] + new_block + text[match.end(1) :]


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    parser.add_argument("rules", nargs="+")
    argv = sys.argv[1:]
    if "--" not in argv:
        raise SystemExit("the rules and the files are separated by '--'")
    split = argv.index("--")
    args = parser.parse_args(argv[:split])
    files = [Path(f) for f in argv[split + 1 :]]
    if not files:
        raise SystemExit("no files named")

    rules = [parse_rule(raw) for raw in args.rules]
    seen = {old: 0 for old, _, _ in rules}
    plan: dict[Path, str] = {}

    for path in files:
        text = original = path.read_text()
        for old, new, _ in rules:
            pattern = re.compile(r"\b" + re.escape(old) + r"\(")
            hits = len(pattern.findall(text))
            if not hits:
                continue
            seen[old] += hits
            text = pattern.sub(new + "(", text)
            print(f"{path}: {old} -> {new} x{hits}")
        if text != original:
            plan[path] = ensure_util_import(text)

    failed = False
    for old, _, want in rules:
        if seen[old] != want:
            print(f"COUNT MISMATCH {old}: found {seen[old]}, expected {want}")
            failed = True
    if failed:
        return 1
    if args.dry_run:
        print(f"dry run: {len(plan)} file(s) would change")
        return 0
    for path, text in plan.items():
        path.write_text(text)
    print(f"wrote {len(plan)} file(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
