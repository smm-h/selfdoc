"""Shared resolution pipeline for docs/ templates.

Provides parse_frontmatter (moved from build.py) and resolve_all_docs,
which walks docs/, parses frontmatter, and resolves directives for each
.md file.  Used by build.py, check.py, and gen.py to avoid duplicating
the walk-parse-resolve logic.
"""

import os

from selfdoc.catalog import ALL_BUILTIN_DIRECTIVES
from selfdoc.directives import resolve_directives
from selfdoc.resolver import make_resolver


def parse_frontmatter(content):
    """Parse YAML-like frontmatter from markdown content (Feature 34).

    If the content starts with '---', extracts key: value pairs until the
    closing '---'. Returns (metadata_dict, remaining_content). If no
    frontmatter is found, returns ({}, original_content).

    Simple parser: splits on ':' (first occurrence), strips whitespace.
    No YAML library needed.
    """
    if not content.startswith("---"):
        return {}, content

    lines = content.split("\n")
    # Find closing ---
    end_idx = None
    for idx in range(1, len(lines)):
        if lines[idx].strip() == "---":
            end_idx = idx
            break

    if end_idx is None:
        return {}, content

    metadata = {}
    for line in lines[1:end_idx]:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        colon_pos = line.find(":")
        if colon_pos == -1:
            continue
        key = line[:colon_pos].strip()
        value = line[colon_pos + 1:].strip()
        # Strip wrapping quotes (single or double) from string values
        if (
            len(value) >= 2
            and value[0] == value[-1]
            and value[0] in ('"', "'")
        ):
            value = value[1:-1]
        # Convert boolean-like strings
        if value.lower() == "true":
            value = True
        elif value.lower() == "false":
            value = False
        else:
            # Try to convert numeric values
            try:
                value = int(value)
            except ValueError:
                try:
                    value = float(value)
                except ValueError:
                    # Comma-separated values become a list
                    if "," in value:
                        value = [item.strip() for item in value.split(",")]
        metadata[key] = value

    remaining = "\n".join(lines[end_idx + 1:]).lstrip("\n")
    return metadata, remaining


def resolve_all_docs(config, docs_dir=None, base_dir="."):
    """Walk docs/, parse frontmatter, resolve directives for each .md file.

    Returns dict mapping rel_path to (frontmatter_dict, resolved_content,
    raw_content, fm_line_count).

    - rel_path: relative to docs_dir (e.g. "index.md", "api/reference.md")
    - frontmatter_dict: parsed frontmatter (empty dict if none)
    - resolved_content: markdown with all directives replaced
    - raw_content: original body content (frontmatter stripped, directives
      NOT resolved)
    - fm_line_count: number of lines consumed by frontmatter (including
      delimiters); 0 when no frontmatter is present
    """
    if docs_dir is None:
        docs_dir = os.path.join(base_dir, config.get("docs", "docs/").rstrip("/"))
    output_dir = os.path.join(base_dir, config.get("output", "docs/_build/").rstrip("/"))

    resolver = make_resolver(config, base_dir)
    valid_names = ALL_BUILTIN_DIRECTIVES | set(config.get("directives", {}).keys())

    abs_output = os.path.abspath(output_dir)
    result = {}

    for root, _dirs, files in os.walk(docs_dir):
        # Skip the output directory to avoid processing previous build artifacts
        if os.path.abspath(root) == abs_output or os.path.abspath(root).startswith(
            abs_output + os.sep
        ):
            continue
        for fname in files:
            if not fname.endswith(".md"):
                continue
            # Skip underscore-prefixed template files (partials, includes)
            if fname.startswith("_"):
                continue

            full_path = os.path.join(root, fname)
            rel_path = os.path.relpath(full_path, docs_dir)

            with open(full_path, "r", encoding="utf-8") as f:
                content = f.read()

            frontmatter_dict, body = parse_frontmatter(content)
            fm_line_count = len(content.split('\n')) - len(body.split('\n'))
            resolved = resolve_directives(body, resolver, valid_names=valid_names)
            result[rel_path] = (frontmatter_dict, resolved, body, fm_line_count)

    return result
