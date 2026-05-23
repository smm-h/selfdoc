#!/usr/bin/env python3
"""Gen-data script: extract directive catalog as structured JSON.

Reads CORE_DIRECTIVES and FUTURE_DIRECTIVES from selfdoc/catalog.py via AST
parsing (no imports, since bwrap runs with --clearenv and no PYTHONPATH).
Outputs a JSON file with directive names, categories, status, and summary
counts to .selfdoc/data/directive-stats.json.
"""

import ast
import json
import os
import sys


def _find_assignment(tree, name):
    """Find the value node of a module-level assignment by variable name.

    Handles both plain assignments (ast.Assign) and annotated assignments
    (ast.AnnAssign, e.g. ``X: dict[str, T] = {...}``).
    """
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    return node.value
        elif isinstance(node, ast.AnnAssign):
            if (
                isinstance(node.target, ast.Name)
                and node.target.id == name
                and node.value is not None
            ):
                return node.value
    return None


def _extract_core_directives(tree):
    """Extract CORE_DIRECTIVES dict from the AST.

    Returns a list of dicts with name, description, category, required_attrs,
    optional_attrs for each directive.
    """
    directives = []

    value = _find_assignment(tree, "CORE_DIRECTIVES")
    if value is None or not isinstance(value, ast.Dict):
        return directives

    for key, call in zip(value.keys, value.values):
        if not isinstance(key, ast.Constant):
            continue
        name = key.value
        # value is a DirectiveSpec(...) call
        if not isinstance(call, ast.Call):
            continue
        entry = {"name": name}
        for kw in call.keywords:
            if kw.arg == "description" and isinstance(
                kw.value, ast.Constant
            ):
                entry["description"] = kw.value.value
            elif kw.arg == "category" and isinstance(
                kw.value, ast.Constant
            ):
                entry["category"] = kw.value.value
            elif kw.arg == "required_attrs" and isinstance(
                kw.value, ast.List
            ):
                entry["required_attrs"] = [
                    elt.value
                    for elt in kw.value.elts
                    if isinstance(elt, ast.Constant)
                ]
            elif kw.arg == "optional_attrs" and isinstance(
                kw.value, ast.List
            ):
                entry["optional_attrs"] = [
                    elt.value
                    for elt in kw.value.elts
                    if isinstance(elt, ast.Constant)
                ]
        # Defaults for missing fields
        entry.setdefault("required_attrs", [])
        entry.setdefault("optional_attrs", [])
        directives.append(entry)

    return directives


def _extract_future_directives(tree):
    """Extract FUTURE_DIRECTIVES set from the AST.

    Returns a sorted list of directive name strings.
    """
    value = _find_assignment(tree, "FUTURE_DIRECTIVES")
    if value is None or not isinstance(value, ast.Set):
        return []
    return sorted(
        elt.value for elt in value.elts if isinstance(elt, ast.Constant)
    )


def main():
    catalog_path = os.path.join("selfdoc", "catalog.py")
    if not os.path.isfile(catalog_path):
        print(f"Error: {catalog_path} not found", file=sys.stderr)
        sys.exit(1)

    with open(catalog_path, "r", encoding="utf-8") as f:
        source = f.read()

    tree = ast.parse(source, filename=catalog_path)

    core = _extract_core_directives(tree)
    future = _extract_future_directives(tree)

    # Group core directives by category
    by_category = {}
    for d in core:
        cat = d.get("category", "unknown")
        by_category.setdefault(cat, []).append(d["name"])

    # Group future directives by prefix
    future_by_prefix = {}
    for name in future:
        prefix = name.split("-")[0] if "-" in name else "other"
        future_by_prefix.setdefault(prefix, []).append(name)

    output = {
        "core_directives": core,
        "future_directives": future,
        "summary": {
            "core_count": len(core),
            "future_count": len(future),
            "total": len(core) + len(future),
            "core_by_category": {
                k: len(v) for k, v in sorted(by_category.items())
            },
            "future_by_prefix": {
                k: len(v) for k, v in sorted(future_by_prefix.items())
            },
        },
    }

    output_path = os.path.join(".selfdoc", "data", "directive-stats.json")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)
        f.write("\n")

    print(f"Wrote {output_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
