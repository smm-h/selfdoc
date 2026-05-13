"""Build pipeline for selfdoc: template scanning, directive resolution, HTML output."""

import gzip
import json
import os
import re
import shutil
import struct
import subprocess
import tempfile
import zlib
from datetime import datetime

from selfdoc.config import load_config
from selfdoc.directives import resolve_directives
from selfdoc.html import (
    generate_html, generate_404_page, get_css, generate_pygments_css,
    _md_to_html_path, _slugify,
    _extract_title, _escape_html, _build_nav,
    _generate_search_js, _minify_js,
)
from selfdoc.resolver import make_resolver

try:
    from predraw.model import Scene, Element, Font
    from predraw.renderer import render_svg
    import cairosvg
    _HAS_PREDRAW = True
except ImportError:
    _HAS_PREDRAW = False


def _read_png_dimensions(filepath):
    """Read width and height from a PNG file's IHDR chunk.

    The IHDR chunk starts at byte 16. Width is 4 bytes big-endian at
    offset 16, height is 4 bytes big-endian at offset 20.
    Returns (width, height) or None if the file is too short or invalid.
    """
    try:
        with open(filepath, "rb") as f:
            header = f.read(24)
        if len(header) < 24:
            return None
        # PNG signature: 89 50 4E 47 0D 0A 1A 0A
        if header[:8] != b"\x89PNG\r\n\x1a\n":
            return None
        width = struct.unpack(">I", header[16:20])[0]
        height = struct.unpack(">I", header[20:24])[0]
        return (width, height)
    except (OSError, struct.error):
        return None


def _read_gif_dimensions(filepath):
    """Read width and height from a GIF file header.

    Bytes 6-7 are width (little-endian uint16), bytes 8-9 are height
    (little-endian uint16).
    Returns (width, height) or None if the file is too short or invalid.
    """
    try:
        with open(filepath, "rb") as f:
            header = f.read(10)
        if len(header) < 10:
            return None
        # GIF signature: GIF87a or GIF89a
        if header[:3] != b"GIF":
            return None
        width = struct.unpack("<H", header[6:8])[0]
        height = struct.unpack("<H", header[8:10])[0]
        return (width, height)
    except (OSError, struct.error):
        return None


def _read_jpeg_dimensions(filepath):
    """Read width and height from a JPEG file by walking SOF markers.

    Walks JPEG segments looking for SOF0-SOF3 markers (\\xff\\xc0 through
    \\xff\\xc3). When found, reads height (2 bytes BE) and width (2 bytes BE)
    after skipping the segment length and precision byte.
    Returns (width, height) or None if the file is invalid or unreadable.
    """
    try:
        with open(filepath, "rb") as f:
            # Validate SOI marker
            soi = f.read(2)
            if soi != b"\xff\xd8":
                return None
            while True:
                # Each segment starts with 0xFF + marker byte
                marker = f.read(2)
                if len(marker) < 2:
                    return None
                if marker[0] != 0xFF:
                    return None
                marker_byte = marker[1]
                # SOF0 through SOF3
                if 0xC0 <= marker_byte <= 0xC3:
                    # Read segment: 2-byte length, 1-byte precision, then dims
                    seg = f.read(7)
                    if len(seg) < 7:
                        return None
                    height = struct.unpack(">H", seg[3:5])[0]
                    width = struct.unpack(">H", seg[5:7])[0]
                    return (width, height)
                # Skip this segment: read 2-byte length, advance
                length_bytes = f.read(2)
                if len(length_bytes) < 2:
                    return None
                seg_len = struct.unpack(">H", length_bytes)[0]
                # seg_len includes the 2 length bytes themselves
                f.seek(seg_len - 2, 1)
    except (OSError, struct.error):
        return None


def _read_webp_dimensions(filepath):
    """Read width and height from a WebP file.

    Supports VP8 (lossy), VP8L (lossless), and VP8X (extended) sub-formats.
    Returns (width, height) or None if the file is invalid or unreadable.
    """
    try:
        with open(filepath, "rb") as f:
            data = f.read(30)
        if len(data) < 16:
            return None
        # Validate RIFF header and WEBP signature
        if data[0:4] != b"RIFF" or data[8:12] != b"WEBP":
            return None
        chunk_type = data[12:16]
        if chunk_type == b"VP8 ":
            # Lossy: width at bytes 26-27, height at 28-29 (LE, masked)
            if len(data) < 30:
                return None
            width = struct.unpack("<H", data[26:28])[0] & 0x3FFF
            height = struct.unpack("<H", data[28:30])[0] & 0x3FFF
            return (width, height)
        if chunk_type == b"VP8L":
            # Lossless: uint32 at byte 21, width = bits 0-13 + 1, height = bits 14-27 + 1
            if len(data) < 25:
                return None
            bits = struct.unpack("<I", data[21:25])[0]
            width = (bits & 0x3FFF) + 1
            height = ((bits >> 14) & 0x3FFF) + 1
            return (width, height)
        if chunk_type == b"VP8X":
            # Extended: uint24 LE at bytes 24-26 + 1 (width), 27-29 + 1 (height)
            if len(data) < 30:
                return None
            width = int.from_bytes(data[24:27], "little") + 1
            height = int.from_bytes(data[27:30], "little") + 1
            return (width, height)
        return None
    except (OSError, struct.error):
        return None


def _get_image_dimensions(filepath):
    """Read dimensions from an image file (PNG, GIF, JPEG, or WebP).

    Returns (width, height) or None if the format is unsupported or
    the file cannot be read.
    """
    ext = os.path.splitext(filepath)[1].lower()
    if ext == ".png":
        return _read_png_dimensions(filepath)
    if ext == ".gif":
        return _read_gif_dimensions(filepath)
    if ext in (".jpg", ".jpeg"):
        return _read_jpeg_dimensions(filepath)
    if ext == ".webp":
        return _read_webp_dimensions(filepath)
    return None


def _add_image_dimensions(html_text, docs_dir, page_rel_path):
    """Add width/height attributes to <img> tags whose source files exist.

    For each <img src="..."> in *html_text*, resolve the src relative to
    the page's directory within *docs_dir*. If the file is a PNG, GIF,
    JPEG, or WebP, read its dimensions and insert width="X" height="Y"
    attributes.
    """
    page_dir = os.path.dirname(os.path.join(docs_dir, page_rel_path))

    def _add_dims(match):
        full_tag = match.group(0)
        src = match.group(1)
        # Skip external URLs
        if src.startswith(("http://", "https://", "//")):
            return full_tag
        # Resolve relative to the page's directory
        img_path = os.path.normpath(os.path.join(page_dir, src))
        dims = _get_image_dimensions(img_path)
        if dims is None:
            return full_tag
        width, height = dims
        # Insert width/height before the closing >
        return full_tag.replace(
            ">",
            f' width="{width}" height="{height}">',
            1,
        )

    return re.sub(r'<img\s[^>]*src="([^"]+)"[^>]*>', _add_dims, html_text)


def _minify_css(css_text):
    """Minify CSS by removing comments, collapsing whitespace, and trimming.

    Simple regex-based approach suitable for well-formed CSS.
    """
    # Remove CSS comments /* ... */
    css_text = re.sub(r"/\*.*?\*/", "", css_text, flags=re.DOTALL)
    # Collapse whitespace (multiple spaces/newlines -> single space)
    css_text = re.sub(r"\s+", " ", css_text)
    # Remove spaces around { } : ; ,
    css_text = re.sub(r"\s*([{}:;,])\s*", r"\1", css_text)
    # Remove trailing semicolons before }
    css_text = re.sub(r";}", "}", css_text)
    # Strip leading/trailing whitespace
    css_text = css_text.strip()
    return css_text


_CRITICAL_CSS_MARKER = "/* --- NON-CRITICAL --- */"


def _extract_critical_css(full_css):
    """Split theme CSS into critical (above-the-fold) and full parts.

    The theme CSS contains a marker comment that separates critical styles
    (needed for first paint) from non-critical styles (loaded async).
    Returns (critical_css, full_css) where critical_css is everything above
    the marker and full_css is the complete stylesheet.
    """
    if _CRITICAL_CSS_MARKER in full_css:
        critical, _ = full_css.split(_CRITICAL_CSS_MARKER, 1)
        return critical.rstrip(), full_css
    # No marker found: treat everything as critical (safe fallback)
    return full_css, full_css


def _minify_html(html_text):
    """Minify HTML by removing comments and collapsing inter-tag whitespace.

    Preserves whitespace inside <pre>, <code>, <script>, and <textarea> tags.
    """
    # Split the HTML into preserved and non-preserved segments.
    # We protect <pre>, <code>, <script>, <textarea> content.
    preserve_pattern = re.compile(
        r"(<(?:pre|code|script|textarea)\b[^>]*>.*?</(?:pre|code|script|textarea)>)",
        re.DOTALL | re.IGNORECASE,
    )
    parts = preserve_pattern.split(html_text)
    result = []
    for i, part in enumerate(parts):
        if i % 2 == 1:
            # Preserved segment -- keep as-is
            result.append(part)
        else:
            # Non-preserved segment -- minify
            # Remove HTML comments <!-- ... -->
            part = re.sub(r"<!--.*?-->", "", part, flags=re.DOTALL)
            # Collapse whitespace between > and <
            part = re.sub(r">\s+<", "> <", part)
            # Collapse runs of whitespace in text nodes to single space
            part = re.sub(r"\s+", " ", part)
            result.append(part)
    return "".join(result)


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


def _generate_og_png_basic(accent_color="#0969da"):
    """Generate a 1200x630 PNG social card using only stdlib (no text).

    Creates a visually distinct card with:
    - Light background derived from accent color
    - Thick accent-colored bar across the top (16px)
    - Decorative accent-colored stripe pattern in the lower portion

    Uses the recommended OG image resolution (1200x630).
    Returns the PNG file contents as bytes.
    """
    width, height = 1200, 630

    # Parse accent color hex to RGB
    ac = accent_color.lstrip("#")
    ar, ag, ab = int(ac[0:2], 16), int(ac[2:4], 16), int(ac[4:6], 16)

    # Background: accent at ~10% opacity on white
    bg_r = 255 - (255 - ar) // 10
    bg_g = 255 - (255 - ag) // 10
    bg_b = 255 - (255 - ab) // 10

    # Build raw pixel data row by row (RGB, filter byte 0 per scanline)
    raw_rows = []
    top_bar_h = 16
    # Decorative stripes in lower portion: 8px accent stripes every 40px
    stripe_start = height - 160

    for y in range(height):
        if y < top_bar_h:
            # Top accent bar
            row = bytes([ar, ag, ab] * width)
        elif y >= stripe_start and (y - stripe_start) % 40 < 8:
            # Accent stripe rows in lower portion
            row = bytes([ar, ag, ab] * width)
        else:
            # Background
            row = bytes([bg_r, bg_g, bg_b] * width)
        # Each row prefixed with filter byte 0 (no filter)
        raw_rows.append(b"\x00" + row)

    raw_data = b"".join(raw_rows)

    # Build PNG chunks
    def _png_chunk(chunk_type, data):
        chunk = chunk_type + data
        crc = struct.pack(">I", zlib.crc32(chunk) & 0xFFFFFFFF)
        return struct.pack(">I", len(data)) + chunk + crc

    # PNG signature
    signature = b"\x89PNG\r\n\x1a\n"

    # IHDR: width, height, bit depth 8, color type 2 (RGB)
    ihdr_data = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    ihdr = _png_chunk(b"IHDR", ihdr_data)

    # IDAT: zlib-compressed pixel data
    compressed = zlib.compress(raw_data, 9)
    idat = _png_chunk(b"IDAT", compressed)

    # IEND
    iend = _png_chunk(b"IEND", b"")

    return signature + ihdr + idat + iend


def _generate_og_png_rich(project_name, title, accent_color, output_path):
    """Generate a 1200x630 PNG social card with text using predraw + cairosvg.

    Builds a predraw Scene with project name, page title, accent bar,
    decorative elements, and renders it to PNG via SVG intermediate.
    """
    # Compute background: accent at 10% opacity on white
    ac = accent_color.lstrip("#")
    ar, ag, ab = int(ac[0:2], 16), int(ac[2:4], 16), int(ac[4:6], 16)
    bg_r = 255 - (255 - ar) // 10
    bg_g = 255 - (255 - ag) // 10
    bg_b = 255 - (255 - ab) // 10
    bg_hex = f"#{bg_r:02x}{bg_g:02x}{bg_b:02x}"

    scene = Scene(
        width=1200,
        height=630,
        background=bg_hex,
        elements=[
            # Top accent bar
            Element(type="rect", x=0, y=0, width=1200, height=8, fill=accent_color),
            # Project name
            Element(
                type="text", x=80, y=160, content=project_name,
                fill="#555555",
                font=Font(family="system-ui, sans-serif", size=36, weight=600),
            ),
            # Page title
            Element(
                type="text", x=80, y=330, content=title,
                fill="#111111",
                font=Font(family="system-ui, sans-serif", size=56, weight=700),
            ),
            # Decorative bar below title
            Element(type="rect", x=80, y=380, width=120, height=4, fill=accent_color),
            # Decorative accent rects at the bottom
            Element(type="rect", x=0, y=470, width=1200, height=8, fill=accent_color, opacity=0.3),
            Element(type="rect", x=0, y=510, width=1200, height=8, fill=accent_color, opacity=0.2),
            Element(type="rect", x=0, y=550, width=1200, height=8, fill=accent_color, opacity=0.15),
            Element(type="rect", x=0, y=590, width=1200, height=8, fill=accent_color, opacity=0.1),
        ],
    )

    svg = render_svg(scene)
    cairosvg.svg2png(
        bytestring=svg.encode("utf-8"),
        write_to=output_path,
        output_width=1200,
        output_height=630,
    )


def _generate_og_png(project_name, title, accent_color="#0969da"):
    """Generate a 1200x630 PNG social card.

    Uses predraw for rich text-bearing cards when available, otherwise
    falls back to the basic stdlib-only version (no text).
    Returns PNG bytes (basic path) or writes to a temp file and returns
    bytes (rich path).
    """
    if _HAS_PREDRAW:
        # Rich path: render to a temp file, read bytes back
        fd, tmp_path = tempfile.mkstemp(suffix=".png")
        os.close(fd)
        try:
            _generate_og_png_rich(project_name, title, accent_color, tmp_path)
            with open(tmp_path, "rb") as f:
                return f.read()
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
    else:
        return _generate_og_png_basic(accent_color)


def _generate_sitemap(base_url, html_paths, page_dates=None):
    """Generate a sitemap.xml string for the given HTML paths.

    Args:
        base_url: Base URL for constructing full URLs.
        html_paths: List of HTML file paths (e.g. ["index.html", "guide.html"]).
        page_dates: Optional dict mapping md paths to (published, modified) tuples.
    """
    if page_dates is None:
        page_dates = {}
    urls = []
    for path in sorted(html_paths):
        # Convert html path to md path for date lookup
        md_path = path.replace(".html", ".md") if path.endswith(".html") else path
        date_tuple = page_dates.get(md_path)
        # Use modified date for lastmod
        date = date_tuple[1] if date_tuple else None
        if date:
            urls.append(
                f"  <url><loc>{base_url}/{path}</loc>"
                f"<lastmod>{date}</lastmod></url>"
            )
        else:
            urls.append(f"  <url><loc>{base_url}/{path}</loc></url>")
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "\n".join(urls)
        + "\n</urlset>\n"
    )


def _parse_frontmatter(content):
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
        # Try to convert numeric values
        try:
            value = int(value)
        except ValueError:
            try:
                value = float(value)
            except ValueError:
                pass
        metadata[key] = value

    remaining = "\n".join(lines[end_idx + 1:]).lstrip("\n")
    return metadata, remaining


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

        url = f"{base_url}/{html_path}"
        lines.append(f"- [{title}]({url}): {first}")

    return "\n".join(lines) + "\n"


def _generate_llms_full_txt(project_name, markdown_files):
    """Generate llms-full.txt: full text of all pages as plain markdown.

    Each page section starts with a title heading and path comment,
    followed by the page content, separated by '---'.
    """
    parts = [f"# {project_name} Documentation", ""]
    for md_path in sorted(markdown_files.keys()):
        content = markdown_files[md_path]
        fallback = os.path.splitext(os.path.basename(md_path))[0].replace(
            "-", " "
        ).replace("_", " ").title()
        title = _extract_title(content, fallback)
        parts.append(f"## {title}")
        parts.append(f"<!-- path: {md_path} -->")
        parts.append("")
        parts.append(content.strip())
        parts.append("")
        parts.append("---")
        parts.append("")
    return "\n".join(parts) + "\n"


def _generate_atom_feed(
    output_dir, base_url, project_name, description,
    markdown_files, frontmatter, page_dates,
):
    """Generate an Atom feed (feed.xml) for the documentation site.

    Returns the path written.
    """
    if frontmatter is None:
        frontmatter = {}
    if page_dates is None:
        page_dates = {}

    entries = []
    for md_path, content in sorted(markdown_files.items()):
        html_path = _md_to_html_path(md_path)

        # Determine page title: frontmatter > first heading > filename
        meta = frontmatter.get(md_path, {})
        title = meta.get("title")
        if not title:
            title = _extract_title(content, md_path.replace(".md", ""))

        # Get first sentence for summary
        summary = ""
        for line in content.split("\n"):
            line = line.strip()
            if line and not line.startswith("#") and not line.startswith("```"):
                summary = _first_sentence(line)
                break

        # Get page date (modified date from tuple)
        date_tuple = page_dates.get(md_path)
        page_date = date_tuple[1] if date_tuple else ""

        # Escape for XML
        escaped_title = _escape_html(title)
        escaped_summary = _escape_html(summary)

        entry = (
            f"  <entry>\n"
            f"    <title>{escaped_title}</title>\n"
            f"    <link href=\"{base_url}/{html_path}\"/>\n"
            f"    <id>{base_url}/{html_path}</id>\n"
            f"    <updated>{page_date}T00:00:00Z</updated>\n"
            f"    <summary>{escaped_summary}</summary>\n"
            f"  </entry>"
        )
        entries.append(entry)

    # Find most recent date for the feed-level <updated>
    all_dates = [page_dates.get(p, (None, ""))[1] for p in markdown_files]
    all_dates = [d for d in all_dates if d]
    most_recent = max(all_dates) if all_dates else datetime.now().strftime("%Y-%m-%d")

    # Build subtitle line
    subtitle_line = ""
    if description:
        subtitle_line = f"  <subtitle>{_escape_html(description)}</subtitle>\n"

    feed_xml = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<feed xmlns="http://www.w3.org/2005/Atom">\n'
        f"  <title>{_escape_html(project_name)} Documentation</title>\n"
        f'  <link href="{base_url}/feed.xml" rel="self"/>\n'
        f'  <link href="{base_url}/"/>\n'
        f"  <id>{base_url}/</id>\n"
        f"  <updated>{most_recent}T00:00:00Z</updated>\n"
        f"{subtitle_line}"
        + "\n".join(entries) + "\n"
        "</feed>\n"
    )

    feed_path = os.path.join(output_dir, "feed.xml")
    with open(feed_path, "w", encoding="utf-8") as f:
        f.write(feed_xml)
    return feed_path


_COMPRESSIBLE_EXTENSIONS = {'.html', '.css', '.js', '.json', '.xml', '.txt', '.svg'}


def _compress_output(output_dir):
    """Generate gzip and brotli compressed companions for text-based files.

    Walks the output directory and creates .gz (and optionally .br) files
    alongside each compressible file. Uses atomic writes (write to tmp,
    then os.replace) for safety.

    Returns the count of files that were compressed.
    """
    try:
        import brotli
        has_brotli = True
    except ImportError:
        has_brotli = False

    count = 0
    for root, _dirs, files in os.walk(output_dir):
        for fname in files:
            ext = os.path.splitext(fname)[1].lower()
            if ext not in _COMPRESSIBLE_EXTENSIONS:
                continue

            filepath = os.path.join(root, fname)
            with open(filepath, "rb") as f:
                data = f.read()

            # gzip companion
            gz_path = filepath + ".gz"
            fd, tmp_path = tempfile.mkstemp(dir=root)
            try:
                with os.fdopen(fd, "wb") as tmp_f:
                    with gzip.GzipFile(
                        fileobj=tmp_f, mode="wb", compresslevel=9,
                    ) as gz_f:
                        gz_f.write(data)
                os.replace(tmp_path, gz_path)
            except Exception:
                # Clean up temp file on failure
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise

            # brotli companion (optional)
            if has_brotli:
                br_path = filepath + ".br"
                fd, tmp_path = tempfile.mkstemp(dir=root)
                try:
                    with os.fdopen(fd, "wb") as tmp_f:
                        tmp_f.write(brotli.compress(data))
                    os.replace(tmp_path, br_path)
                except Exception:
                    try:
                        os.unlink(tmp_path)
                    except OSError:
                        pass
                    raise

            count += 1

    return count, has_brotli


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
    frontmatter = {}  # {rel_path: metadata_dict} (Feature 34)
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
                # Parse frontmatter (Feature 34)
                metadata, content = _parse_frontmatter(content)
                # Resolve directives with the language-aware resolver
                resolved = resolve_directives(content, resolver)
                markdown_files[rel_path] = resolved
                if metadata:
                    frontmatter[rel_path] = metadata
            else:
                other_files.append(rel_path)

    # Build page_dates: map md_path -> (published, modified) tuple
    # modified: frontmatter "updated" > frontmatter "date" > file mtime
    # published: frontmatter "date" > file mtime (never use "updated")
    page_dates = {}
    for rel_path in markdown_files:
        meta = frontmatter.get(rel_path, {})
        has_updated = "updated" in meta
        has_date = "date" in meta
        if has_updated and has_date:
            modified = str(meta["updated"])
            published = str(meta["date"])
        elif has_updated:
            modified = str(meta["updated"])
            published = None
        elif has_date:
            modified = str(meta["date"])
            published = str(meta["date"])
        else:
            full_path = os.path.join(docs_dir, rel_path)
            mtime = os.path.getmtime(full_path)
            mtime_str = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d")
            modified = mtime_str
            published = mtime_str
        page_dates[rel_path] = (published, modified)

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

    # Detect git branch for edit links
    branch = config.get("branch")
    if not branch:
        try:
            result = subprocess.run(
                ["git", "symbolic-ref", "--short", "HEAD"],
                capture_output=True, text=True, timeout=5,
                cwd=dir_path,
            )
            if result.returncode == 0 and result.stdout.strip():
                branch = result.stdout.strip()
        except (OSError, subprocess.TimeoutExpired):
            pass
    if not branch:
        branch = "main"

    # Get base_url for canonical links and sitemap (Feature 22)
    base_url = config.get("base_url", None)

    # Get lang attribute for HTML pages (default "en")
    lang = config.get("lang") or "en"

    # Get author from config for JSON-LD structured data
    author = config.get("author")

    # Get project-level description from config
    config_description = config.get("description", "")

    # Atom feed link in HTML <head>
    feed_url = "feed.xml"

    # Extract critical CSS from raw theme (before minification) for inlining
    theme_name = config.get("theme", "minimal")
    raw_theme_css = get_css(theme_name)
    critical_css, _ = _extract_critical_css(raw_theme_css)
    critical_css = _minify_css(critical_css)

    # Convert to HTML
    html_files = generate_html(
        markdown_files,
        project_name=project_name,
        version=version,
        has_custom_css=has_custom_css,
        repo=repo,
        docs_dir_name=config["docs"],
        base_url=base_url,
        frontmatter=frontmatter,
        lang=lang,
        page_dates=page_dates,
        author=author,
        feed_url=feed_url,
        critical_css=critical_css,
        twitter_site=config.get("twitter"),
        search=config.get("search"),
        feedback=config.get("feedback"),
        branch=branch,
        search_engine=config.get("search_engine"),
        branding=config.get("branding"),
        config_description=config_description,
    )

    # Post-process HTML pages: add image dimensions from file inspection
    # (Phase 3.3). Convert md_path keys to html_path keys for lookup.
    for html_path in list(html_files):
        md_path = html_path.replace(".html", ".md") if html_path.endswith(".html") else html_path
        html_files[html_path] = _add_image_dimensions(
            html_files[html_path], docs_dir, md_path,
        )

    # Ensure output directory exists
    os.makedirs(output_dir, exist_ok=True)

    written = {}

    # Write the theme CSS file (with Pygments syntax highlighting rules appended)
    css_path = os.path.join(output_dir, "style.css")
    theme_css = raw_theme_css
    pygments_css = generate_pygments_css()
    if pygments_css:
        theme_css = theme_css + "\n\n/* Pygments syntax highlighting */\n" + pygments_css
    theme_css = _minify_css(theme_css)
    with open(css_path, "w", encoding="utf-8") as f:
        f.write(theme_css)
    written[css_path] = True

    # Build and write search index (Feature 19)
    search_index = _build_search_index(markdown_files)
    search_index_path = os.path.join(output_dir, "search-index.json")
    with open(search_index_path, "w", encoding="utf-8") as f:
        json.dump(search_index, f, ensure_ascii=False)
    written[search_index_path] = True

    # Generate external search JS (Feature 19 -- externalized, pluggable engine)
    search_engine = config.get("search_engine") or "builtin"
    search_js_path = os.path.join(output_dir, "search.js")
    with open(search_js_path, "w", encoding="utf-8") as f:
        f.write(_minify_js(_generate_search_js(engine=search_engine)))
    written[search_js_path] = True

    # Copy custom.css to output if it exists
    if has_custom_css:
        custom_css_dst = os.path.join(output_dir, "custom.css")
        shutil.copy2(custom_css_src, custom_css_dst)
        written[custom_css_dst] = True

    # Write HTML files (minified)
    for rel_path, html_content in html_files.items():
        out_path = os.path.join(output_dir, rel_path)
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(_minify_html(html_content))
        written[out_path] = True

    # Copy non-.md files (images, CSS, etc.) to output
    for rel_path in other_files:
        src = os.path.join(docs_dir, rel_path)
        dst = os.path.join(output_dir, rel_path)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)
        written[dst] = True

    # Generate auxiliary files (OG cards, sitemap, llms.txt, 404, favicon, feed, etc.)
    aux_written = _generate_auxiliary_files(
        output_dir=output_dir,
        project_name=project_name,
        version=version,
        markdown_files=markdown_files,
        html_paths=list(html_files.keys()),
        base_url=base_url,
        has_custom_css=has_custom_css,
        repo=repo,
        lang=lang,
        page_dates=page_dates,
        frontmatter=frontmatter,
        description=config_description,
        feed_url=feed_url,
        critical_css=critical_css,
    )
    written.update(aux_written)

    # Pre-compress text-based output files (gzip + optional brotli)
    compress_count, has_brotli = _compress_output(output_dir)
    if has_brotli:
        print(f"Pre-compressed {compress_count} files (gzip + brotli)")
    else:
        print(
            f"Pre-compressed {compress_count} files "
            f"(gzip only, install brotli for better compression)"
        )

    if _HAS_PREDRAW:
        print("OG cards: rich (predraw)")
    else:
        print("OG cards: basic (install predraw for text)")

    return written


def _generate_auxiliary_files(
    output_dir, project_name, version, markdown_files, html_paths,
    base_url, has_custom_css, repo, lang="en", page_dates=None,
    frontmatter=None, description="", feed_url=None, critical_css=None,
):
    """Generate auxiliary build artifacts (OG cards, sitemap, llms.txt, 404, favicon, feed).

    Called by build() after the main HTML pages and static files are written.
    Returns a dict of {output_path: True} for files written.
    """
    written = {}

    # Generate OG social card PNGs (Feature 21)
    for md_path, content in markdown_files.items():
        html_path = _md_to_html_path(md_path)
        slug = html_path.replace(".html", "")
        page_title = _extract_title(content, slug)
        png_bytes = _generate_og_png(project_name, page_title)
        png_path = os.path.join(output_dir, f"og-{slug}.png")
        os.makedirs(os.path.dirname(png_path), exist_ok=True)
        with open(png_path, "wb") as f:
            f.write(png_bytes)
        written[png_path] = True

    # Generate sitemap.xml (Feature 22)
    sitemap_content = _generate_sitemap(base_url, html_paths, page_dates)
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

    # Generate Atom feed (feed.xml)
    feed_path = _generate_atom_feed(
        output_dir=output_dir,
        base_url=base_url,
        project_name=project_name,
        description=description,
        markdown_files=markdown_files,
        frontmatter=frontmatter,
        page_dates=page_dates,
    )
    written[feed_path] = True

    # Generate 404.html (Feature 39)
    nav_items = _build_nav(markdown_files, frontmatter)
    not_found_html = generate_404_page(
        project_name=project_name,
        version=version,
        has_custom_css=has_custom_css,
        nav_items=nav_items,
        repo=repo,
        base_url=base_url,
        lang=lang,
        feed_url=feed_url,
        critical_css=critical_css,
    )
    not_found_path = os.path.join(output_dir, "404.html")
    with open(not_found_path, "w", encoding="utf-8") as f:
        f.write(not_found_html)
    written[not_found_path] = True

    # Generate favicon.svg from project initials (Feature 40)
    favicon_svg = _generate_favicon_svg(project_name)
    favicon_path = os.path.join(output_dir, "favicon.svg")
    with open(favicon_path, "w", encoding="utf-8") as f:
        f.write(favicon_svg)
    written[favicon_path] = True

    # Generate robots.txt (allow all crawlers including AI bots)
    robots_path = _generate_robots_txt(output_dir, base_url)
    written[robots_path] = True

    # Generate _headers (Cloudflare Pages security headers)
    headers_path = _generate_headers(output_dir)
    written[headers_path] = True

    # Generate _redirects (Cloudflare Pages trailing slash rules)
    redirects_path = _generate_redirects(output_dir)
    written[redirects_path] = True

    return written


def _generate_robots_txt(output_dir, base_url):
    """Generate robots.txt allowing all crawlers including AI bots."""
    lines = [
        "User-agent: *",
        "Allow: /",
        "",
        "User-agent: GPTBot",
        "Allow: /",
        "",
        "User-agent: ChatGPT-User",
        "Allow: /",
        "",
        "User-agent: Google-Extended",
        "Allow: /",
        "",
        "User-agent: PerplexityBot",
        "Allow: /",
        "",
        "User-agent: ClaudeBot",
        "Allow: /",
        "",
        "User-agent: Googlebot",
        "Allow: /",
        "",
        "User-agent: OAI-SearchBot",
        "Allow: /",
        "",
        f"Sitemap: {base_url}/sitemap.xml",
    ]
    content = "\n".join(lines) + "\n"
    path = os.path.join(output_dir, "robots.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path


def _generate_headers(output_dir):
    """Generate _headers file (Cloudflare Pages format) with security headers."""
    content = (
        "/*\n"
        "  Strict-Transport-Security: max-age=31536000; includeSubDomains; preload\n"
        "  X-Content-Type-Options: nosniff\n"
        "  X-Frame-Options: DENY\n"
        "  Referrer-Policy: strict-origin-when-cross-origin\n"
        "  Permissions-Policy: camera=(), microphone=(), geolocation=()\n"
        "  X-XSS-Protection: 0\n"
        "\n"
        "/style.css\n"
        "  Cache-Control: public, max-age=31536000, immutable\n"
        "\n"
        "/*.svg\n"
        "  Cache-Control: public, max-age=31536000, immutable\n"
    )
    path = os.path.join(output_dir, "_headers")
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path


def _generate_redirects(output_dir):
    """Generate _redirects file (Cloudflare Pages format) with trailing slash rules."""
    content = (
        "# Strip trailing slashes (except root)\n"
        "/:path/ /:path 301\n"
    )
    path = os.path.join(output_dir, "_redirects")
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path


def _generate_favicon_svg(project_name):
    """Generate a simple SVG favicon from the project name's initial (Feature 40).

    Uses the first letter (uppercase) of the project name, with the accent
    color as the background.
    """
    initial = project_name[0].upper() if project_name else "D"
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">'
        f'<rect width="32" height="32" rx="4" fill="#0969da"/>'
        f'<text x="16" y="22" text-anchor="middle" fill="white" '
        f'font-family="system-ui" font-size="18" font-weight="700">'
        f'{_escape_html(initial)}</text>'
        '</svg>'
    )
