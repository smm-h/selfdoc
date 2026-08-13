"""Build pipeline for selfdoc: template scanning, directive resolution, HTML output."""

from dataclasses import dataclass
import gzip
import io
import os
import posixpath
import re
import struct
import subprocess
import sys
import tempfile
import time
import zlib
from datetime import datetime

from selfdoc_core import require_post_provider
from selfdoc_core.config import load_config, ConfigError
from selfdoc_core.address import (
    ARCHIVE_PREFIX, POSTS_PREFIX, locale_segment, page_address,
)
from selfdoc_core.prose import first_paragraph
from selfdoc_core.docs import resolve_all_docs
from selfdoc_core.utils import detect_project_version, parse_frontmatter
from selfdoc_core.html import (
    generate_html, generate_404_page, get_css, generate_pygments_css,
    _md_to_html_path, _html_to_md_path,
    _extract_title, _escape_html, _build_nav,
)
from selfdoc_core.themes import get_theme_meta, list_themes
from selfdoc_core.urls import SimpleURLBuilder, TopologyURLBuilder

from selfdoc_core import effects

try:
    from predraw.model import Scene, Element, Font
    from predraw.renderer import render_svg
    import cairosvg
    _HAS_PREDRAW = True
except ImportError:
    _HAS_PREDRAW = False


def _make_url_builder(config):
    """Create the appropriate URLBuilder based on config.

    When topology config has docs_base and slug, returns a
    TopologyURLBuilder. Otherwise falls back to SimpleURLBuilder
    using base_url.
    """
    topology = config.get("topology") or {}
    docs_base = topology.get("docs_base")
    slug = topology.get("slug")
    if docs_base and slug:
        return TopologyURLBuilder(
            docs_base=docs_base,
            slug=slug,
            projects=topology.get("projects"),
        )
    base_url = config.get("base_url")
    if base_url:
        return SimpleURLBuilder(base_url)
    return None


@dataclass(frozen=True, slots=True)
class BuildResult:
    """Result of build_single() -- all outputs needed by callers."""

    html_files: dict
    markdown_files: dict
    frontmatter: dict
    page_dates: dict
    nav_items: list
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
    effects.makedirs(cache_root, exist_ok=True)
    gitignore_path = os.path.join(cache_root, ".gitignore")
    if not os.path.isfile(gitignore_path):
        with effects.open_write(gitignore_path, "w", encoding="utf-8") as f:
            f.write("*\n")

    # Determine tag name
    tag_name = None
    for candidate in (f"v{version}", version):
        result = effects.run(
            ["git", "rev-parse", f"refs/tags/{candidate}"],
            capture_output=True, text=True, timeout=10,
            cwd=base_dir, read=True,
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
    result = effects.run(
        ["git", "rev-parse", f"{tag_name}^{{commit}}"],
        capture_output=True, text=True, timeout=10,
        cwd=base_dir, read=True,
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
        effects.rmtree(cache_dir)
    effects.makedirs(cache_dir, exist_ok=True)

    # Determine paths to extract: docs dir + source dirs
    docs_path = config["docs"].rstrip("/")
    from selfdoc_core.extractors import source_paths as _source_paths

    raw_source_paths = _source_paths(config) if config.get("source") else []
    archive_paths = [docs_path] + [s.rstrip("/") for s in raw_source_paths]

    # Run git archive piped into tar
    git_cmd = ["git", "archive", tag_name] + archive_paths
    tar_cmd = ["tar", "-x", "-C", cache_dir]

    outcome = effects.pipeline(git_cmd, tar_cmd, cwd=base_dir, timeout=30)
    if effects.unsettled(outcome):
        # Recorded, not extracted. The sentinel is recorded too so the
        # preview names every path this cache fill would create.
        effects.write_text(hash_file, commit_hash + "\n")
        return cache_dir
    returncode, tar_err = outcome
    if returncode != 0:
        raise RuntimeError(
            f"tag archive extraction failed for tag '{tag_name}': "
            f"{tar_err.decode().strip()}"
        )

    # Write hash sentinel
    effects.write_text(hash_file, commit_hash + "\n")

    return cache_dir


def _run_pagefind(output_dir):
    """Run Pagefind to generate the search index for the output directory.

    Tries the Python module first (python3 -m pagefind), then the standalone
    binary.  Raises RuntimeError if neither is available.
    """
    # Try Python module first, then standalone binary
    for cmd in (
        [sys.executable, "-m", "pagefind", "--site", output_dir],
        ["pagefind", "--site", output_dir],
    ):
        try:
            result = effects.run(
                cmd, capture_output=True, text=True, timeout=120,
                resource=f"pagefind:{output_dir}",
            )
            if effects.unsettled(result):
                return
            if result.returncode == 0:
                return
            # Command found but failed -- report the error
            raise RuntimeError(
                f"Pagefind indexing failed (exit {result.returncode}):\n"
                f"{result.stderr.strip()}"
            )
        except FileNotFoundError:
            continue
        except subprocess.TimeoutExpired:
            raise RuntimeError(
                "Pagefind indexing timed out after 120 seconds."
            )

    raise RuntimeError(
        "Pagefind is not installed. Install it with: uv add pagefind\n"
        "Or install the standalone binary: npm install -g pagefind"
    )


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
        fd, tmp_path = tempfile.mkstemp(suffix=".png")  # effects: exempt -- self-owned scratch file, created, read back and deleted inside this call
        os.close(fd)
        try:
            _generate_og_png_rich(project_name, title, accent_color, tmp_path)
            with open(tmp_path, "rb") as f:
                return f.read()
        finally:
            try:
                os.unlink(tmp_path)  # effects: exempt -- removes this call's own scratch file
            except OSError:
                pass
    else:
        return _generate_og_png_basic(accent_color)


def _output_key_to_url(output_key):
    """URL path for an emitted HTML file, keyed from the output root.

    The directory-index form the addressing authority produces, applied to
    a full output key: ``index.html`` is the site root (``""``) and
    ``guide/index.html`` is ``guide/``.  A sitemap entry and a canonical
    link therefore name the same URL, which they did not while the sitemap
    spelled the home page ``index.html``.
    """
    if output_key == "index.html":
        return ""
    if output_key.endswith("/index.html"):
        return output_key[: -len("index.html")]
    return output_key


def _generate_sitemap(html_paths, url_builder, page_dates=None):
    """Generate a sitemap.xml string for the given HTML paths.

    Args:
        html_paths: List of HTML file paths (e.g. ["index.html", "guide.html"]).
        url_builder: URLBuilder for constructing URLs.
        page_dates: Optional dict mapping md paths to (published, modified) tuples.
    """
    if page_dates is None:
        page_dates = {}
    urls = []
    for path in sorted(html_paths):
        # Convert html path to md path for date lookup.
        # html_paths may include a locale/version prefix (e.g. "en/1.0.0/guide/index.html")
        # while page_dates is keyed by unprefixed md_path (e.g. "guide.md").
        md_path = _html_to_md_path(path)
        url = _output_key_to_url(path)
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
        full_url = url_builder.page_url(url)
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


def _first_content_paragraph(content):
    """Return the first prose paragraph of markdown *content* as one line.

    Skips leading headings, blank lines, and fenced code blocks, then
    returns the whole first paragraph via :func:`first_paragraph` (soft-
    wrapped physical lines joined). llms.txt and Atom-feed summaries carry
    the complete first paragraph -- no character cap, no ellipsis.
    """
    prose_lines = []
    in_fence = False
    for line in content.split("\n"):
        stripped = line.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if stripped.startswith("#"):
            continue
        if not stripped:
            if prose_lines:
                break
            continue
        prose_lines.append(stripped)
    return first_paragraph("\n".join(prose_lines))


def _generate_llms_txt(project_name, markdown_files, url_builder,
                       page_addresses):
    """Generate llms.txt (brief index) content.

    Lists each page with its title and first sentence.

    Args:
        page_addresses: md_path -> PageAddress for every page listed.
            Required: a page's absolute URL is its mounted address, and
            this function has no way to work one out on its own.
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
        url_path = page_addresses[md_path].stable

        # Summary is the complete first paragraph of the page.
        first = _first_content_paragraph(content)

        url = url_builder.page_url(url_path)
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


def _make_feed_entry(title, url, date, summary="", page_type=""):
    """Create a single Atom feed entry XML string.

    Takes abstract page metadata (not raw markdown) for reuse across
    different feed generators (per-project and unified assembly).

    Args:
        title: Page title (will be XML-escaped).
        url: Full page URL.
        date: ISO date string (YYYY-MM-DD).
        summary: Optional summary text (will be XML-escaped).
        page_type: Optional page type (reserved for Phase 3 type-aware ordering).

    Returns:
        Tuple of (date, entry_xml) for sorting by date.
    """
    escaped_title = _escape_html(title)
    escaped_summary = _escape_html(summary) if summary else ""
    entry = (
        f"  <entry>\n"
        f"    <title>{escaped_title}</title>\n"
        f'    <link href="{url}"/>\n'
        f"    <id>{url}</id>\n"
        f"    <updated>{date}T00:00:00Z</updated>\n"
    )
    if escaped_summary:
        entry += f"    <summary>{escaped_summary}</summary>\n"
    entry += "  </entry>"
    return (date, entry)


def _generate_atom_feed(
    output_dir, base_url, project_name, description,
    markdown_files, frontmatter, page_dates,
    url_builder, page_addresses, feed_max_entries=None,
):
    """Generate an Atom feed (feed.xml) for the documentation site.

    Args:
        page_addresses: md_path -> PageAddress for every page in the feed.
            Required: an entry's link and id are its mounted address.

    Returns the path written.
    """
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

        url_path = page_addresses[md_path].stable
        title = meta.get("title")
        if not title:
            title = _extract_title(content, md_path.replace(".md", ""))

        # Summary is the complete first paragraph of the page.
        summary = _first_content_paragraph(content)

        # Posts use their publication date (frontmatter date field);
        # docs use the modification date from page_dates.
        page_type = meta.get("type", "")
        if page_type == "post" and meta.get("date"):
            page_date = str(meta["date"])
        else:
            date_tuple = page_dates.get(md_path)
            page_date = date_tuple[1] if date_tuple else ""

        page_full_url = url_builder.page_url(url_path)

        entries.append(_make_feed_entry(
            title=title,
            url=page_full_url,
            date=page_date,
            summary=summary,
            page_type=page_type,
        ))

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

    feed_self_url = url_builder.feed_url()
    feed_home_url = url_builder.page_url("")
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
    with effects.open_write(feed_path, "w", encoding="utf-8") as f:
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
            gz_buf = io.BytesIO()
            with gzip.GzipFile(
                fileobj=gz_buf, mode="wb", compresslevel=9,
            ) as gz_f:
                gz_f.write(data)
            effects.write_bytes(gz_path, gz_buf.getvalue())

            # brotli companion (optional)
            if has_brotli:
                br_path = filepath + ".br"
                effects.write_bytes(br_path, brotli.compress(data))

            count += 1

    return count, has_brotli


#: Root filenames the changelog page is auto-detected from, in order.
_ROOT_CHANGELOG_NAMES = ("CHANGELOG.md", "Changelog.md", "changelog.md")


def _changelog_source(config, dir_path, *, missing_ok=False):
    """Path to the changelog document this site publishes, or None.

    Two ways in, and the config decides which:

    * ``changelog`` names the file.  A declared name that is not there is
      an error -- the page was asked for, so its absence is a broken
      build rather than a page that quietly does not appear.
    * Absent, the project root's ``CHANGELOG.md`` is used when it exists.
      That convention reads "the root changelog is this project's
      changelog", which holds for a standalone repo and fails in a
      workspace whose root file rolls up several independently versioned
      projects; such a project declares the key instead.

    ``missing_ok`` is for the scans that ask which pages a *past* version
    held: an older checkout need not have the file, and that is an answer
    rather than a failure.
    """
    declared = (config or {}).get("changelog")
    if declared:
        candidate = os.path.join(dir_path, declared)
        if os.path.isfile(candidate):
            return candidate
        if missing_ok:
            return None
        raise RuntimeError(
            f"changelog: '{declared}' does not exist under {dir_path}. "
            f"The config names the changelog document to publish, so it "
            f"has to be a file; remove the key to fall back to the "
            f"project root's CHANGELOG.md."
        )
    for name in _ROOT_CHANGELOG_NAMES:
        candidate = os.path.join(dir_path, name)
        if os.path.isfile(candidate):
            return candidate
    return None


def build_single(dir_path=".", config=None,
                  mount_locale=None, mount_project="", mount_version=None,
                  mount_archived=False,
                  version_override=None,
                  locale_override=None,
                  available_versions=None, available_locales=None,
                  version_pages=None,
                  current_version="", current_locale="",
                  is_latest=True, page_filter=None,
                  unversioned_markdown=None, unversioned_frontmatter=None,
                  overlay_docs=None, write_baselines=True):
    """Build HTML and search entries for a single version/locale of docs.

    Performs config loading, template resolution, HTML generation, image
    dimension post-processing, and search index building.  The generated
    output goes back to the caller (``build()``), which handles all output
    IO.

    One thing is written here, and only here: the staleness baselines
    under ``.selfdoc/hashes``.  Pass ``write_baselines=False`` to suppress
    that and get a call that touches nothing at all -- which, together
    with ``overlay_docs``, is what makes an in-memory render possible.

    Args:
        dir_path: Project root directory.
        config: Pre-loaded config dict (if None, loads from selfdoc_core.json).
        mount_locale: Locale segment of this build's output mount (e.g.
            "en").  Pass ``""`` explicitly for an unmounted build.  When
            ``None`` (default), auto-computed from config alongside
            ``mount_version``.
        mount_project: Constituent-project segment of the mount on a
            unified site (e.g. "core"); ``""`` on a standalone site.
        mount_version: Version these pages are built from (e.g. "0.7.0").
            Pass ``""`` explicitly for pages that are not version-scoped.
            When ``None`` (default), auto-computed from config alongside
            ``mount_locale``.  A version does not imply a version segment:
            the current version is emitted at the stable address.
        mount_archived: Whether this build is a superseded version, emitted
            under ``v/<version>/`` beside the stable tree.
        version_override: Override detected version string (optional).
        locale_override: Override detected locale string (optional).
        overlay_docs: Optional dict mapping a docs-relative ``.md`` path to
            markdown source held in memory.  Entries are resolved like
            files on disk and override same-named files, so pages that were
            never written can be built.
        write_baselines: Whether to advance the staleness baselines in
            ``.selfdoc/hashes``.  ``False`` makes this call write nothing.

    The mount is the single input that decides where pages land and how
    they reach the output root; ``selfdoc_core.address.page_address``
    turns it plus a page path into every address the page has.

    Returns:
        BuildResult dataclass containing all build outputs for this version/locale.
    """
    if config is None:
        config = load_config(dir_path)

    if config is None:
        raise RuntimeError(
            "No selfdoc.json found. Run 'selfdoc init' to initialize."
        )

    # Resolve the mount coordinates from config when not explicitly set
    if mount_locale is None and mount_version is None:
        locales = config.get("locales")
        versions = config.get("versions")
        if locales and versions:
            # Find default locale (one with default: true, or first)
            default_locale = locales[0]
            for loc in locales:
                if loc.get("default") is True:
                    default_locale = loc
                    break
            mount_locale = locale_segment(default_locale["code"], locales)
            mount_version = versions[0]["version"]
        else:
            mount_locale = ""
            mount_version = ""
    else:
        if mount_locale is None:
            mount_locale = ""
        if mount_version is None:
            mount_version = ""

    docs_dir = os.path.join(dir_path, config["docs"].rstrip("/"))
    output_dir = os.path.join(dir_path, config["output"].rstrip("/"))

    if not os.path.isdir(docs_dir):
        raise RuntimeError(
            f"Docs directory '{config['docs']}' not found. "
            "Create it or run 'selfdoc init'."
        )

    # Resolve all .md templates via the shared pipeline
    all_docs = resolve_all_docs(
        config, docs_dir=docs_dir, base_dir=dir_path, overlay=overlay_docs,
    )
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
    # This is the only write in build_single; write_baselines=False turns it
    # off for renders that must leave the working tree untouched.
    if write_baselines:
        from selfdoc_core.staleness import update_hashes
        # build always writes fresh baselines and never enforces staleness, so
        # no skeleton exemption is needed. Pass an empty set explicitly
        # (update_hashes requires the keyword).
        if locale_override:
            prefixed_docs = {
                f"{locale_override}/{rp}": val
                for rp, val in all_docs.items()
            }
            update_hashes(prefixed_docs, dir_path, skeleton_pages=set())
        else:
            update_hashes(all_docs, dir_path, skeleton_pages=set())

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
            if os.path.isfile(full_path):
                mtime = os.path.getmtime(full_path)
            else:
                # Overlay page with no file behind it. Injecting it would
                # have written the file just now, so "now" is the same date.
                mtime = time.time()
            mtime_str = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d")
            modified = mtime_str
            published = mtime_str
        page_dates[rel_path] = (published, modified)

    changelog_path = _changelog_source(config, dir_path)

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
            result = effects.run(
                ["git", "symbolic-ref", "--short", "HEAD"],
                capture_output=True, text=True, timeout=5,
                cwd=dir_path, read=True,
            )
            if result.returncode == 0 and result.stdout.strip():
                branch = result.stdout.strip()
        except (OSError, subprocess.TimeoutExpired):
            pass
    if not branch:
        branch = "main"

    # Get base_url for canonical links and sitemap (Feature 22)
    base_url = config.get("base_url", None)
    url_builder = _make_url_builder(config)

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
        mount_locale=mount_locale,
        mount_project=mount_project,
        mount_version=mount_version,
        mount_archived=mount_archived,
        available_versions=available_versions,
        available_locales=available_locales,
        version_pages=version_pages,
        current_version=current_version,
        current_locale=current_locale,
        is_latest=is_latest,
        schema_types=config.get("schema_types"),
        unversioned_pages=unversioned_markdown,
        unversioned_frontmatter=unversioned_frontmatter,
    )

    # Post-process HTML pages: add image dimensions from file inspection
    # (Phase 3.3). Keys are output keys (mount included), so strip the
    # mount before converting back to a docs-relative md_path.
    mount = page_address("index.html", locale=mount_locale,
                         project=mount_project, version=mount_version,
                         archived=mount_archived).mount
    for output_key in list(html_files):
        page_path = (
            output_key[len(mount) + 1:] if mount else output_key
        )
        md_path = _html_to_md_path(page_path)
        html_files[output_key] = _add_image_dimensions(
            html_files[output_key], docs_dir, md_path,
        )

    # Build nav items (used by search index and auxiliary files)
    nav_items = _build_nav(
        markdown_files, frontmatter,
        unversioned_pages=unversioned_markdown,
        unversioned_frontmatter=unversioned_frontmatter,
    )

    return BuildResult(
        html_files=html_files,
        markdown_files=markdown_files,
        frontmatter=frontmatter,
        page_dates=page_dates,
        nav_items=nav_items,
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

    Pages under the posts prefix are neither: they are site-level pages,
    built once with no mount at all, and come back as their own set.

    Returns (versioned_paths, unversioned_paths, unversioned_markdown,
    unversioned_frontmatter, site_paths) where the sets hold relative md
    paths, ``unversioned_markdown`` maps md_path to resolved content, and
    ``unversioned_frontmatter`` maps md_path to frontmatter dicts.
    """
    all_docs = resolve_all_docs(config, docs_dir=docs_dir, base_dir=dir_path)
    versioned = set()
    unversioned = set()
    site = set()
    unversioned_markdown = {}
    unversioned_frontmatter = {}
    for rel_path, (fm, resolved, _raw, _lc) in all_docs.items():
        if _is_site_level(rel_path):
            site.add(rel_path)
        elif fm and fm.get("versioned") is False:
            unversioned.add(rel_path)
            unversioned_markdown[rel_path] = resolved
            if fm:
                unversioned_frontmatter[rel_path] = fm
        else:
            versioned.add(rel_path)
    return (
        versioned, unversioned, unversioned_markdown, unversioned_frontmatter,
        site,
    )


def _versioned_html_paths(build_dir, docs_dir_name, locale_code, locales,
                          config=None):
    """HTML paths of the version-scoped pages a docs tree would build.

    A cheap scan -- walk the tree, read frontmatter, skip the site-level
    and ``versioned: false`` pages -- because the only question it answers
    is which versions hold a given page.  The version picker asks that
    before offering a version, so it never links to a file no build wrote.
    """
    try:
        locale_docs_dir = _resolve_locale_docs_dir(
            build_dir, docs_dir_name, locale_code, locales,
        )
    except RuntimeError:
        return set()

    paths = set()
    for root, _dirs, files in os.walk(locale_docs_dir):
        for fname in files:
            if not fname.endswith(".md") or fname.startswith("_"):
                continue
            full = os.path.join(root, fname)
            rel = os.path.relpath(full, locale_docs_dir).replace(os.sep, "/")
            if _is_site_level(rel):
                continue
            with open(full, "r", encoding="utf-8") as f:
                fm, _body = parse_frontmatter(f.read())
            if fm.get("versioned") is False:
                continue
            paths.add(_md_to_html_path(rel))

    # build_single injects the project's changelog as a page of its own.
    if _changelog_source(config, build_dir, missing_ok=True) is not None:
        paths.add(_md_to_html_path("changelog.md"))
    return paths


#: The top-level segments of a mount that belong to the build rather than
#: to the author, each mapped to what the build does with it:
#:
#: * ``v`` is where superseded versions are emitted
#:   (``v/<version>/<page>/``), so a page named ``v`` would collide with
#:   the whole archive tree.
#: * ``blog`` is where posts are emitted, at the site level -- and where
#:   post injection *writes*, which is why an authored page there is a
#:   file the build would overwrite and then delete.
_RESERVED_TOP_SEGMENTS = {
    ARCHIVE_PREFIX: (
        f"superseded versions are emitted at "
        f"'{ARCHIVE_PREFIX}/<version>/<page>/'"
    ),
    POSTS_PREFIX: "posts are emitted at 'blog/<slug>/'",
}


def _check_reserved_page_paths(md_paths):
    """Refuse pages whose top-level segment is a reserved one.

    Raises RuntimeError naming the page and the segment.
    """
    for md_path in sorted(md_paths):
        first = md_path.split("/", 1)[0]
        stem = first[:-3] if first.endswith(".md") else first
        if stem in _RESERVED_TOP_SEGMENTS:
            raise RuntimeError(
                f"Page '{md_path}' uses the reserved top-level path "
                f"'{stem}': {_RESERVED_TOP_SEGMENTS[stem]}. Rename the page."
            )


def _check_reserved_authored_pages(docs_dir, base_dir=None):
    """Refuse authored pages sitting where the build writes its own files.

    ``_check_reserved_page_paths`` runs on the partitioned page sets, and
    the site-level partition holds exactly the pages injection just wrote,
    so it can never see an *authored* ``blog.md``: injection had already
    overwritten it, and cleanup deleted it afterwards.  This reads the tree
    itself, before anything writes into it, and refuses the file.

    *docs_dir* is a docs tree (a locale's, or the root one injection writes
    into); *base_dir* is what the reported path is relative to, so the
    message names the file the way its author does.

    Raises RuntimeError naming the file and the segment.
    """
    for stem in sorted(_RESERVED_TOP_SEGMENTS):
        found = []
        page = os.path.join(docs_dir, f"{stem}.md")
        if os.path.isfile(page):
            found.append(page)
        subdir = os.path.join(docs_dir, stem)
        if os.path.isdir(subdir):
            for root, _dirs, files in os.walk(subdir):
                found.extend(
                    os.path.join(root, name)
                    for name in sorted(files) if name.endswith(".md")
                )
        for path in found:
            rel = os.path.relpath(path, base_dir or docs_dir)
            raise RuntimeError(
                f"Authored page '{rel.replace(os.sep, '/')}' sits on the "
                f"reserved top-level path '{stem}': "
                f"{_RESERVED_TOP_SEGMENTS[stem]}. The build writes that path "
                f"itself, so building would overwrite the file and then "
                f"delete it. Move or rename the page."
            )


def _is_site_level(md_path):
    """Whether a docs-relative page is site-level (a post or their listing).

    Site-level pages are built with no mount at all: the posts under
    ``blog/<slug>.md`` and the listing at ``blog.md``, which is emitted at
    ``blog/`` beside them.
    """
    first = md_path.split("/", 1)[0]
    stem = first[: -len(".md")] if first.endswith(".md") else first
    return stem == POSTS_PREFIX


def check_post_slug_uniqueness(claims):
    """Refuse two posts claiming the same site-level address.

    Posts are emitted at ``blog/<slug>/`` with no project segment, so on a
    site assembled from several projects the slug namespace is shared.  A
    repeat would silently overwrite one post with another, so it is a hard
    error naming both sources.

    Args:
        claims: Iterable of ``(slug, source)`` pairs, where *source* names
            whatever produced the post (a project slug, a file path).
    """
    seen = {}
    for slug, source in claims:
        if slug in seen:
            raise RuntimeError(
                f"Duplicate post slug {slug!r}: claimed by both "
                f"{seen[slug]!r} and {source!r}. Posts are emitted at "
                f"'{POSTS_PREFIX}/<slug>/' with no project segment, so a "
                f"slug must be unique across every project on the site."
            )
        seen[slug] = source


def _render_post_listing(published_posts):
    """Render a Markdown post listing page from published post metadata.

    Returns the full Markdown content including frontmatter.
    ``published_posts`` should already be sorted newest-first and
    filtered (no drafts unless --drafts was used).
    """
    lines = [
        "---",
        "title: Posts",
        "versioned: false",
        "type: post-listing",
        "order: 95",
        "feed: false",
        "---",
        "",
        "# Posts",
        "",
    ]
    if not published_posts:
        lines.append("No posts yet.")
    else:
        for post in published_posts:
            date = post["date"]
            title = post["title"]
            slug = post["slug"]
            # The listing is emitted at blog/, so a post is a sibling.
            lines.append(f"- **{date}** -- [{title}]({slug}/)")
    lines.append("")
    return "\n".join(lines)


def post_docs_payloads(published_posts):
    """Return the docs-tree markdown for a set of published posts.

    Maps a docs-relative path (``blog/<slug>.md``, plus ``blog.md``
    for the listing, which is emitted at ``blog/``) to the markdown that page is built from.  Posts are
    site-level pages: they are built at ``blog/<slug>/`` under the output
    root, with no locale, project or version segment, and both the full
    build and the posts-only build emit them at that same address.  This is the
    one place a post becomes a docs page: ``_inject_posts_into_docs``
    writes these payloads into the docs tree, and the in-memory render path
    hands the same payloads to ``build_single`` as an overlay -- so both
    produce the same pages.

    ``published_posts`` must already be filtered (drafts removed unless
    they were asked for) and ordered newest-first.
    """
    payloads = {}
    for post in published_posts:
        fm_lines = []
        for key, val in post["frontmatter"].items():
            if val is None:
                continue
            if isinstance(val, bool):
                fm_lines.append(f"{key}: {'true' if val else 'false'}")
            elif isinstance(val, list):
                fm_lines.append(f"{key}: [{', '.join(str(v) for v in val)}]")
            else:
                fm_lines.append(f"{key}: {val}")
        payloads[f"{POSTS_PREFIX}/{post['slug']}.md"] = (
            "---\n" + "\n".join(fm_lines) + "\n---\n" + post["content"]
        )

    if published_posts:
        payloads[f"{POSTS_PREFIX}.md"] = _render_post_listing(published_posts)

    return payloads


def _inject_posts_into_docs(dir_path, config, docs_dir, include_drafts):
    """Write post markdown files into docs/blog/ for the build pipeline.

    Discovers posts from the configured posts directory, filters drafts
    unless ``include_drafts`` is True, and writes each post as a ``.md``
    file under ``docs_dir/blog/``.  Also generates a listing page at
    ``docs_dir/blog.md``, which is emitted at ``blog/``.  The written files are picked up by
    ``resolve_all_docs`` and partitioned into the site-level page set,
    which is built with no mount at all -- so a post is at ``blog/<slug>/``
    whichever build produced it.

    Returns a list of absolute paths to injected files (for cleanup).

    Refuses first: an authored page on a reserved path is a file this
    function would overwrite and cleanup would then delete, so no build
    that could inject may proceed past one.  Checking here rather than at
    each call site is what makes the destruction structurally impossible --
    every build path reaches the tree through this function.
    """
    _check_reserved_authored_pages(docs_dir, dir_path)

    posts_config = config.get("posts") or {}
    posts_dir_rel = posts_config.get("dir", ".selfdoc/posts/")
    posts_dir = os.path.join(dir_path, posts_dir_rel)
    if not os.path.isdir(posts_dir):
        return []

    discover_posts = require_post_provider()

    manifest_path = os.path.join(dir_path, ".selfdoc", "manifest.json")
    all_posts = discover_posts(posts_dir, manifest_path=manifest_path)

    published_posts = [
        post for post in all_posts
        if include_drafts or not post["draft"]
    ]

    injected = []
    for rel_path, content in post_docs_payloads(published_posts).items():
        post_docs_path = os.path.join(docs_dir, rel_path)
        effects.makedirs(os.path.dirname(post_docs_path), exist_ok=True)
        with effects.open_write(post_docs_path, "w", encoding="utf-8") as f:
            f.write(content)
        injected.append(post_docs_path)

    return injected


def default_locale_of(config):
    """The locale code a project's site-level pages are written in.

    The declared default if one is marked, else the first declared -- the
    same rule :func:`build` applies to the versioned tree.
    """
    locales = config.get("locales") or []
    if not locales:
        return ""
    for loc in locales:
        if loc.get("default") is True:
            return loc["code"]
    return locales[0]["code"]


def site_level_build_args(config, docs_dir_name):
    """The ``build_single`` arguments every site-level page is built with.

    A post is one page with one address, and three paths produce it: the
    full build's site-level pass, the posts-only target the assembly runs
    when nothing but a post changed, and the in-memory renderer an editor
    previews with.  Whichever ran last decides what the site serves, so
    they cannot differ -- and the way to guarantee that is for the
    arguments to have one definition rather than three copies.

    Site-level means no mount and no version segment: the page is served
    from the site root, not from the project's subtree and not from an
    archive prefix.  It still carries the project's default locale, which
    is what puts it in a locale search filter.
    """
    site_config = dict(config)
    site_config["docs"] = docs_dir_name
    locale_code = default_locale_of(config)
    return {
        "config": site_config,
        "mount_locale": "",
        "mount_version": "",
        "version_override": "",
        "locale_override": locale_code,
        "available_locales": None,
        "current_version": "",
        "current_locale": locale_code,
        "is_latest": True,
    }


def _cleanup_injected_posts(injected_files, docs_dir):
    """Remove post files injected into docs/ by ``_inject_posts_into_docs``.

    Also removes the ``blog/`` subdirectory under ``docs_dir`` if it
    becomes empty after cleanup.
    """
    for fpath in injected_files:
        if os.path.isfile(fpath):
            effects.remove(fpath)
    posts_subdir = os.path.join(docs_dir, POSTS_PREFIX)
    if os.path.isdir(posts_subdir) and not os.listdir(posts_subdir):
        effects.rmdir(posts_subdir)


def _build_posts_only(dir_path, config, output_dir, docs_dir_name,
                      docs_dir, include_drafts):
    """Build only post pages, skipping versioned docs and auxiliary files.

    Injects posts into ``docs/blog/``, runs them through ``build_single``
    with a page filter and no mount, writes the HTML output, cleans up,
    and generates a post-manifest.  No sitemap, feed, search index, or CSS
    is generated.

    The mount is empty here and the post pages are site-level in the full
    build too, so a post is at ``blog/<slug>/`` either way -- the two
    builds cannot disagree about where a post lives.

    The arguments handed to ``build_single`` are the ones the full build's
    site-level pass uses, and for the same reason: a post is one page, so
    the two targets have to produce one page.  The assembly rebuilds posts
    alone when only a post changed and grafts the result beside the full
    build's output, so any disagreement would make the last build to run
    decide what the site serves.

    Returns:
        Dict of {output_path: True} for files written.
    """
    # Discover posts for manifest generation (before injection, which
    # also calls the provider internally)
    discover_posts = require_post_provider()
    posts_config = config.get("posts") or {}
    posts_dir_rel = posts_config.get("dir", ".selfdoc/posts/")
    posts_dir = os.path.join(dir_path, posts_dir_rel)
    manifest_path = os.path.join(dir_path, ".selfdoc", "manifest.json")
    discovered_posts = discover_posts(posts_dir, manifest_path=manifest_path)

    # Filter drafts to match what _inject_posts_into_docs will produce
    if not include_drafts:
        discovered_posts = [p for p in discovered_posts if not p["draft"]]

    injected_paths = _inject_posts_into_docs(
        dir_path, config, docs_dir, include_drafts,
    )

    try:
        if not injected_paths:
            # Generate empty post-manifest even with no posts
            from selfdoc_core.manifest import generate_manifest
            generate_manifest(
                config, pages_data={}, posts_data=[],
                dir_path=dir_path, output_name="post-manifest.json",
            )
            return {}

        # Convert absolute injected paths to relative paths within docs_dir
        page_filter = {
            os.path.relpath(p, docs_dir) for p in injected_paths
        }

        result = build_single(
            dir_path=dir_path,
            page_filter=page_filter,
            **site_level_build_args(config, docs_dir_name),
        )

        written = {}
        for rel_path, html_content in result.html_files.items():
            out_path = os.path.join(output_dir, rel_path)
            effects.makedirs(os.path.dirname(out_path), exist_ok=True)
            with effects.open_write(out_path, "w", encoding="utf-8") as f:
                f.write(_minify_html(html_content))
            written[out_path] = True

        # Generate post-manifest with discovered posts
        from selfdoc_core.manifest import generate_manifest
        generate_manifest(
            config, pages_data={}, posts_data=discovered_posts,
            dir_path=dir_path, output_name="post-manifest.json",
        )

        return written
    finally:
        _cleanup_injected_posts(injected_paths, docs_dir)


def build(dir_path=".", config=None, version_filter=None, locale_filter=None,
          include_drafts=False, target="", theme=""):
    """Build docs from templates + directives, with multi-locale/multi-version support.

    Outer loop iterates locales, inner loop iterates versions. For each
    locale/version combination, builds HTML from either the working tree
    (latest version) or git archive extraction (older versions). All
    search entries are merged into a single index. Auxiliary files (OG
    cards, sitemap, feed, etc.) use the latest version's data only.

    Args:
        dir_path: Project root directory.
        config: Pre-loaded config dict (if None, loads from selfdoc_core.json).
        version_filter: Optional version string to build only that version.
        locale_filter: Optional locale code to build only that locale.
        include_drafts: Include draft posts in the build output.
        target: Build target. ``"posts"`` for posts-only build, empty
            string for a full build.
        theme: Theme name that overrides the one the config declares, for
            this build only.  Empty means the config decides.  Nothing is
            written back to selfdoc.json -- the override lives as long as
            the call does.

    Returns:
        Dict of {output_path: True} for files written.
    """
    if config is None:
        config = load_config(dir_path)
    if config is None:
        raise RuntimeError(
            "No selfdoc.json found. Run 'selfdoc init' to initialize."
        )

    if theme:
        # Validated against the registry rather than trusted: a
        # misspelled name would otherwise reach get_theme and fail deep
        # in the render with a less useful message.
        known = list_themes()
        if theme not in known:
            raise ConfigError(
                f"unknown theme {theme!r}; available themes: "
                f"{', '.join(known)}"
            )
        config = {**config, "theme": theme}

    if config.get("versions") is None:
        raise ConfigError(
            "selfdoc.json requires 'versions' array. "
            "Add: \"versions\": [{\"version\": \"1.0.0\"}]"
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

    # Refuse an authored page on a path the build writes itself, before the
    # output directory is touched and long before injection runs.  Injection
    # checks the tree it writes into; these are the locale trees it never
    # sees, whose pages the partition would still carry.
    _check_reserved_authored_pages(docs_dir_check, dir_path)
    for locale in build_locales:
        try:
            locale_docs_dir = _resolve_locale_docs_dir(
                dir_path, docs_dir_name, locale["code"], locales,
            )
        except RuntimeError:
            # A missing locale directory is reported by the build proper,
            # with its own message; this check has nothing to read.
            continue
        _check_reserved_authored_pages(locale_docs_dir, dir_path)

    # Clean output directory
    if os.path.exists(output_dir):
        effects.rmtree(output_dir)
    effects.makedirs(output_dir, exist_ok=True)

    # Resolve docs from the latest (working tree)
    latest_docs_dir = os.path.join(dir_path, docs_dir_name)

    # --- Posts-only build mode ---
    if target == "posts":
        return _build_posts_only(
            dir_path, config, output_dir, docs_dir_name,
            latest_docs_dir, include_drafts,
        )

    # --- Partition pages into versioned, unversioned and site-level ---
    version_strs = [v["version"] for v in versions]

    # Inject posts into docs/blog/ so the normal pipeline discovers them
    injected_post_files = _inject_posts_into_docs(
        dir_path, config, latest_docs_dir, include_drafts,
    )
    # Post pages are site-level: built once, with no mount, from the tree
    # they were just written into.
    site_pages = {
        os.path.relpath(f, latest_docs_dir).replace(os.sep, "/")
        for f in injected_post_files
    }

    # Partition per locale.  Page paths are relative to the locale's own
    # docs directory, so a single partition of the top-level docs/ tree
    # yields locale-prefixed paths that no per-locale build can match --
    # which silently filtered every page out of a localized build.
    partitions = {}
    for locale in build_locales:
        locale_code = locale["code"]
        locale_docs_dir = _resolve_locale_docs_dir(
            dir_path, docs_dir_name, locale_code, locales,
        )
        locale_config = dict(config)
        locale_config["docs"] = os.path.relpath(locale_docs_dir, dir_path)
        partition = _partition_pages(locale_config, locale_docs_dir, dir_path)
        # The build owns two top-level segments; an author page may not
        # take either.  Post pages are exempt: the build put them there.
        _check_reserved_page_paths(partition[0] | partition[1])
        partitions[locale_code] = partition

    try:
        written = _build_body(
            dir_path, config, locales, versions, default_locale_code,
            latest_version, build_versions, build_locales, output_dir,
            docs_dir_name, latest_docs_dir, partitions,
            version_strs, include_drafts, site_pages,
        )
    finally:
        _cleanup_injected_posts(injected_post_files, latest_docs_dir)

    return written


def _build_body(
    dir_path, config, locales, versions, default_locale_code,
    latest_version, build_versions, build_locales, output_dir,
    docs_dir_name, latest_docs_dir, partitions,
    version_strs, include_drafts, site_pages,
):
    """Core build logic for single-project sites.

    ``partitions`` maps a locale code to that locale's
    ``(versioned, unversioned, uv_markdown, uv_frontmatter, site)`` page
    partition, because page paths are relative to the locale's own docs
    directory.

    The current version is emitted at the stable address and every older
    version under ``v/<version>/``; site-level pages (posts) are built
    once, with no mount at all.

    Extracted so ``build`` can wrap it in try/finally for
    post-injection cleanup.
    """
    written = {}
    content_pages = 0
    latest_build = None
    # Track per-locale stable HTML paths for the sitemaps.  Archived
    # versions are excluded: they canonicalize to the stable address, so
    # listing them would ask a crawler to index a page that points away
    # from itself.
    per_locale_stable_html = {}  # locale_code -> list of html rel paths

    # Extract every version's content once, up front, and learn which
    # pages each version holds -- the version picker is rendered inside
    # each page and offers a version only when that version has the page.
    build_dirs = {}
    for ver_entry in build_versions:
        ver_str = ver_entry["version"]
        build_dirs[ver_str] = (
            dir_path if ver_str == latest_version
            else _extract_version_content(ver_str, config, dir_path)
        )
    version_pages = {}  # locale_code -> {version: set of html paths}
    for locale in build_locales:
        version_pages[locale["code"]] = {
            ver_entry["version"]: _versioned_html_paths(
                build_dirs[ver_entry["version"]], docs_dir_name,
                locale["code"], locales, config,
            )
            for ver_entry in build_versions
        }

    # Multi-locale / multi-version build loop (locales = outer, versions = inner)
    for locale in build_locales:
        locale_code = locale["code"]
        mount_locale = locale_segment(locale_code, locales)
        per_locale_stable_html[locale_code] = []
        (versioned_pages, unversioned_pages, uv_markdown, uv_frontmatter,
         _site_pages) = partitions[locale_code]

        for ver_entry in build_versions:
            ver_str = ver_entry["version"]
            is_latest = (ver_str == latest_version)
            archived = not is_latest
            output_subdir = page_address(
                "index.html", locale=mount_locale, version=ver_str,
                archived=archived,
            ).mount

            build_dir = build_dirs[ver_str]

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
                mount_locale=mount_locale,
                mount_version=ver_str,
                mount_archived=archived,
                version_override=ver_str,
                locale_override=locale_code,
                available_versions=versions,
                available_locales=locales,
                version_pages=version_pages[locale_code],
                current_version=ver_str,
                current_locale=locale_code,
                is_latest=is_latest,
                page_filter=versioned_pages if unversioned_pages else None,
                unversioned_markdown=uv_markdown if unversioned_pages else None,
                unversioned_frontmatter=uv_frontmatter if unversioned_pages else None,
            )
            html_files = result.html_files
            markdown_files = result.markdown_files
            frontmatter = result.frontmatter
            page_dates = result.page_dates
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

            for rel_path, html_content in html_files.items():
                out_path = os.path.join(output_dir, rel_path)
                effects.makedirs(os.path.dirname(out_path), exist_ok=True)
                with effects.open_write(out_path, "w", encoding="utf-8") as f:
                    f.write(_minify_html(html_content))
                written[out_path] = True
                content_pages += 1

            for rel_path in other_files:
                src = os.path.join(docs_dir, rel_path)
                dst = os.path.join(output_dir, output_subdir, rel_path)
                effects.makedirs(os.path.dirname(dst), exist_ok=True)
                effects.copy_file(src, dst)
                written[dst] = True

            # Collect stable HTML paths for the sitemaps.  Only the
            # current version is listed; an archive is canonicalized away.
            if is_latest:
                for rel_path in html_files:
                    if rel_path.endswith(".html") and (
                        rel_path not in per_locale_stable_html[locale_code]
                    ):
                        per_locale_stable_html[locale_code].append(rel_path)

            if is_latest and locale_code == default_locale_code:
                latest_build = {
                    "html_files": html_files,
                    "markdown_files": markdown_files,
                    "page_addresses": {
                        md: page_address(
                            _md_to_html_path(md),
                            locale=mount_locale, version=ver_str,
                        )
                        for md in markdown_files
                    },
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
                    "url_builder": _make_url_builder(config),
                    "feed_url": feed_url,
                    "lang": lang,
                }

    # Fallback: if version_filter excluded the latest, use the last build
    if latest_build is None:
        latest_build = {
            "html_files": html_files,
            "markdown_files": markdown_files,
            "page_addresses": {
                md: page_address(
                    _md_to_html_path(md),
                    locale=locale_segment(locale_code, locales),
                    version=ver_str,
                )
                for md in markdown_files
            },
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
            "url_builder": _make_url_builder(config),
            "feed_url": feed_url,
            "lang": lang,
        }

    # --- Build unversioned pages (once per locale, no version) ---
    uv_latest_build = None
    for locale in build_locales:
        locale_code = locale["code"]
        mount_locale = locale_segment(locale_code, locales)
        unversioned_pages = partitions[locale_code][1]
        if not unversioned_pages:
            continue
        # Unversioned pages sit at the stable mount, beside the current
        # version's pages.
        uv_output_subdir = page_address(
            "index.html", locale=mount_locale,
        ).mount

        # Resolve locale-specific docs directory
        locale_docs_dir = _resolve_locale_docs_dir(
            dir_path, docs_dir_name, locale_code, locales,
        )
        locale_config = dict(config)
        locale_config["docs"] = os.path.relpath(locale_docs_dir, dir_path)

        uv_result = build_single(
            dir_path=dir_path,
            config=locale_config,
            mount_locale=mount_locale,
            mount_version="",
            version_override="",
            locale_override=locale_code,
            available_versions=versions,
            available_locales=locales,
            version_pages=version_pages[locale_code],
            current_version="",
            current_locale=locale_code,
            is_latest=True,
            page_filter=unversioned_pages,
        )

        for rel_path, html_content in uv_result.html_files.items():
            out_path = os.path.join(output_dir, rel_path)
            effects.makedirs(os.path.dirname(out_path), exist_ok=True)
            with effects.open_write(out_path, "w", encoding="utf-8") as f:
                f.write(_minify_html(html_content))
            written[out_path] = True
            content_pages += 1

        for rel_path in uv_result.other_files:
            src = os.path.join(uv_result.docs_dir, rel_path)
            dst = os.path.join(output_dir, uv_output_subdir, rel_path)
            effects.makedirs(os.path.dirname(dst), exist_ok=True)
            effects.copy_file(src, dst)
            written[dst] = True

        # Unversioned pages are stable addresses: they belong in the sitemap.
        for rel_path in uv_result.html_files:
            if rel_path.endswith(".html") and (
                rel_path not in per_locale_stable_html[locale_code]
            ):
                per_locale_stable_html[locale_code].append(rel_path)

        if locale_code == default_locale_code:
            uv_latest_build = {
                "markdown_files": uv_result.markdown_files,
                "frontmatter": uv_result.frontmatter,
                "page_dates": uv_result.page_dates,
                "page_addresses": {
                    md: page_address(
                        _md_to_html_path(md), locale=mount_locale,
                    )
                    for md in uv_result.markdown_files
                },
            }

    # --- Build site-level pages (posts) once, with no mount at all ---
    # They are read from the top-level docs tree, which is where they were
    # injected, so a localized project's posts are not dropped on the floor
    # by a per-locale partition that never sees them.
    site_latest_build = None
    if site_pages:
        site_result = build_single(
            dir_path=dir_path,
            page_filter=site_pages,
            **site_level_build_args(config, docs_dir_name),
        )
        for rel_path, html_content in site_result.html_files.items():
            out_path = os.path.join(output_dir, rel_path)
            effects.makedirs(os.path.dirname(out_path), exist_ok=True)
            with effects.open_write(out_path, "w", encoding="utf-8") as f:
                f.write(_minify_html(html_content))
            written[out_path] = True
            content_pages += 1
            if rel_path not in per_locale_stable_html[default_locale_code]:
                per_locale_stable_html[default_locale_code].append(rel_path)
        site_latest_build = {
            "markdown_files": site_result.markdown_files,
            "frontmatter": site_result.frontmatter,
            "page_dates": site_result.page_dates,
            "page_addresses": {
                md: page_address(_md_to_html_path(md))
                for md in site_result.markdown_files
            },
        }

    # A build that wrote no page at all is a build whose page filters
    # matched nothing.  It still writes assets, a sitemap and redirect
    # stubs, so nothing downstream notices -- which is how a localized
    # project with an unversioned page shipped an empty site.
    if content_pages == 0:
        raise RuntimeError(
            "Build produced no content pages: every page filter matched "
            "nothing. Check that the pages under "
            f"'{config['docs']}' resolve for the configured locales."
        )

    # Merge unversioned and site-level data into latest_build for aux files
    for extra in (uv_latest_build, site_latest_build):
        if not (extra and latest_build):
            continue
        latest_build["markdown_files"] = {
            **latest_build["markdown_files"], **extra["markdown_files"],
        }
        latest_build["frontmatter"] = {
            **latest_build["frontmatter"], **extra["frontmatter"],
        }
        latest_build["page_dates"] = {
            **latest_build["page_dates"], **extra["page_dates"],
        }
        # These pages mount elsewhere, so their addresses come from their
        # own build, not from the versioned one.
        latest_build["page_addresses"] = {
            **latest_build["page_addresses"], **extra["page_addresses"],
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
    with effects.open_write(css_path, "w", encoding="utf-8") as f:
        f.write(theme_css)
    written[css_path] = True

    # Custom CSS
    custom_css_src = os.path.join(lb["docs_dir"], "custom.css")
    if lb["has_custom_css"]:
        custom_css_dst = os.path.join(output_dir, "custom.css")
        effects.copy_file(custom_css_src, custom_css_dst)
        written[custom_css_dst] = True

    # Auxiliary files using latest version data only.  The sitemap lists
    # stable addresses across every locale, and nothing else.
    all_stable_html_paths = []
    for locale_paths in per_locale_stable_html.values():
        all_stable_html_paths.extend(locale_paths)

    repo = config.get("repo", None)
    has_sitemap_index = len(build_locales) > 1
    aux_written = _generate_auxiliary_files(
        output_dir=output_dir,
        project_name=lb["project_name"],
        version=lb["version"],
        markdown_files=lb["markdown_files"],
        html_paths=all_stable_html_paths,
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
        # 404.html sits at the output root; its sidebar links into the
        # stable mount, where every current page lives.
        mount_locale=locale_segment(default_locale_code, locales),
        page_addresses=lb["page_addresses"],
    )
    written.update(aux_written)

    # Per-locale sitemaps + sitemap-index (when multiple locales)
    if len(build_locales) > 1:
        locale_sitemap_paths = _generate_per_locale_sitemaps(
            output_dir=output_dir,
            per_locale_stable_html=per_locale_stable_html,
            url_builder=lb["url_builder"],
            page_dates=lb["page_dates"],
        )
        for sp in locale_sitemap_paths:
            written[sp] = True

        sitemap_index_path = _generate_sitemap_index(
            output_dir=output_dir,
            locale_codes=list(per_locale_stable_html.keys()),
            url_builder=lb["url_builder"],
        )
        written[sitemap_index_path] = True

    # Root redirect into the stable mount.  A single-locale standalone
    # site mounts the current version at the output root, so its home page
    # IS the root index -- there is nothing to redirect to, and writing a
    # stub would overwrite the page.
    stable_home = page_address("index.html", locale=locale_segment(
        default_locale_code, locales,
    ))
    # Document-relative, with no leading slash.  The build output is not
    # always served from an origin root: an assembly serves it under
    # /<slug>/ and GitHub Pages project sites under /<repo>/.  A
    # root-relative hop escapes that subtree; a document-relative one
    # resolves correctly in every case, origin root included.  The stub
    # sits at the output root, so the pinned address is already the hop.
    redirect_url = stable_home.stable
    # The canonical must be absolute: a root-relative one resolves against
    # whatever host served the stub, so every alias of the site would claim
    # to be canonical.
    canonical_url = lb["url_builder"].page_url(redirect_url)
    write_root_stub = bool(redirect_url)
    root_index_html = (
        "<!DOCTYPE html>\n"
        "<html>\n"
        "<head>\n"
        f'  <meta http-equiv="refresh" content="0;url={redirect_url}">\n'
        f'  <link rel="canonical" href="{canonical_url}">\n'
        "</head>\n"
        "<body>\n"
        f'  <script>window.location.replace("{redirect_url}")</script>\n'
        f'  <p>Redirecting to <a href="{redirect_url}">{redirect_url}</a></p>\n'
        "</body>\n"
        "</html>\n"
    )
    if write_root_stub:
        root_index_path = os.path.join(output_dir, "index.html")
        with effects.open_write(root_index_path, "w", encoding="utf-8") as f:
            f.write(root_index_html)
        written[root_index_path] = True

    # Cloudflare only ever reads the _redirects at the deployed site root,
    # where there is no document to resolve a relative target against --
    # these rules stay site-absolute.  Deliberate: a standalone deployment
    # owns its origin root, and on the unified site the assembly worker
    # owns redirects instead of this file.
    redirects_path = os.path.join(output_dir, "_redirects")
    redirects_content = f"/ /{redirect_url} 302\n" if write_root_stub else ""
    with effects.open_write(redirects_path, "w", encoding="utf-8") as f:
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
                mount_locale = locale_segment(locale["code"], locales)
                for ver_entry in build_versions:
                    ver_str = ver_entry["version"]
                    archived = ver_str != latest_version
                    # Both ends of the redirect are pages of this mount, so
                    # both come from the addressing authority.
                    from_addr = page_address(
                        f"{from_slug}/index.html",
                        locale=mount_locale, version=ver_str,
                        archived=archived,
                    )
                    to_addr = page_address(
                        f"{to_slug}/index.html",
                        locale=mount_locale, version=ver_str,
                        archived=archived,
                    )
                    old_path = os.path.join(output_dir, from_addr.output_key)
                    # Skip if the page already exists (e.g. cached old-version page)
                    if os.path.exists(old_path):
                        continue
                    # Target path within the site, and the document-relative
                    # hop from the stub's own directory to it (see the root
                    # stub above for why a root-relative hop is wrong).
                    target_path = to_addr.url
                    stub_dir = posixpath.dirname(from_addr.output_key)
                    target_url = (
                        posixpath.relpath(target_path, stub_dir) + "/"
                    )
                    # Absolute canonical (see the root stub above).
                    target_canonical = lb["url_builder"].page_url(target_path)
                    # Generate HTML meta-refresh page
                    meta_html = (
                        "<!DOCTYPE html>\n"
                        "<html>\n"
                        "<head>\n"
                        f'  <meta http-equiv="refresh" content="0;url={target_url}">\n'
                        f'  <link rel="canonical" href="{target_canonical}">\n'
                        "</head>\n"
                        "<body>\n"
                        f'  <script>window.location.replace("{target_url}")</script>\n'
                        f'  <p>Redirecting to <a href="{target_url}">{target_url}</a></p>\n'
                        "</body>\n"
                        "</html>\n"
                    )
                    effects.makedirs(os.path.dirname(old_path), exist_ok=True)
                    with effects.open_write(old_path, "w", encoding="utf-8") as f:
                        f.write(meta_html)
                    written[old_path] = True
                    # Append Cloudflare _redirects rule
                    with effects.open_write(redirects_path, "a", encoding="utf-8") as f:
                        f.write(
                            f"/{from_addr.url} /{target_path} 301\n"
                        )
                    redirect_count += 1
        if redirect_count:
            print(f"Generated {redirect_count} redirect(s)")

    # Pagefind indexes the pages this build just wrote and emits both the
    # index and the UI bundle every page references into pagefind/ at the
    # output root.  It runs after the last HTML file -- including the 404
    # page and the redirect stubs -- and before compression, so the index
    # covers the whole site and its own assets get compressed with it.
    _run_pagefind(output_dir)

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
    base_url, has_custom_css, repo, url_builder, lang="en", page_dates=None,
    frontmatter=None, description="", feed_url=None, critical_css=None,
    accent_color="#0969da", theme_meta=None, deploy=None,
    feed_max_entries=None, has_sitemap_index=False,
    mount_locale="", mount_project="",
    page_addresses=None,
):
    """Generate auxiliary build artifacts (OG cards, sitemap, llms.txt, 404, favicon, feed).

    Called by build() after the main HTML pages and static files are written.

    ``page_addresses`` maps every md_path in ``markdown_files`` to its
    :class:`~selfdoc_core.address.PageAddress`.  It is mandatory: the feed
    and llms.txt emit absolute page URLs, and a page's URL is its mounted
    address -- there is no sensible mountless answer to fall back on.
    Both emit the stable address, which is the one that keeps working.

    Returns a dict of {output_path: True} for files written.
    """
    if page_addresses is None:
        raise ValueError(
            "page_addresses is required: auxiliary files emit absolute page "
            "URLs, which are the pages' mounted addresses"
        )
    written = {}

    # Generate OG social card PNGs (Feature 21)
    for md_path, content in markdown_files.items():
        slug = md_path.replace(".md", "") if md_path.endswith(".md") else md_path
        page_title = _extract_title(content, slug)
        png_bytes = _generate_og_png(project_name, page_title, accent_color)
        png_path = os.path.join(output_dir, f"og-{slug}.png")
        effects.makedirs(os.path.dirname(png_path), exist_ok=True)
        with effects.open_write(png_path, "wb") as f:
            f.write(png_bytes)
        written[png_path] = True

    # Generate sitemap.xml (Feature 22)
    sitemap_content = _generate_sitemap(html_paths, url_builder,
                                        page_dates=page_dates)
    sitemap_path = os.path.join(output_dir, "sitemap.xml")
    with effects.open_write(sitemap_path, "w", encoding="utf-8") as f:
        f.write(sitemap_content)
    written[sitemap_path] = True

    # Generate llms.txt and llms-full.txt (Feature 24)
    llms_txt = _generate_llms_txt(project_name, markdown_files, url_builder,
                                  page_addresses)
    llms_path = os.path.join(output_dir, "llms.txt")
    with effects.open_write(llms_path, "w", encoding="utf-8") as f:
        f.write(llms_txt)
    written[llms_path] = True

    llms_full = _generate_llms_full_txt(project_name, markdown_files)
    llms_full_path = os.path.join(output_dir, "llms-full.txt")
    with effects.open_write(llms_full_path, "w", encoding="utf-8") as f:
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
        url_builder=url_builder,
        page_addresses=page_addresses,
        feed_max_entries=feed_max_entries,
    )
    written[feed_path] = True

    # Generate 404.html (Feature 39).  The sidebar spans both mounts, so
    # the pages are split the way a page build splits them: an address
    # with no version segment belongs to the version-free mount.
    #
    # Only for a project serving its own output root.  ``404.html`` is a
    # hosting-provider convention answered at the root of what is served,
    # and a mounted project's output root is a subdirectory of somebody
    # else's site: no request ever reaches a subtree's copy, the site's own
    # root 404 answers instead, and the buried copy is an unreachable page
    # that still has to satisfy every assertion made about a page.
    if url_builder is None or not url_builder.mounted():
        versioned_md = {}
        unversioned_md = {}
        for md_path, content in markdown_files.items():
            if page_addresses[md_path].version:
                versioned_md[md_path] = content
            else:
                unversioned_md[md_path] = content
        nav_items = _build_nav(
            versioned_md, frontmatter,
            unversioned_pages=unversioned_md or None,
            unversioned_frontmatter=frontmatter,
        )
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
            mount_locale=mount_locale,
            mount_project=mount_project,
        )
        not_found_path = os.path.join(output_dir, "404.html")
        with effects.open_write(not_found_path, "w", encoding="utf-8") as f:
            f.write(not_found_html)
        written[not_found_path] = True

    # Generate favicon.svg from project initials (Feature 40)
    favicon_svg = _generate_favicon_svg(project_name, accent_color)
    favicon_path = os.path.join(output_dir, "favicon.svg")
    with effects.open_write(favicon_path, "w", encoding="utf-8") as f:
        f.write(favicon_svg)
    written[favicon_path] = True

    # Generate robots.txt (allow all crawlers including AI bots)
    robots_path = _generate_robots_txt(output_dir, base_url, url_builder,
                                       has_sitemap_index=has_sitemap_index)
    written[robots_path] = True

    # Generate _headers only for Cloudflare Pages deploy target
    deploy_provider = (deploy or {}).get("provider")
    if deploy_provider == "cloudflare-pages":
        headers_path = _generate_headers(output_dir)
        written[headers_path] = True

    # _redirects no longer needed: directory-index URLs work without
    # trailing-slash redirects on all hosting platforms.

    return written


def _generate_robots_txt(output_dir, base_url, url_builder, has_sitemap_index=False):
    """Generate robots.txt allowing all crawlers including AI bots.

    The crawler policy itself is declared in :mod:`selfdoc_core.robots`, so
    this file and the assembly's site-wide robots.txt cannot drift apart.

    When ``has_sitemap_index`` is True, references ``sitemap-index.xml``
    instead of ``sitemap.xml``.
    """
    from selfdoc_core.robots import render_robots_txt

    sitemap_file = "sitemap-index.xml" if has_sitemap_index else "sitemap.xml"
    content = render_robots_txt(url_builder.asset_url(sitemap_file))
    path = os.path.join(output_dir, "robots.txt")
    with effects.open_write(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path


def _generate_per_locale_sitemaps(output_dir, per_locale_stable_html,
                                  url_builder, page_dates=None):
    """Generate per-locale sitemap.xml files at output_dir/{locale}/sitemap.xml.

    Returns a list of written file paths.
    """
    written = []
    for locale_code, html_paths in per_locale_stable_html.items():
        sitemap_content = _generate_sitemap(html_paths, url_builder,
                                            page_dates=page_dates)
        locale_dir = os.path.join(output_dir, locale_code)
        effects.makedirs(locale_dir, exist_ok=True)
        sitemap_path = os.path.join(locale_dir, "sitemap.xml")
        with effects.open_write(sitemap_path, "w", encoding="utf-8") as f:
            f.write(sitemap_content)
        written.append(sitemap_path)
    return written


def _generate_sitemap_index(output_dir, locale_codes, url_builder):
    """Generate sitemap-index.xml at the output root listing per-locale sitemaps.

    Returns the written file path.
    """
    entries = []
    for code in sorted(locale_codes):
        loc_url = url_builder.asset_url(f"{code}/sitemap.xml")
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
    with effects.open_write(path, "w", encoding="utf-8") as f:
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
    with effects.open_write(path, "w", encoding="utf-8") as f:
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
