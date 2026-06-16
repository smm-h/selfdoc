"""Build pipeline for selfdoc: template scanning, directive resolution, HTML output."""

import dataclasses
from dataclasses import dataclass
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

from selfdoc.config import load_config, ConfigError
from selfdoc.context import SearchEntry
from selfdoc.docs import resolve_all_docs
from selfdoc.utils import detect_project_version
from selfdoc.html import (
    generate_html, generate_404_page, get_css, generate_pygments_css,
    _md_to_html_path, _html_path_to_url, _html_to_md_path, _slugify,
    _extract_title, _escape_html, _build_nav,
    _generate_search_js, _minify_js,
)
from selfdoc.themes import get_theme_meta
from selfdoc.urls import SimpleURLBuilder

try:
    from predraw.model import Scene, Element, Font
    from predraw.renderer import render_svg
    import cairosvg
    _HAS_PREDRAW = True
except ImportError:
    _HAS_PREDRAW = False


@dataclass(frozen=True, slots=True)
class BuildResult:
    """Result of build_single() -- all outputs needed by callers."""

    html_files: dict
    markdown_files: dict
    frontmatter: dict
    page_dates: dict
    nav_items: list
    search_entries: list
    project_name: str
    version: str
    config: dict
    docs_dir: str
    other_files: list
    has_custom_css: bool
    raw_theme_css: str
    theme_meta: dict
    critical_css: str
    config_description: str
    base_url: str | None
    feed_url: str
    lang: str
    url_builder: object | None = None


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


def _stub_resolver(name, attrs, body):
    """Placeholder resolver that produces a visible unresolved marker."""
    attrs_str = " ".join(f'{k}="{v}"' for k, v in attrs.items()) if attrs else ""
    label = f"{name} {attrs_str}".strip()
    return f"> *[selfdoc: {label} — not yet resolved]*"


def _extract_version_content(version, config, base_dir):
    """Extract docs and source content from a git tag into a cache directory.

    Tries tag names ``v{version}`` then ``{version}``. Uses
    ``git archive | tar -x`` to populate ``.selfdoc/cache/{version}/``.
    The tag's commit hash is stored in a ``.hash`` sentinel; if the tag
    still points to the same commit, extraction is skipped.

    Also ensures ``.selfdoc/cache/.gitignore`` exists with ``*`` so the
    entire cache directory is ignored by git.

    Returns the cache directory path.
    Raises RuntimeError if neither tag name exists.
    """
    cache_root = os.path.join(base_dir, ".selfdoc", "cache")
    cache_dir = os.path.join(cache_root, version)
    hash_file = os.path.join(cache_dir, ".hash")

    # Ensure .gitignore in cache root
    os.makedirs(cache_root, exist_ok=True)
    gitignore_path = os.path.join(cache_root, ".gitignore")
    if not os.path.isfile(gitignore_path):
        with open(gitignore_path, "w", encoding="utf-8") as f:
            f.write("*\n")

    # Determine tag name
    tag_name = None
    for candidate in (f"v{version}", version):
        result = subprocess.run(
            ["git", "rev-parse", f"refs/tags/{candidate}"],
            capture_output=True, text=True, timeout=10,
            cwd=base_dir,
        )
        if result.returncode == 0:
            tag_name = candidate
            break

    if tag_name is None:
        raise RuntimeError(
            f"Git tag for version '{version}' not found. "
            f"Tried 'v{version}' and '{version}'."
        )

    # Get commit hash for the tag (dereference annotated tags)
    result = subprocess.run(
        ["git", "rev-parse", f"{tag_name}^{{commit}}"],
        capture_output=True, text=True, timeout=10,
        cwd=base_dir,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Failed to resolve commit for tag '{tag_name}': "
            f"{result.stderr.strip()}"
        )
    commit_hash = result.stdout.strip()

    # Cache validation: skip extraction if hash matches
    if os.path.isfile(hash_file):
        with open(hash_file, "r", encoding="utf-8") as f:
            cached_hash = f.read().strip()
        if cached_hash == commit_hash:
            return cache_dir

    # Clear stale cache and re-extract
    if os.path.isdir(cache_dir):
        shutil.rmtree(cache_dir)
    os.makedirs(cache_dir, exist_ok=True)

    # Determine paths to extract: docs dir + source dirs
    docs_path = config["docs"].rstrip("/")
    from selfdoc.extractors import source_paths as _source_paths

    raw_source_paths = _source_paths(config) if config.get("source") else []
    archive_paths = [docs_path] + [s.rstrip("/") for s in raw_source_paths]

    # Run git archive piped into tar
    git_cmd = ["git", "archive", tag_name] + archive_paths
    tar_cmd = ["tar", "-x", "-C", cache_dir]

    git_proc = subprocess.Popen(
        git_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        cwd=base_dir,
    )
    tar_proc = subprocess.Popen(
        tar_cmd, stdin=git_proc.stdout, stderr=subprocess.PIPE,
        cwd=base_dir,
    )
    git_proc.stdout.close()

    _, tar_err = tar_proc.communicate(timeout=30)
    git_proc.wait(timeout=30)

    if git_proc.returncode != 0:
        raise RuntimeError(
            f"git archive failed for tag '{tag_name}': "
            f"{git_proc.stderr.read().decode().strip()}"
        )
    if tar_proc.returncode != 0:
        raise RuntimeError(
            f"tar extraction failed for tag '{tag_name}': "
            f"{tar_err.decode().strip()}"
        )

    # Write hash sentinel
    with open(hash_file, "w", encoding="utf-8") as f:
        f.write(commit_hash + "\n")

    return cache_dir




def _build_search_index(
    markdown_files,
    version="",
    locale="",
    target="",
    project="",
    frontmatter=None,
    nav_items=None,
):
    """Build a search index from markdown files.

    Splits each file by headings and creates one entry per section.
    Returns a list of SearchEntry dataclasses with title, path, body,
    and metadata fields (version, locale, group, type, tags, etc.).
    """
    if frontmatter is None:
        frontmatter = {}
    if nav_items is None:
        nav_items = []

    # Build md_path -> nav group name lookup from nav_items
    _page_group = {}
    for nav_item in nav_items:
        if "group" in nav_item:
            group_name = nav_item["group"]
            for sub_item in nav_item.get("items", []):
                _page_group[sub_item.get("md_path", "")] = group_name

    entries = []
    for md_path, content in markdown_files.items():
        url_path = _html_path_to_url(_md_to_html_path(md_path))
        lines = content.split("\n")
        current_title = None
        current_slug = None
        current_body = []

        # Derive per-page metadata
        nav_group = _page_group.get(md_path, "")
        page_meta = frontmatter.get(md_path, {})
        tags_val = page_meta.get("tags", [])
        # tags may be a string (no comma in frontmatter) -- wrap in list
        if isinstance(tags_val, str):
            tags_val = [tags_val] if tags_val else []
        page_tags = list(tags_val)

        # Derive page type: explicit frontmatter overrides heuristic
        if page_meta.get("type"):
            page_type = page_meta["type"]
        else:
            base_name = md_path.replace(".md", "").lower()
            if page_meta.get("generated") is True and "API" in nav_group:
                page_type = "api"
            elif page_meta.get("generated") is True and "CLI" in nav_group:
                page_type = "cli"
            elif "changelog" in base_name:
                page_type = "changelog"
            elif "glossary" in base_name:
                page_type = "glossary"
            else:
                page_type = "guide"

        def _flush():
            if current_title is not None:
                body_text = " ".join(current_body).strip()
                # Strip markdown formatting for plain text
                body_text = re.sub(r"\*\*(.+?)\*\*", r"\1", body_text)
                body_text = re.sub(r"\*(.+?)\*", r"\1", body_text)
                body_text = re.sub(r"`([^`]+)`", r"\1", body_text)
                body_text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", body_text)
                path = url_path
                if current_slug:
                    path = f"{url_path}#{current_slug}"
                entries.append(SearchEntry(
                    title=current_title,
                    path=path,
                    body=body_text[:500],
                    version=version,
                    locale=locale,
                    target=target,
                    project=project,
                    group=nav_group,
                    type=page_type,
                    tags=page_tags,
                ))

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


def _generate_sitemap(base_url, html_paths, page_dates=None, url_builder=None):
    """Generate a sitemap.xml string for the given HTML paths.

    Args:
        base_url: Base URL for constructing full URLs (kept for backward compat).
        html_paths: List of HTML file paths (e.g. ["index.html", "guide.html"]).
        page_dates: Optional dict mapping md paths to (published, modified) tuples.
        url_builder: Optional URLBuilder for constructing URLs. When provided,
            used instead of raw base_url string concatenation.
    """
    if url_builder is None and base_url is not None:
        url_builder = SimpleURLBuilder(base_url)
    if page_dates is None:
        page_dates = {}
    urls = []
    for path in sorted(html_paths):
        # Convert html path to md path for date lookup.
        # html_paths may include a locale/version prefix (e.g. "en/1.0.0/guide/index.html")
        # while page_dates is keyed by unprefixed md_path (e.g. "guide.md").
        md_path = _html_to_md_path(path)
        url = _html_path_to_url(path)
        date_tuple = page_dates.get(md_path)
        if date_tuple is None:
            # Try stripping prefix: "en/1.0.0/guide.md" -> "guide.md"
            parts = md_path.split("/")
            if len(parts) > 1:
                date_tuple = page_dates.get(parts[-1])
                if date_tuple is None and len(parts) > 2:
                    date_tuple = page_dates.get("/".join(parts[2:]))
        # Use modified date for lastmod
        date = date_tuple[1] if date_tuple else None
        full_url = url_builder.page_url(url) if url_builder else f"{base_url}/{url}"
        if date:
            urls.append(
                f"  <url><loc>{full_url}</loc>"
                f"<lastmod>{date}</lastmod></url>"
            )
        else:
            urls.append(f"  <url><loc>{full_url}</loc></url>")
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


def _generate_llms_txt(project_name, markdown_files, base_url=None, url_builder=None):
    """Generate llms.txt (brief index) content.

    Lists each page with its title and first sentence.
    """
    if url_builder is None and base_url is not None:
        url_builder = SimpleURLBuilder(base_url)
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
        url_path = _html_path_to_url(_md_to_html_path(md_path))

        # Get first non-heading, non-empty line as summary
        first = ""
        for line in content.split("\n"):
            line = line.strip()
            if line and not line.startswith("#") and not line.startswith("```"):
                first = _first_sentence(line)
                break

        url = url_builder.page_url(url_path) if url_builder else f"{base_url}/{url_path}"
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
    feed_max_entries=None, url_builder=None,
):
    """Generate an Atom feed (feed.xml) for the documentation site.

    Returns the path written.
    """
    if url_builder is None and base_url is not None:
        url_builder = SimpleURLBuilder(base_url)
    if frontmatter is None:
        frontmatter = {}
    if page_dates is None:
        page_dates = {}

    entries = []  # list of (page_date, entry_xml) tuples
    for md_path, content in sorted(markdown_files.items()):
        # Skip pages with feed: false in frontmatter
        meta = frontmatter.get(md_path, {})
        if meta.get("feed") is False:
            continue

        url_path = _html_path_to_url(_md_to_html_path(md_path))
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

        page_full_url = url_builder.page_url(url_path) if url_builder else f"{base_url}/{url_path}"
        entry = (
            f"  <entry>\n"
            f"    <title>{escaped_title}</title>\n"
            f"    <link href=\"{page_full_url}\"/>\n"
            f"    <id>{page_full_url}</id>\n"
            f"    <updated>{page_date}T00:00:00Z</updated>\n"
            f"    <summary>{escaped_summary}</summary>\n"
            f"  </entry>"
        )
        entries.append((page_date, entry))

    # Sort by modification date descending (most recent first)
    entries.sort(key=lambda e: e[0], reverse=True)

    # Truncate to feed_max_entries if set
    if feed_max_entries is not None:
        entries = entries[:feed_max_entries]

    # Find most recent date for the feed-level <updated>
    all_dates = [page_dates.get(p, (None, ""))[1] for p in markdown_files]
    all_dates = [d for d in all_dates if d]
    most_recent = max(all_dates) if all_dates else datetime.now().strftime("%Y-%m-%d")

    # Build subtitle line
    subtitle_line = ""
    if description:
        subtitle_line = f"  <subtitle>{_escape_html(description)}</subtitle>\n"

    feed_self_url = url_builder.feed_url() if url_builder else f"{base_url}/feed.xml"
    feed_home_url = url_builder.page_url("") if url_builder else f"{base_url}/"
    feed_xml = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<feed xmlns="http://www.w3.org/2005/Atom">\n'
        f"  <title>{_escape_html(project_name)} Documentation</title>\n"
        f'  <link href="{feed_self_url}" rel="self"/>\n'
        f'  <link href="{feed_home_url}"/>\n'
        f"  <id>{feed_home_url}</id>\n"
        f"  <updated>{most_recent}T00:00:00Z</updated>\n"
        f"{subtitle_line}"
        + "\n".join(entry_xml for _, entry_xml in entries) + "\n"
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


def build_single(dir_path=".", config=None, output_subdir="",
                  url_prefix="", version_override=None,
                  locale_override=None,
                  available_versions=None, available_locales=None,
                  current_version="", current_locale="",
                  is_latest=True, page_filter=None):
    """Build HTML and search entries for a single version/locale of docs.

    Performs config loading, template resolution, HTML generation, image
    dimension post-processing, and search index building. Does NOT write
    any files to disk -- the caller (``build()``) handles all IO.

    Args:
        dir_path: Project root directory.
        config: Pre-loaded config dict (if None, loads from selfdoc.json).
        output_subdir: Subdirectory within output for this build (e.g. "en/0.7.0").
        url_prefix: URL path prefix for versioned/localized links (e.g. "en/0.7.0").
        version_override: Override detected version string (optional).
        locale_override: Override detected locale string (optional).

    Returns:
        Tuple of (html_files, markdown_files, frontmatter, page_dates,
        nav_items, search_entries, project_name, version, config,
        docs_dir, other_files, has_custom_css, raw_theme_css, theme_meta,
        critical_css, config_description, base_url, feed_url, lang).
    """
    if config is None:
        config = load_config(dir_path)

    if config is None:
        raise RuntimeError(
            "No selfdoc.json found. Run 'selfdoc init' to initialize."
        )

    # Compute output_subdir and url_prefix from config if not explicitly set
    if not output_subdir and not url_prefix:
        locales = config.get("locales")
        versions = config.get("versions")
        if locales and versions:
            # Find default locale (one with default: true, or first)
            default_locale = locales[0]
            for loc in locales:
                if loc.get("default") is True:
                    default_locale = loc
                    break
            locale_code = default_locale["code"]
            version_str = versions[0]["version"]
            output_subdir = f"{locale_code}/{version_str}"
            url_prefix = output_subdir

    docs_dir = os.path.join(dir_path, config["docs"].rstrip("/"))
    output_dir = os.path.join(dir_path, config["output"].rstrip("/"))

    if not os.path.isdir(docs_dir):
        raise RuntimeError(
            f"Docs directory '{config['docs']}' not found. "
            "Create it or run 'selfdoc init'."
        )

    # Resolve all .md templates via the shared pipeline
    all_docs = resolve_all_docs(config, docs_dir=docs_dir, base_dir=dir_path)
    markdown_files = {rp: resolved for rp, (fm, resolved, raw, _) in all_docs.items()}
    frontmatter = {rp: fm for rp, (fm, resolved, raw, _) in all_docs.items() if fm}

    # Collect non-.md static assets for copying
    other_files = []
    abs_output = os.path.abspath(output_dir)

    for root, _dirs, files in os.walk(docs_dir):
        if os.path.abspath(root) == abs_output or os.path.abspath(root).startswith(abs_output + os.sep):
            continue
        for fname in files:
            if not fname.endswith(".md"):
                full_path = os.path.join(root, fname)
                other_files.append(os.path.relpath(full_path, docs_dir))

    # Save content/description hashes for staleness detection.
    # Build always proceeds -- staleness is only enforced at check time.
    # Prefix hash keys with locale code to avoid collisions between locales
    # (each locale may have the same relative paths like "index.md").
    from selfdoc.staleness import update_hashes
    if locale_override:
        prefixed_docs = {
            f"{locale_override}/{rp}": val
            for rp, val in all_docs.items()
        }
        update_hashes(prefixed_docs, dir_path)
    else:
        update_hashes(all_docs, dir_path)

    # Apply page filter if provided (used by build() to partition
    # versioned and unversioned pages into separate build_single calls)
    if page_filter is not None:
        markdown_files = {k: v for k, v in markdown_files.items() if k in page_filter}
        frontmatter = {k: v for k, v in frontmatter.items() if k in page_filter}

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

    # Auto-detect changelog in project root (case-insensitive)
    changelog_path = None
    for name in ("CHANGELOG.md", "Changelog.md", "changelog.md"):
        candidate = os.path.join(dir_path, name)
        if os.path.isfile(candidate):
            changelog_path = candidate
            break

    if changelog_path is not None and (page_filter is None or "changelog.md" in page_filter):
        with open(changelog_path, "r", encoding="utf-8") as f:
            changelog_content = f.read()
        # Inject as if it were docs/changelog.md so it flows through
        # the normal pipeline (nav, prev/next, HTML wrapping, etc.)
        markdown_files["changelog.md"] = changelog_content
        frontmatter["changelog.md"] = {
            "title": "Changelog",
            "order": 999,
            "feed": False,
        }

    if not markdown_files:
        if page_filter is not None:
            # Filtered build may legitimately have no pages (e.g. all pages
            # are unversioned, so the versioned filter yields nothing)
            return BuildResult(
                html_files={},
                markdown_files={},
                frontmatter={},
                page_dates={},
                nav_items=[],
                search_entries=[],
                project_name=os.path.basename(os.path.abspath(dir_path)),
                version=version_override if version_override is not None else "",
                config=config,
                docs_dir=docs_dir,
                other_files=[],
                has_custom_css=os.path.isfile(os.path.join(docs_dir, "custom.css")),
                raw_theme_css=get_css(config.get("theme", "minimal")),
                theme_meta=get_theme_meta(config.get("theme", "minimal")),
                critical_css="",
                config_description=config.get("description", ""),
                base_url=config.get("base_url"),
                feed_url="feed.xml",
                lang=config.get("lang") or "en",
            )
        raise RuntimeError(
            f"No .md files found in '{config['docs']}'. Nothing to build."
        )

    # Detect project name and version
    project_name = os.path.basename(os.path.abspath(dir_path))
    version = version_override if version_override is not None else detect_project_version(dir_path)

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
    url_builder = SimpleURLBuilder(base_url) if base_url else None

    # Get lang attribute for HTML pages (default "en").
    # When multiple locales are configured, the locale code is the
    # authoritative language tag. For single-locale projects, the
    # config "lang" field takes precedence (backward compat).
    lang = config.get("lang") or "en"
    if locale_override is not None and available_locales and len(available_locales) > 1:
        lang = locale_override

    # Get author from config for JSON-LD structured data
    author = config.get("author")

    # Get project-level description from config
    config_description = config.get("description", "")

    # Atom feed link in HTML <head>
    feed_url = "feed.xml"

    # Load theme CSS and metadata
    theme_name = config.get("theme", "minimal")
    raw_theme_css = get_css(theme_name)
    theme_meta = get_theme_meta(theme_name)

    # Extract critical CSS from raw theme (before minification) for inlining
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
        url_builder=url_builder,
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
        auto_detect=config.get("auto_detect"),
        theme_meta=theme_meta,
        deploy_target=(config.get("deploy") or {}).get("provider"),
        run_button=config.get("run_button", False),
        line_numbers=config.get("line_numbers", False),
        page_nav=config.get("page_nav", True),
        page_progress=config.get("page_progress", True),
        code_icons=config.get("code_icons", "colorful"),
        glossary=config.get("glossary", True),
        url_prefix=url_prefix,
        available_versions=available_versions,
        available_locales=available_locales,
        current_version=current_version,
        current_locale=current_locale,
        is_latest=is_latest,
    )

    # Post-process HTML pages: add image dimensions from file inspection
    # (Phase 3.3). Convert html_path keys back to md_path for lookup.
    for html_path in list(html_files):
        md_path = _html_to_md_path(html_path)
        html_files[html_path] = _add_image_dimensions(
            html_files[html_path], docs_dir, md_path,
        )

    # Prefix html_files keys with output_subdir so callers write under
    # the versioned/localized subdirectory (e.g. "en/1.0.0/index.html")
    if output_subdir:
        html_files = {
            f"{output_subdir}/{k}": v for k, v in html_files.items()
        }

    # Build nav items (used by search index and auxiliary files)
    nav_items = _build_nav(markdown_files, frontmatter)

    # Build search index entries (returned to caller for accumulation)
    search_entries = _build_search_index(
        markdown_files,
        version=version,
        locale=locale_override or "",
        target="",
        project=project_name,
        frontmatter=frontmatter,
        nav_items=nav_items,
    )

    return BuildResult(
        html_files=html_files,
        markdown_files=markdown_files,
        frontmatter=frontmatter,
        page_dates=page_dates,
        nav_items=nav_items,
        search_entries=search_entries,
        project_name=project_name,
        version=version,
        config=config,
        docs_dir=docs_dir,
        other_files=other_files,
        has_custom_css=has_custom_css,
        raw_theme_css=raw_theme_css,
        theme_meta=theme_meta,
        critical_css=critical_css,
        config_description=config_description,
        base_url=base_url,
        feed_url=feed_url,
        lang=lang,
    )


def _resolve_locale_docs_dir(dir_path, docs_dir_name, locale_code, locales):
    """Resolve the docs directory for a locale.

    For backward compatibility: if there's exactly one locale and
    ``docs/{code}/`` doesn't exist, fall back to ``docs/`` directly
    (single-locale projects don't need locale subdirectories).

    For multi-locale projects: ``docs/{locale_code}/`` must exist.

    Returns the resolved docs directory path.
    Raises RuntimeError if the directory doesn't exist and fallback
    is not applicable.
    """
    locale_docs = os.path.join(dir_path, docs_dir_name, locale_code)
    if os.path.isdir(locale_docs):
        return locale_docs

    # Single-locale fallback: use docs/ directly if locale subdir missing
    if len(locales) == 1:
        plain_docs = os.path.join(dir_path, docs_dir_name)
        if os.path.isdir(plain_docs):
            # Check that plain_docs has .md files (not just an empty dir)
            has_md = any(f.endswith(".md") for f in os.listdir(plain_docs)
                        if os.path.isfile(os.path.join(plain_docs, f)))
            if has_md:
                return plain_docs

    raise RuntimeError(
        f"Locale directory '{docs_dir_name}/{locale_code}/' not found. "
        f"Create it with .md files for locale '{locale_code}'."
    )


def _partition_pages(config, docs_dir, dir_path):
    """Partition markdown pages into versioned and unversioned sets.

    Resolves all docs once and checks frontmatter for ``versioned: false``.
    Pages without the key (or with ``versioned: true``) are versioned by default.

    Returns (versioned_paths, unversioned_paths) where each is a set of
    relative md paths.
    """
    all_docs = resolve_all_docs(config, docs_dir=docs_dir, base_dir=dir_path)
    versioned = set()
    unversioned = set()
    for rel_path, (fm, _resolved, _raw, _lc) in all_docs.items():
        if fm and fm.get("versioned") is False:
            unversioned.add(rel_path)
        else:
            versioned.add(rel_path)
    return versioned, unversioned


def _check_unversioned_collisions(unversioned_paths, version_strs):
    """Verify no unversioned page output path collides with versioned paths.

    Unversioned pages output to ``/{locale}/{page_path}/`` (no version segment).
    If an unversioned page lives in a directory whose name matches a version
    string, its output would collide with versioned pages in that version.

    Raises RuntimeError on collision.
    """
    version_set = set(version_strs)
    for uv_path in unversioned_paths:
        parts = uv_path.split("/")
        if len(parts) > 1 and parts[0] in version_set:
            raise RuntimeError(
                f"Unversioned page '{uv_path}' would collide with versioned "
                f"output under version '{parts[0]}'. Rename the page or remove "
                f"'versioned: false' from its frontmatter."
            )


def _check_reserved_paths(version_strs, config):
    """Verify version strings do not clash with reserved URL prefixes.

    Currently the only reserved prefix is the posts listing path
    (default ``posts``).  Raises RuntimeError on conflict.
    """
    reserved = set()
    posts_config = config.get("posts")
    if posts_config:
        listing_path = posts_config.get("listing_path", "posts")
        reserved.add(listing_path)
    # Future reserved prefixes can be added here

    for ver_str in version_strs:
        if ver_str in reserved:
            raise RuntimeError(
                f"Version string '{ver_str}' conflicts with reserved URL "
                f"prefix. Reserved prefixes: {', '.join(sorted(reserved))}. "
                f"Rename the version or change the conflicting config."
            )


def build(dir_path=".", config=None, version_filter=None, locale_filter=None):
    """Build docs from templates + directives, with multi-locale/multi-version support.

    Outer loop iterates locales, inner loop iterates versions. For each
    locale/version combination, builds HTML from either the working tree
    (latest version) or git archive extraction (older versions). All
    search entries are merged into a single index. Auxiliary files (OG
    cards, sitemap, feed, etc.) use the latest version's data only.

    Args:
        dir_path: Project root directory.
        config: Pre-loaded config dict (if None, loads from selfdoc.json).
        version_filter: Optional version string to build only that version.
        locale_filter: Optional locale code to build only that locale.

    Returns:
        Dict of {output_path: True} for files written.
    """
    if config is None:
        config = load_config(dir_path)
    if config is None:
        raise RuntimeError(
            "No selfdoc.json found. Run 'selfdoc init' to initialize."
        )

    if config.get("versions") is None:
        raise ConfigError(
            "selfdoc.json requires 'versions' array. "
            "Add: \"versions\": [{\"version\": \"1.0.0\", \"indexed\": true}]"
        )
    if config.get("locales") is None:
        raise ConfigError(
            "selfdoc.json requires 'locales' array. "
            "Add: \"locales\": [{\"code\": \"en\", \"label\": \"English\", "
            "\"default\": true}]"
        )

    locales = config.get("locales", [])
    versions = config.get("versions", [])
    default_locale = locales[0]
    for loc in locales:
        if loc.get("default") is True:
            default_locale = loc
            break
    default_locale_code = default_locale["code"]
    latest_version = versions[-1]["version"]

    # Filter versions if --version flag was given
    if version_filter:
        matching = [v for v in versions if v["version"] == version_filter]
        if not matching:
            raise RuntimeError(
                f"Version '{version_filter}' not found in config. "
                f"Available: {', '.join(v['version'] for v in versions)}"
            )
        build_versions = matching
    else:
        build_versions = versions

    # Filter locales if --locale flag was given
    if locale_filter:
        matching_locales = [loc for loc in locales if loc["code"] == locale_filter]
        if not matching_locales:
            raise RuntimeError(
                f"Locale '{locale_filter}' not found in config. "
                f"Available: {', '.join(loc['code'] for loc in locales)}"
            )
        build_locales = matching_locales
    else:
        build_locales = locales

    output_dir = os.path.join(dir_path, config["output"].rstrip("/"))

    # Validate docs directory exists before touching output (creating
    # output_dir could implicitly create the docs parent directory,
    # masking a missing docs/ error).
    docs_dir_name = config["docs"].rstrip("/")
    docs_dir_check = os.path.join(dir_path, docs_dir_name)
    if not os.path.isdir(docs_dir_check):
        raise RuntimeError(
            f"Docs directory '{config['docs']}' not found. "
            "Create it or run 'selfdoc init'."
        )

    # Clean output directory
    if os.path.exists(output_dir):
        shutil.rmtree(output_dir)
    os.makedirs(output_dir, exist_ok=True)

    # --- Partition pages into versioned and unversioned ---
    version_strs = [v["version"] for v in versions]
    _check_reserved_paths(version_strs, config)

    # Resolve docs from the latest (working tree) to discover unversioned pages
    latest_docs_dir = os.path.join(dir_path, docs_dir_name)
    versioned_pages, unversioned_pages = _partition_pages(config, latest_docs_dir, dir_path)

    # Check for collisions between unversioned output paths and version strings
    _check_unversioned_collisions(unversioned_pages, version_strs)

    written = {}
    all_search_entries = []
    latest_build = None
    # Track per-locale indexed HTML paths for per-locale sitemaps
    per_locale_indexed_html = {}  # locale_code -> list of html rel paths

    # Multi-locale / multi-version build loop (locales = outer, versions = inner)
    for locale in build_locales:
        locale_code = locale["code"]
        per_locale_indexed_html[locale_code] = []

        for ver_entry in build_versions:
            ver_str = ver_entry["version"]
            is_latest = (ver_str == latest_version)
            output_subdir = f"{locale_code}/{ver_str}"
            url_prefix = output_subdir

            if is_latest:
                build_dir = dir_path
            else:
                build_dir = _extract_version_content(ver_str, config, dir_path)

            # Resolve locale-specific docs directory
            locale_docs_dir = _resolve_locale_docs_dir(
                build_dir, docs_dir_name, locale_code, locales,
            )

            # Build a locale-aware config copy pointing to the locale docs dir
            locale_config = dict(config)
            locale_config["docs"] = os.path.relpath(locale_docs_dir, build_dir)

            result = build_single(
                dir_path=build_dir,
                config=locale_config,
                output_subdir=output_subdir,
                url_prefix=url_prefix,
                version_override=ver_str,
                locale_override=locale_code,
                available_versions=versions,
                available_locales=locales,
                current_version=ver_str,
                current_locale=locale_code,
                is_latest=is_latest,
                page_filter=versioned_pages if unversioned_pages else None,
            )
            html_files = result.html_files
            markdown_files = result.markdown_files
            frontmatter = result.frontmatter
            page_dates = result.page_dates
            nav_items = result.nav_items
            search_entries = result.search_entries
            project_name = result.project_name
            version = result.version
            docs_dir = result.docs_dir
            other_files = result.other_files
            has_custom_css = result.has_custom_css
            raw_theme_css = result.raw_theme_css
            theme_meta = result.theme_meta
            critical_css = result.critical_css
            config_description = result.config_description
            base_url = result.base_url
            feed_url = result.feed_url
            lang = result.lang

            all_search_entries.extend(search_entries)

            for rel_path, html_content in html_files.items():
                out_path = os.path.join(output_dir, rel_path)
                os.makedirs(os.path.dirname(out_path), exist_ok=True)
                with open(out_path, "w", encoding="utf-8") as f:
                    f.write(_minify_html(html_content))
                written[out_path] = True

            for rel_path in other_files:
                src = os.path.join(docs_dir, rel_path)
                dst = os.path.join(output_dir, output_subdir, rel_path)
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.copy2(src, dst)
                written[dst] = True

            # Collect indexed HTML paths for per-locale sitemaps
            if ver_entry.get("indexed", True):
                ver_prefix = os.path.join(output_dir, f"{locale_code}/{ver_str}")
                for k in written:
                    if k.startswith(ver_prefix) and k.endswith(".html"):
                        rel = os.path.relpath(k, output_dir)
                        if rel not in per_locale_indexed_html[locale_code]:
                            per_locale_indexed_html[locale_code].append(rel)

            if is_latest and locale_code == default_locale_code:
                latest_build = {
                    "html_files": html_files,
                    "markdown_files": markdown_files,
                    "frontmatter": frontmatter,
                    "page_dates": page_dates,
                    "project_name": project_name,
                    "version": version,
                    "docs_dir": docs_dir,
                    "has_custom_css": has_custom_css,
                    "raw_theme_css": raw_theme_css,
                    "theme_meta": theme_meta,
                    "critical_css": critical_css,
                    "config_description": config_description,
                    "base_url": base_url,
                    "url_builder": SimpleURLBuilder(base_url) if base_url else None,
                    "feed_url": feed_url,
                    "lang": lang,
                }

    # Fallback: if version_filter excluded the latest, use the last build
    if latest_build is None:
        latest_build = {
            "html_files": html_files,
            "markdown_files": markdown_files,
            "frontmatter": frontmatter,
            "page_dates": page_dates,
            "project_name": project_name,
            "version": version,
            "docs_dir": docs_dir,
            "has_custom_css": has_custom_css,
            "raw_theme_css": raw_theme_css,
            "theme_meta": theme_meta,
            "critical_css": critical_css,
            "config_description": config_description,
            "base_url": base_url,
            "url_builder": SimpleURLBuilder(base_url) if base_url else None,
            "feed_url": feed_url,
            "lang": lang,
        }

    # --- Build unversioned pages (once per locale, no version segment) ---
    uv_latest_build = None
    if unversioned_pages:
        for locale in build_locales:
            locale_code = locale["code"]
            # Unversioned pages output to /{locale}/page/ (no version)
            uv_output_subdir = locale_code
            uv_url_prefix = locale_code

            # Resolve locale-specific docs directory
            locale_docs_dir = _resolve_locale_docs_dir(
                dir_path, docs_dir_name, locale_code, locales,
            )
            locale_config = dict(config)
            locale_config["docs"] = os.path.relpath(locale_docs_dir, dir_path)

            uv_result = build_single(
                dir_path=dir_path,
                config=locale_config,
                output_subdir=uv_output_subdir,
                url_prefix=uv_url_prefix,
                version_override="",
                locale_override=locale_code,
                available_versions=versions,
                available_locales=locales,
                current_version="",
                current_locale=locale_code,
                is_latest=True,
                page_filter=unversioned_pages,
            )

            all_search_entries.extend(uv_result.search_entries)

            for rel_path, html_content in uv_result.html_files.items():
                out_path = os.path.join(output_dir, rel_path)
                os.makedirs(os.path.dirname(out_path), exist_ok=True)
                with open(out_path, "w", encoding="utf-8") as f:
                    f.write(_minify_html(html_content))
                written[out_path] = True

            for rel_path in uv_result.other_files:
                src = os.path.join(uv_result.docs_dir, rel_path)
                dst = os.path.join(output_dir, uv_output_subdir, rel_path)
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.copy2(src, dst)
                written[dst] = True

            # Add to per-locale indexed HTML
            uv_prefix = os.path.join(output_dir, locale_code)
            for k in written:
                if k.startswith(uv_prefix) and k.endswith(".html"):
                    rel = os.path.relpath(k, output_dir)
                    if rel not in per_locale_indexed_html[locale_code]:
                        per_locale_indexed_html[locale_code].append(rel)

            if locale_code == default_locale_code:
                uv_latest_build = {
                    "markdown_files": uv_result.markdown_files,
                    "frontmatter": uv_result.frontmatter,
                    "page_dates": uv_result.page_dates,
                }

    # Merge unversioned data into latest_build for auxiliary files
    if uv_latest_build and latest_build:
        latest_build["markdown_files"] = {
            **latest_build["markdown_files"],
            **uv_latest_build["markdown_files"],
        }
        latest_build["frontmatter"] = {
            **latest_build["frontmatter"],
            **uv_latest_build["frontmatter"],
        }
        latest_build["page_dates"] = {
            **latest_build["page_dates"],
            **uv_latest_build["page_dates"],
        }

    lb = latest_build
    theme_meta = lb["theme_meta"]

    # Shared assets: CSS
    css_path = os.path.join(output_dir, "style.css")
    theme_css = lb["raw_theme_css"]
    pygments_css = generate_pygments_css(
        light_style=theme_meta.get("pygments_light", "default"),
        dark_style=theme_meta.get("pygments_dark", "monokai"),
    )
    if pygments_css:
        theme_css = theme_css + "\n\n/* Pygments syntax highlighting */\n" + pygments_css
    theme_css = _minify_css(theme_css)
    with open(css_path, "w", encoding="utf-8") as f:
        f.write(theme_css)
    written[css_path] = True

    # Combined search index from ALL versions and locales
    search_index_path = os.path.join(output_dir, "search-index.json")
    with open(search_index_path, "w", encoding="utf-8") as f:
        json.dump(
            [dataclasses.asdict(entry) for entry in all_search_entries],
            f, ensure_ascii=False,
        )
    written[search_index_path] = True

    # Search JS
    search_engine = config.get("search_engine") or "builtin"
    search_js_path = os.path.join(output_dir, "search.js")
    with open(search_js_path, "w", encoding="utf-8") as f:
        f.write(_minify_js(_generate_search_js(engine=search_engine)))
    written[search_js_path] = True

    # Custom CSS
    custom_css_src = os.path.join(lb["docs_dir"], "custom.css")
    if lb["has_custom_css"]:
        custom_css_dst = os.path.join(output_dir, "custom.css")
        shutil.copy2(custom_css_src, custom_css_dst)
        written[custom_css_dst] = True

    # Auxiliary files using latest version data only
    # Collect all indexed HTML paths across all locales for the root sitemap
    all_indexed_html_paths = []
    for locale_paths in per_locale_indexed_html.values():
        all_indexed_html_paths.extend(locale_paths)

    repo = config.get("repo", None)
    has_sitemap_index = len(build_locales) > 1
    aux_written = _generate_auxiliary_files(
        output_dir=output_dir,
        project_name=lb["project_name"],
        version=lb["version"],
        markdown_files=lb["markdown_files"],
        html_paths=all_indexed_html_paths,
        base_url=lb["base_url"],
        has_custom_css=lb["has_custom_css"],
        repo=repo,
        lang=lb["lang"],
        page_dates=lb["page_dates"],
        frontmatter=lb["frontmatter"],
        description=lb["config_description"],
        feed_url=lb["feed_url"],
        critical_css=lb["critical_css"],
        accent_color=theme_meta["accent_color"],
        theme_meta=theme_meta,
        deploy=config.get("deploy"),
        feed_max_entries=config.get("feed_max_entries"),
        has_sitemap_index=has_sitemap_index,
        url_builder=lb["url_builder"],
    )
    written.update(aux_written)

    # Per-locale sitemaps + sitemap-index (when multiple locales)
    if len(build_locales) > 1:
        locale_sitemap_paths = _generate_per_locale_sitemaps(
            output_dir=output_dir,
            base_url=lb["base_url"],
            per_locale_indexed_html=per_locale_indexed_html,
            page_dates=lb["page_dates"],
            url_builder=lb["url_builder"],
        )
        for sp in locale_sitemap_paths:
            written[sp] = True

        sitemap_index_path = _generate_sitemap_index(
            output_dir=output_dir,
            base_url=lb["base_url"],
            locale_codes=list(per_locale_indexed_html.keys()),
            url_builder=lb["url_builder"],
        )
        written[sitemap_index_path] = True

    # Root redirect to default locale / latest version
    latest_prefix = f"{default_locale_code}/{latest_version}"
    redirect_url = f"/{latest_prefix}/"
    root_index_html = (
        "<!DOCTYPE html>\n"
        "<html>\n"
        "<head>\n"
        f'  <meta http-equiv="refresh" content="0;url={redirect_url}">\n'
        f'  <link rel="canonical" href="{redirect_url}">\n'
        "</head>\n"
        "<body>\n"
        f'  <script>window.location.replace("{redirect_url}")</script>\n'
        f'  <p>Redirecting to <a href="{redirect_url}">{redirect_url}</a></p>\n'
        "</body>\n"
        "</html>\n"
    )
    root_index_path = os.path.join(output_dir, "index.html")
    with open(root_index_path, "w", encoding="utf-8") as f:
        f.write(root_index_html)
    written[root_index_path] = True

    redirects_content = f"/ {redirect_url} 302\n"
    redirects_path = os.path.join(output_dir, "_redirects")
    with open(redirects_path, "w", encoding="utf-8") as f:
        f.write(redirects_content)
    written[redirects_path] = True

    # Config-driven page redirects (expanded across all locale/version combos)
    config_redirects = config.get("redirects") or []
    if config_redirects:
        redirect_count = 0
        for redirect_entry in config_redirects:
            from_slug = redirect_entry["from"]
            to_slug = redirect_entry["to"]
            for locale in build_locales:
                locale_code = locale["code"]
                for ver_entry in build_versions:
                    ver_str = ver_entry["version"]
                    old_path = os.path.join(
                        output_dir, locale_code, ver_str,
                        from_slug, "index.html",
                    )
                    # Skip if the page already exists (e.g. cached old-version page)
                    if os.path.exists(old_path):
                        continue
                    # Target URL for the redirect
                    target_url = f"/{locale_code}/{ver_str}/{to_slug}/"
                    # Generate HTML meta-refresh page
                    meta_html = (
                        "<!DOCTYPE html>\n"
                        "<html>\n"
                        "<head>\n"
                        f'  <meta http-equiv="refresh" content="0;url={target_url}">\n'
                        f'  <link rel="canonical" href="{target_url}">\n'
                        "</head>\n"
                        "<body>\n"
                        f'  <script>window.location.replace("{target_url}")</script>\n'
                        f'  <p>Redirecting to <a href="{target_url}">{target_url}</a></p>\n'
                        "</body>\n"
                        "</html>\n"
                    )
                    os.makedirs(os.path.dirname(old_path), exist_ok=True)
                    with open(old_path, "w", encoding="utf-8") as f:
                        f.write(meta_html)
                    written[old_path] = True
                    # Append Cloudflare _redirects rule
                    with open(redirects_path, "a", encoding="utf-8") as f:
                        f.write(
                            f"/{locale_code}/{ver_str}/{from_slug}/ "
                            f"{target_url} 301\n"
                        )
                    redirect_count += 1
        if redirect_count:
            print(f"Generated {redirect_count} redirect(s)")

    # Pre-compress
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
    accent_color="#0969da", theme_meta=None, deploy=None,
    feed_max_entries=None, has_sitemap_index=False, url_builder=None,
):
    """Generate auxiliary build artifacts (OG cards, sitemap, llms.txt, 404, favicon, feed).

    Called by build() after the main HTML pages and static files are written.
    Returns a dict of {output_path: True} for files written.
    """
    if url_builder is None and base_url is not None:
        url_builder = SimpleURLBuilder(base_url)
    written = {}

    # Generate OG social card PNGs (Feature 21)
    for md_path, content in markdown_files.items():
        slug = md_path.replace(".md", "") if md_path.endswith(".md") else md_path
        page_title = _extract_title(content, slug)
        png_bytes = _generate_og_png(project_name, page_title, accent_color)
        png_path = os.path.join(output_dir, f"og-{slug}.png")
        os.makedirs(os.path.dirname(png_path), exist_ok=True)
        with open(png_path, "wb") as f:
            f.write(png_bytes)
        written[png_path] = True

    # Generate sitemap.xml (Feature 22)
    sitemap_content = _generate_sitemap(base_url, html_paths, page_dates,
                                        url_builder=url_builder)
    sitemap_path = os.path.join(output_dir, "sitemap.xml")
    with open(sitemap_path, "w", encoding="utf-8") as f:
        f.write(sitemap_content)
    written[sitemap_path] = True

    # Generate llms.txt and llms-full.txt (Feature 24)
    llms_txt = _generate_llms_txt(project_name, markdown_files, base_url,
                                  url_builder=url_builder)
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
        feed_max_entries=feed_max_entries,
        url_builder=url_builder,
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
        url_builder=url_builder,
        lang=lang,
        feed_url=feed_url,
        critical_css=critical_css,
        theme_meta=theme_meta,
    )
    not_found_path = os.path.join(output_dir, "404.html")
    with open(not_found_path, "w", encoding="utf-8") as f:
        f.write(not_found_html)
    written[not_found_path] = True

    # Generate favicon.svg from project initials (Feature 40)
    favicon_svg = _generate_favicon_svg(project_name, accent_color)
    favicon_path = os.path.join(output_dir, "favicon.svg")
    with open(favicon_path, "w", encoding="utf-8") as f:
        f.write(favicon_svg)
    written[favicon_path] = True

    # Generate robots.txt (allow all crawlers including AI bots)
    robots_path = _generate_robots_txt(output_dir, base_url, has_sitemap_index,
                                       url_builder=url_builder)
    written[robots_path] = True

    # Generate _headers only for Cloudflare Pages deploy target
    deploy_provider = (deploy or {}).get("provider")
    if deploy_provider == "cloudflare-pages":
        headers_path = _generate_headers(output_dir)
        written[headers_path] = True

    # _redirects no longer needed: directory-index URLs work without
    # trailing-slash redirects on all hosting platforms.

    return written


def _generate_robots_txt(output_dir, base_url, has_sitemap_index=False, url_builder=None):
    """Generate robots.txt allowing all crawlers including AI bots.

    When ``has_sitemap_index`` is True, references ``sitemap-index.xml``
    instead of ``sitemap.xml``.
    """
    if url_builder is None and base_url is not None:
        url_builder = SimpleURLBuilder(base_url)
    sitemap_file = "sitemap-index.xml" if has_sitemap_index else "sitemap.xml"
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
        f"Sitemap: {url_builder.asset_url(sitemap_file) if url_builder else f'{base_url}/{sitemap_file}'}",
    ]
    content = "\n".join(lines) + "\n"
    path = os.path.join(output_dir, "robots.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path


def _generate_per_locale_sitemaps(output_dir, base_url, per_locale_indexed_html,
                                  page_dates=None, url_builder=None):
    """Generate per-locale sitemap.xml files at output_dir/{locale}/sitemap.xml.

    Returns a list of written file paths.
    """
    if url_builder is None and base_url is not None:
        url_builder = SimpleURLBuilder(base_url)
    written = []
    for locale_code, html_paths in per_locale_indexed_html.items():
        sitemap_content = _generate_sitemap(base_url, html_paths, page_dates,
                                            url_builder=url_builder)
        locale_dir = os.path.join(output_dir, locale_code)
        os.makedirs(locale_dir, exist_ok=True)
        sitemap_path = os.path.join(locale_dir, "sitemap.xml")
        with open(sitemap_path, "w", encoding="utf-8") as f:
            f.write(sitemap_content)
        written.append(sitemap_path)
    return written


def _generate_sitemap_index(output_dir, base_url, locale_codes, url_builder=None):
    """Generate sitemap-index.xml at the output root listing per-locale sitemaps.

    Returns the written file path.
    """
    if url_builder is None and base_url is not None:
        url_builder = SimpleURLBuilder(base_url)
    entries = []
    for code in sorted(locale_codes):
        loc_url = (url_builder.asset_url(f"{code}/sitemap.xml")
                   if url_builder else f"{base_url}/{code}/sitemap.xml")
        entries.append(
            f"  <sitemap><loc>{loc_url}</loc></sitemap>"
        )
    content = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "\n".join(entries)
        + "\n</sitemapindex>\n"
    )
    path = os.path.join(output_dir, "sitemap-index.xml")
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


def _generate_favicon_svg(project_name, accent_color="#0969da"):
    """Generate a simple SVG favicon from the project name's initial (Feature 40).

    Uses the first letter (uppercase) of the project name, with the accent
    color as the background.
    """
    initial = project_name[0].upper() if project_name else "D"
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">'
        f'<rect width="32" height="32" rx="4" fill="{accent_color}"/>'
        f'<text x="16" y="22" text-anchor="middle" fill="white" '
        f'font-family="system-ui" font-size="18" font-weight="700">'
        f'{_escape_html(initial)}</text>'
        '</svg>'
    )
