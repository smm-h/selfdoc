"""Shared resolution pipeline for docs/ templates.

Provides resolve_all_docs, which walks docs/, parses frontmatter, and
resolves directives for each .md file.  Used by build.py, check.py, and
gen.py to avoid duplicating the walk-parse-resolve logic.

parse_frontmatter lives in selfdoc.utils and is re-exported here for
backward compatibility.
"""

import os

from selfdoc.catalog import ALL_BUILTIN_DIRECTIVES
from selfdoc.directives import resolve_directives, validate_directive_names
from selfdoc.resolver import make_resolver
from selfdoc.utils import parse_frontmatter  # re-export


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
    custom_names = set(config.get("directives", {}).keys())
    validate_directive_names(custom_names)
    valid_names = ALL_BUILTIN_DIRECTIVES | custom_names

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
