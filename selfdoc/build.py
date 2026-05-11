"""Build pipeline for selfdoc: template scanning, directive resolution, HTML output."""

import json
import os
import re
import shutil

from selfdoc.config import load_config
from selfdoc.directives import resolve_directives
from selfdoc.html import generate_html, get_css, _md_to_html_path, _slugify
from selfdoc.resolver import make_resolver


def _stub_resolver(name, arg, body):
    """Placeholder resolver that produces a visible unresolved marker."""
    label = f"{name} {arg}".strip()
    return f"> *[selfdoc: {label} — not yet resolved]*"


def _detect_project_version(dir_path):
    """Detect project version from pyproject.toml or package.json.

    Returns the version string, or an empty string if not found.
    """
    # Try pyproject.toml
    pyproject_path = os.path.join(dir_path, "pyproject.toml")
    if os.path.isfile(pyproject_path):
        try:
            try:
                import tomllib
            except ModuleNotFoundError:
                import tomli as tomllib  # type: ignore[no-redef]
            with open(pyproject_path, "rb") as f:
                data = tomllib.load(f)
            version = data.get("project", {}).get("version")
            if version:
                return version
        except Exception:
            pass

    # Try package.json
    package_path = os.path.join(dir_path, "package.json")
    if os.path.isfile(package_path):
        try:
            with open(package_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            version = data.get("version")
            if version:
                return version
        except Exception:
            pass

    return ""


def _build_search_index(markdown_files):
    """Build a search index from markdown files.

    Splits each file by headings and creates one entry per section.
    Each entry has: title, path (html path with anchor), and body text.
    """
    entries = []
    for md_path, content in markdown_files.items():
        html_path = _md_to_html_path(md_path)
        lines = content.split("\n")
        current_title = None
        current_slug = None
        current_body = []

        def _flush():
            if current_title is not None:
                body_text = " ".join(current_body).strip()
                # Strip markdown formatting for plain text
                body_text = re.sub(r"\*\*(.+?)\*\*", r"\1", body_text)
                body_text = re.sub(r"\*(.+?)\*", r"\1", body_text)
                body_text = re.sub(r"`([^`]+)`", r"\1", body_text)
                body_text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", body_text)
                path = html_path
                if current_slug:
                    path = f"{html_path}#{current_slug}"
                entries.append({
                    "title": current_title,
                    "path": path,
                    "body": body_text[:500],
                })

        for line in lines:
            heading_match = re.match(r"^(#{1,6})\s+(.+)$", line)
            if heading_match:
                _flush()
                current_title = heading_match.group(2)
                current_slug = _slugify(current_title)
                current_body = []
            elif line.startswith("```"):
                # Skip code fence markers
                pass
            elif line.startswith(">"):
                # Strip blockquote prefix
                stripped = re.sub(r"^>\s?", "", line)
                current_body.append(stripped)
            elif line.strip():
                current_body.append(line.strip())

        _flush()

    return entries


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

    # Normalize output_dir so we can reliably check containment
    abs_output = os.path.abspath(output_dir)

    for root, _dirs, files in os.walk(docs_dir):
        # Skip the output directory to avoid processing previous build artifacts
        if os.path.abspath(root) == abs_output or os.path.abspath(root).startswith(abs_output + os.sep):
            continue
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

    # Detect project name and version
    project_name = os.path.basename(os.path.abspath(dir_path))
    version = _detect_project_version(dir_path)

    # Check for custom.css in docs/
    custom_css_src = os.path.join(docs_dir, "custom.css")
    has_custom_css = os.path.isfile(custom_css_src)

    # Get repo URL for edit links (Feature 14)
    repo = config.get("repo", None)

    # Convert to HTML
    html_files = generate_html(
        markdown_files,
        project_name=project_name,
        version=version,
        has_custom_css=has_custom_css,
        repo=repo,
        docs_dir_name=config["docs"],
    )

    # Ensure output directory exists
    os.makedirs(output_dir, exist_ok=True)

    written = {}

    # Write the theme CSS file
    theme_name = config.get("theme", "minimal")
    css_path = os.path.join(output_dir, "style.css")
    with open(css_path, "w", encoding="utf-8") as f:
        f.write(get_css(theme_name))
    written[css_path] = True

    # Build and write search index (Feature 19)
    search_index = _build_search_index(markdown_files)
    search_index_path = os.path.join(output_dir, "search-index.json")
    with open(search_index_path, "w", encoding="utf-8") as f:
        json.dump(search_index, f, ensure_ascii=False)
    written[search_index_path] = True

    # Copy custom.css to output if it exists
    if has_custom_css:
        custom_css_dst = os.path.join(output_dir, "custom.css")
        shutil.copy2(custom_css_src, custom_css_dst)
        written[custom_css_dst] = True

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
