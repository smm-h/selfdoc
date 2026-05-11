"""Build pipeline for selfdoc: template scanning, directive resolution, HTML output."""

import json
import os
import re
import shutil

from selfdoc.config import load_config
from selfdoc.directives import resolve_directives
from selfdoc.html import (
    generate_html, get_css, _md_to_html_path, _slugify,
    _extract_title, _escape_html,
)
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


def _generate_og_svg(project_name, page_title, accent_color="#0969da"):
    """Generate a simple SVG social card (1200x630) for a page.

    Shows the project name at the top, page title in the center,
    on a branded background using the accent color.
    """
    escaped_project = _escape_html(project_name)
    escaped_title = _escape_html(page_title)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="630" '
        f'viewBox="0 0 1200 630">'
        f'<rect width="1200" height="630" fill="{accent_color}" opacity="0.1"/>'
        f'<rect width="1200" height="8" fill="{accent_color}"/>'
        f'<text x="80" y="160" font-family="system-ui, sans-serif" '
        f'font-size="36" font-weight="600" fill="#555">'
        f'{escaped_project}</text>'
        f'<text x="80" y="330" font-family="system-ui, sans-serif" '
        f'font-size="56" font-weight="700" fill="#111">'
        f'{escaped_title}</text>'
        f'<rect x="80" y="380" width="120" height="4" fill="{accent_color}"/>'
        f'</svg>'
    )


def _generate_sitemap(base_url, html_paths):
    """Generate a sitemap.xml string for the given HTML paths."""
    urls = []
    for path in sorted(html_paths):
        urls.append(f"  <url><loc>{base_url}/{path}</loc></url>")
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "\n".join(urls)
        + "\n</urlset>\n"
    )


def _strip_html(text):
    """Strip HTML tags from text, returning plain text."""
    return re.sub(r"<[^>]+>", "", text)


def _first_sentence(text):
    """Extract the first sentence from text."""
    text = text.strip()
    # Find the first sentence-ending punctuation
    match = re.search(r"[.!?]", text)
    if match:
        return text[:match.end()]
    # No punctuation found -- return first 100 chars
    return text[:100]


def _generate_llms_txt(project_name, markdown_files, base_url=None):
    """Generate llms.txt (brief index) content.

    Lists each page with its title and first sentence.
    """
    lines = [f"# {project_name} Documentation", ""]

    # Try to get description from index.md first paragraph
    index_content = markdown_files.get("index.md", "")
    description = ""
    for line in index_content.split("\n"):
        line = line.strip()
        if line and not line.startswith("#"):
            description = line
            break
    if description:
        lines.append(f"> {description}")
        lines.append("")

    lines.append("## Pages")
    lines.append("")

    for md_path in sorted(markdown_files.keys()):
        content = markdown_files[md_path]
        title = _extract_title(content, md_path.replace(".md", ""))
        html_path = _md_to_html_path(md_path)

        # Get first non-heading, non-empty line as summary
        first = ""
        for line in content.split("\n"):
            line = line.strip()
            if line and not line.startswith("#") and not line.startswith("```"):
                first = _first_sentence(line)
                break

        if base_url:
            url = f"{base_url}/{html_path}"
        else:
            url = html_path
        lines.append(f"- [{title}]({url}): {first}")

    return "\n".join(lines) + "\n"


def _generate_llms_full_txt(project_name, markdown_files):
    """Generate llms-full.txt: full text of all pages as plain markdown.

    Strips HTML but keeps markdown text content.
    """
    parts = [f"# {project_name} Documentation", ""]
    for md_path in sorted(markdown_files.keys()):
        content = markdown_files[md_path]
        parts.append(content.strip())
        parts.append("")
        parts.append("---")
        parts.append("")
    return "\n".join(parts) + "\n"


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

    # Get base_url for canonical links and sitemap (Feature 22)
    base_url = config.get("base_url", None)

    # Convert to HTML
    html_files = generate_html(
        markdown_files,
        project_name=project_name,
        version=version,
        has_custom_css=has_custom_css,
        repo=repo,
        docs_dir_name=config["docs"],
        base_url=base_url,
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

    # Generate OG social card SVGs (Feature 21)
    for md_path, content in markdown_files.items():
        html_path = _md_to_html_path(md_path)
        slug = html_path.replace(".html", "")
        page_title = _extract_title(content, slug)
        svg_content = _generate_og_svg(project_name, page_title)
        svg_path = os.path.join(output_dir, f"og-{slug}.svg")
        os.makedirs(os.path.dirname(svg_path), exist_ok=True)
        with open(svg_path, "w", encoding="utf-8") as f:
            f.write(svg_content)
        written[svg_path] = True

    # Generate sitemap.xml (Feature 22) -- only if base_url is set
    if base_url:
        sitemap_content = _generate_sitemap(base_url, list(html_files.keys()))
        sitemap_path = os.path.join(output_dir, "sitemap.xml")
        with open(sitemap_path, "w", encoding="utf-8") as f:
            f.write(sitemap_content)
        written[sitemap_path] = True

    # Generate llms.txt and llms-full.txt (Feature 24)
    llms_txt = _generate_llms_txt(project_name, markdown_files, base_url)
    llms_path = os.path.join(output_dir, "llms.txt")
    with open(llms_path, "w", encoding="utf-8") as f:
        f.write(llms_txt)
    written[llms_path] = True

    llms_full = _generate_llms_full_txt(project_name, markdown_files)
    llms_full_path = os.path.join(output_dir, "llms-full.txt")
    with open(llms_full_path, "w", encoding="utf-8") as f:
        f.write(llms_full)
    written[llms_full_path] = True

    return written
