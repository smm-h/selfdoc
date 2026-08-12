#!/usr/bin/env python3
"""One-shot sweep: declare search_engine in every test's selfdoc config literal.

`search_engine` became a required config key, so every hand-written config
in the suite has to declare it.  Finds dict literals that are selfdoc
configs (a base_url plus at least one of locales/versions/docs/source, and
not a project manifest) and inserts the declaration after the base_url key.
"""

import ast
import sys


CONFIG_MARKERS = {"locales", "versions", "docs", "source"}
MANIFEST_MARKERS = {"schema_version", "pages", "last_gen"}


def keys_of(node):
    return {k.value for k in node.keys if isinstance(k, ast.Constant)
            and isinstance(k.value, str)}


def sweep(path):
    src = open(path).read()
    tree = ast.parse(src)
    lines = src.split("\n")
    inserts = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        keys = keys_of(node)
        if "base_url" not in keys or "search_engine" in keys:
            continue
        if not (keys & CONFIG_MARKERS) or (keys & MANIFEST_MARKERS):
            continue
        for key in node.keys:
            if isinstance(key, ast.Constant) and key.value == "base_url":
                inserts.append(key.lineno)
    if not inserts:
        return 0
    for lineno in sorted(set(inserts), reverse=True):
        indent = " " * (len(lines[lineno - 1]) - len(lines[lineno - 1].lstrip()))
        lines.insert(lineno, f'{indent}"search_engine": "pagefind",')
    open(path, "w").write("\n".join(lines))
    return len(set(inserts))


if __name__ == "__main__":
    total = 0
    for path in sys.argv[1:]:
        n = sweep(path)
        if n:
            print(f"{path}: {n}")
            total += n
    print(f"total: {total}")
