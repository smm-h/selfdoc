"""Build pipeline for selfdoc: template scanning, directive resolution, HTML output."""

import os
import shutil

from selfdoc.config import load_config
from selfdoc.directives import resolve_directives
from selfdoc.html import generate_html, get_css
from selfdoc.resolver import make_resolver


def _stub_resolver(name, arg, body):
    """Placeholder resolver that produces a visible unresolved marker."""
    label = f"{name} {arg}".strip()
    return f"> *[selfdoc: {label} — not yet resolved]*"


def build(dir_path=".", config=None):
    """Build docs from templates + directives.

    1. Load config from selfdoc.json
    2. Scan docs/ directory for .md template files
    3. For each template, resolve directives using language-specific extractor
    4. Convert resolved markdown to HTML
    5. Write HTML to output directory
    6. Copy non-.md files (images, CSS, etc.) to output

    Args:
        dir_path: Project root directory.
        config: Pre-loaded config dict (if None, loads from selfdoc.json).

    Returns:
        Dict of {output_path: True} for files written.
    """
    if config is None:
        config = load_config(dir_path)

    if config is None:
        raise RuntimeError(
            "No selfdoc.json found. Run 'selfdoc init' to initialize."
        )

    docs_dir = os.path.join(dir_path, config["docs"].rstrip("/"))
    output_dir = os.path.join(dir_path, config["output"].rstrip("/"))

    if not os.path.isdir(docs_dir):
        raise RuntimeError(
            f"Docs directory '{config['docs']}' not found. "
            "Create it or run 'selfdoc init'."
        )

    # Create the resolver: use language-specific extractor if supported,
    # otherwise fall back to the stub resolver
    resolver = make_resolver(config, dir_path)

    # Scan for .md template files
    markdown_files = {}
    other_files = []

    for root, _dirs, files in os.walk(docs_dir):
        for fname in files:
            full_path = os.path.join(root, fname)
            # Relative path within docs/
            rel_path = os.path.relpath(full_path, docs_dir)

            if fname.endswith(".md"):
                with open(full_path, "r", encoding="utf-8") as f:
                    content = f.read()
                # Resolve directives with the language-aware resolver
                resolved = resolve_directives(content, resolver)
                markdown_files[rel_path] = resolved
            else:
                other_files.append(rel_path)

    if not markdown_files:
        raise RuntimeError(
            f"No .md files found in '{config['docs']}'. Nothing to build."
        )

    # Detect project name from config or directory name
    project_name = os.path.basename(os.path.abspath(dir_path))

    # Convert to HTML
    html_files = generate_html(
        markdown_files,
        project_name=project_name,
    )

    # Ensure output directory exists
    os.makedirs(output_dir, exist_ok=True)

    written = {}

    # Write the external CSS file
    css_path = os.path.join(output_dir, "style.css")
    with open(css_path, "w", encoding="utf-8") as f:
        f.write(get_css())
    written[css_path] = True

    # Write HTML files
    for rel_path, html_content in html_files.items():
        out_path = os.path.join(output_dir, rel_path)
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(html_content)
        written[out_path] = True

    # Copy non-.md files (images, CSS, etc.) to output
    for rel_path in other_files:
        src = os.path.join(docs_dir, rel_path)
        dst = os.path.join(output_dir, rel_path)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)
        written[dst] = True

    return written
