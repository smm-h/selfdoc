#!/usr/bin/env python3
"""Gen-data script: extract directive catalog as structured JSON.

Reads the core directives from ``selfdoc_core/directives.toml`` (the declarative
catalogue document, parsed with the stdlib ``tomllib``) and FUTURE_DIRECTIVES
from ``selfdoc_core/catalog.py`` via AST parsing. No selfdoc imports are needed
(bwrap runs with --clearenv and no PYTHONPATH). Outputs a JSON file with
directive names, categories, status, and summary counts to
.selfdoc/data/directive-stats.json.
"""

import ast
import json
import os
import sys
import tomllib


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


def _extract_core_directives(document):
    """Extract the core directives from the parsed directives.toml document.

    Returns a list of dicts with name, description, category, required_attrs,
    optional_attrs for each directive, in catalogue (document) order.
    """
    directives = []
    for entry in document.get("directives", []):
        directives.append(
            {
                "name": entry["name"],
                "description": entry.get("description", ""),
                "category": entry.get("category", "unknown"),
                "required_attrs": list(entry.get("required_attrs", [])),
                "optional_attrs": list(entry.get("optional_attrs", [])),
            }
        )
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
    document_path = os.path.join("selfdoc_core", "directives.toml")
    catalog_path = os.path.join("selfdoc_core", "catalog.py")
    for required in (document_path, catalog_path):
        if not os.path.isfile(required):
            print(f"Error: {required} not found", file=sys.stderr)
            sys.exit(1)

    with open(document_path, "rb") as f:
        document = tomllib.load(f)

    with open(catalog_path, "r", encoding="utf-8") as f:
        tree = ast.parse(f.read(), filename=catalog_path)

    core = _extract_core_directives(document)
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
