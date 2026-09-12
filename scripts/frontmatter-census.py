#!/usr/bin/env python3
"""Census of frontmatter keys across selfdoc projects.

Walks every project given on the command line (default: every directory
under ~/Projects, two levels deep, that holds a selfdoc.json, plus the two
under ~/Projects/.archive), reads each page's leading ``---`` block the way
selfdoc's own parser does (a key is the token before the first colon), and
prints:

- one row per distinct key: occurrences, how many projects use it, how many
  of those occurrences sit in generated pages versus authored ones, and how
  many sit in posts;
- one row per value shape (quoted, boolean, integer, bracket list, bare
  value containing a colon, ...) so a TOML conversion knows what it faces;
- with --per-project, a key-by-project matrix.

Read-only. No dependencies beyond the standard library.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

HOME = Path.home()
PROJECTS = HOME / "Projects"


# Audit fixtures and scratch copies carry their own selfdoc.json but are not
# production docs; a root whose path contains one of these tokens is skipped.
EXCLUDED_TOKENS = ("audit", "scratch", "fixtures")


def discover_projects() -> list[Path]:
    roots: list[Path] = []
    for cfg in sorted(PROJECTS.glob("*/selfdoc.json")):
        roots.append(cfg.parent)
    for cfg in sorted(PROJECTS.glob(".archive/*/selfdoc.json")):
        roots.append(cfg.parent)
    for cfg in sorted(PROJECTS.glob("*/*/selfdoc.json")):
        if cfg.parent not in roots and ".archive" not in cfg.parts:
            roots.append(cfg.parent)
    return [r for r in roots if not any(t in str(r.relative_to(PROJECTS)).lower() for t in EXCLUDED_TOKENS)]


def docs_dir(root: Path) -> Path:
    try:
        cfg = json.loads((root / "selfdoc.json").read_text())
    except (OSError, ValueError):
        return root / "docs"
    return root / str(cfg.get("docs", "docs/")).rstrip("/")


def leading_block(text: str) -> list[str] | None:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    block: list[str] = []
    for line in lines[1:]:
        if line.strip() == "---":
            return block
        block.append(line)
    return None


LIST_RE = re.compile(r"^\[.*\]$")
INT_RE = re.compile(r"^-?\d+$")
FLOAT_RE = re.compile(r"^-?\d+\.\d+$")


def value_shape(value: str) -> str:
    v = value.strip()
    if v == "":
        return "empty"
    if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
        inner = v[1:-1]
        return "quoted-with-inner-quote" if '"' in inner else "quoted"
    if v in ("true", "false"):
        return "boolean"
    if INT_RE.match(v):
        return "integer"
    if FLOAT_RE.match(v):
        return "float"
    if LIST_RE.match(v):
        return "bracket-list"
    if ":" in v:
        return "bare-with-colon"
    if '"' in v:
        return "bare-with-quote"
    return "bare"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("projects", nargs="*", type=Path, help="project roots (default: discover)")
    ap.add_argument("--per-project", action="store_true", help="also print the key-by-project matrix")
    args = ap.parse_args()

    roots = [p.resolve() for p in args.projects] or discover_projects()

    key_total: Counter[str] = Counter()
    key_projects: dict[str, set[str]] = defaultdict(set)
    key_generated: Counter[str] = Counter()
    key_authored: Counter[str] = Counter()
    key_posts: Counter[str] = Counter()
    shape_total: Counter[str] = Counter()
    shape_examples: dict[str, list[str]] = defaultdict(list)
    matrix: dict[str, Counter[str]] = defaultdict(Counter)
    pages = posts = no_block = 0

    for root in roots:
        name = str(root.relative_to(PROJECTS)) if root.is_relative_to(PROJECTS) else root.name
        sources: list[tuple[Path, bool]] = []
        d = docs_dir(root)
        if d.is_dir():
            sources += [(p, False) for p in sorted(d.rglob("*.md")) if "_build" not in p.parts]
        posts_dir = root / ".selfdoc" / "posts"
        if posts_dir.is_dir():
            sources += [(p, True) for p in sorted(posts_dir.glob("*.md"))]
        for path, is_post in sources:
            try:
                block = leading_block(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError):
                continue
            if block is None:
                no_block += 1
                continue
            if is_post:
                posts += 1
            else:
                pages += 1
            entries = [(ln.split(":", 1)[0].strip(), ln.split(":", 1)[1]) for ln in block if ":" in ln]
            keys = {k for k, _ in entries}
            generated = any(k == "generated" and v.strip() == "true" for k, v in entries)
            for key, value in entries:
                key_total[key] += 1
                key_projects[key].add(name)
                matrix[key][name] += 1
                if is_post:
                    key_posts[key] += 1
                elif generated:
                    key_generated[key] += 1
                else:
                    key_authored[key] += 1
                shape = value_shape(value)
                shape_total[shape] += 1
                if shape not in ("bare", "quoted", "boolean", "integer") and len(shape_examples[shape]) < 5:
                    shape_examples[shape].append(f"{path.relative_to(PROJECTS) if path.is_relative_to(PROJECTS) else path}: {key}:{value.strip()[:70]}")
            del keys

    print(f"projects: {len(roots)}   pages with a block: {pages}   posts with a block: {posts}   files without a block: {no_block}\n")
    print(f"{'key':<16}{'occurrences':>12}{'projects':>10}{'generated':>11}{'authored':>10}{'posts':>7}")
    for key, n in key_total.most_common():
        print(f"{key:<16}{n:>12}{len(key_projects[key]):>10}{key_generated[key]:>11}{key_authored[key]:>10}{key_posts[key]:>7}")
    single = [k for k in key_total if len(key_projects[k]) == 1]
    if single:
        print("\nkeys used by exactly one project: " + ", ".join(f"{k} ({next(iter(key_projects[k]))})" for k in sorted(single)))

    print(f"\n{'value shape':<26}{'count':>8}")
    for shape, n in shape_total.most_common():
        print(f"{shape:<26}{n:>8}")
    for shape, examples in shape_examples.items():
        print(f"\n  {shape}:")
        for e in examples:
            print(f"    {e}")

    if args.per_project:
        names = sorted({p for s in key_projects.values() for p in s})
        print("\nkey-by-project matrix (occurrences):")
        print(f"{'key':<16}" + "".join(f"{n[:9]:>10}" for n in names))
        for key, _ in key_total.most_common():
            print(f"{key:<16}" + "".join(f"{matrix[key][n] or '':>10}" for n in names))
    return 0


if __name__ == "__main__":
    sys.exit(main())
