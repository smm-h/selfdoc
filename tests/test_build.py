"""Tests for selfdoc.build."""

import json
import os
import re

import pytest

import struct

import gzip as gzip_module

from unittest import mock

from selfdoc.build import build, _parse_frontmatter, _generate_robots_txt, _generate_headers, _generate_redirects, _generate_sitemap, _generate_atom_feed, _minify_css, _minify_html, _extract_critical_css, _add_image_dimensions, _read_jpeg_dimensions, _read_webp_dimensions, _compress_output, _generate_og_png_basic
from selfdoc.html import generate_html, generate_404_page, _extract_first_paragraph, _minify_js, md_to_html


@pytest.fixture()
def project_dir(tmp_path):
    """Create a minimal selfdoc project in a temp directory."""
    # Write selfdoc.json
    config = {
        "language": "python",
        "source": ["src/"],
        "docs": "docs/",
        "output": "docs/_build/",
        "base_url": "https://example.com",
    }
    config_path = os.path.join(tmp_path, "selfdoc.json")
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f)

    # Create docs/ with a simple template
    docs_dir = os.path.join(tmp_path, "docs")
    os.makedirs(docs_dir)

    index_md = os.path.join(docs_dir, "index.md")
    with open(index_md, "w", encoding="utf-8") as f:
        f.write("# Test Project\n\nWelcome.\n")

    return tmp_path


def test_build_produces_html(project_dir):
    """Build with a simple template produces HTML output."""
    written = build(str(project_dir))

    assert len(written) > 0

    # Check that index.html was created
    output_dir = os.path.join(project_dir, "docs", "_build")
    index_html = os.path.join(output_dir, "index.html")
    assert index_html in written
    assert os.path.isfile(index_html)

    # Verify it contains expected HTML content
    with open(index_html, "r", encoding="utf-8") as f:
        content = f.read()
    assert "<!DOCTYPE html>" in content
    assert '<h1 id="test-project"><a class="heading-link" href="#test-project" aria-label="Link to section: Test Project">#</a>Test Project</h1>' in content
    assert "Welcome." in content


def test_build_resolves_directives_with_error_for_missing(project_dir):
    """Directives for missing modules produce a visible error message."""
    docs_dir = os.path.join(project_dir, "docs")
    page_md = os.path.join(docs_dir, "api.md")
    with open(page_md, "w", encoding="utf-8") as f:
        f.write("# API\n\n:::module mymod\n:::\n")

    written = build(str(project_dir))

    output_dir = os.path.join(project_dir, "docs", "_build")
    api_html = os.path.join(output_dir, "api.html")
    assert api_html in written

    with open(api_html, "r", encoding="utf-8") as f:
        content = f.read()
    # The resolver produces an error message for missing modules
    assert "not found" in content
    assert "mymod" in content


def test_build_copies_non_md_files(project_dir):
    """Non-.md files in docs/ are copied to output."""
    docs_dir = os.path.join(project_dir, "docs")

    # Create an image file (just a dummy)
    img_path = os.path.join(docs_dir, "logo.png")
    with open(img_path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n")  # PNG magic bytes

    written = build(str(project_dir))

    output_dir = os.path.join(project_dir, "docs", "_build")
    copied_img = os.path.join(output_dir, "logo.png")
    assert copied_img in written
    assert os.path.isfile(copied_img)


def test_build_multiple_files(project_dir):
    """Build with multiple templates produces multiple HTML files."""
    docs_dir = os.path.join(project_dir, "docs")

    guide_md = os.path.join(docs_dir, "guide.md")
    with open(guide_md, "w", encoding="utf-8") as f:
        f.write("# Guide\n\nA guide page.\n")

    written = build(str(project_dir))

    output_dir = os.path.join(project_dir, "docs", "_build")
    assert os.path.isfile(os.path.join(output_dir, "index.html"))
    assert os.path.isfile(os.path.join(output_dir, "guide.html"))
    # 2 HTML + 1 style.css + 1 search-index.json + 1 search.js + 2 OG PNGs
    # + 2 llms files + 1 404.html + 1 favicon.svg + 1 robots.txt
    # + 1 _headers + 1 _redirects + 1 sitemap.xml + 1 feed.xml (base_url is set)
    assert len(written) == 16
    assert os.path.isfile(os.path.join(output_dir, "style.css"))
    assert os.path.isfile(os.path.join(output_dir, "search-index.json"))
    assert os.path.isfile(os.path.join(output_dir, "og-index.png"))
    assert os.path.isfile(os.path.join(output_dir, "og-guide.png"))
    # Verify PNG magic bytes
    with open(os.path.join(output_dir, "og-index.png"), "rb") as f:
        assert f.read(8) == b"\x89PNG\r\n\x1a\n"
    assert os.path.isfile(os.path.join(output_dir, "llms.txt"))
    assert os.path.isfile(os.path.join(output_dir, "llms-full.txt"))
    assert os.path.isfile(os.path.join(output_dir, "404.html"))
    assert os.path.isfile(os.path.join(output_dir, "favicon.svg"))
    assert os.path.isfile(os.path.join(output_dir, "sitemap.xml"))
    assert os.path.isfile(os.path.join(output_dir, "feed.xml"))


def test_build_no_config_raises(tmp_path):
    """Build without selfdoc.json raises an error."""
    with pytest.raises(RuntimeError, match="No selfdoc.json found"):
        build(str(tmp_path))


def test_build_no_docs_dir_raises(tmp_path):
    """Build without docs/ directory raises an error."""
    config = {"language": "python", "source": ["src/"], "docs": "docs/", "output": "docs/_build/", "base_url": "https://example.com"}
    config_path = os.path.join(tmp_path, "selfdoc.json")
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f)

    with pytest.raises(RuntimeError, match="not found"):
        build(str(tmp_path))


def test_build_generates_sidebar(project_dir):
    """Built HTML contains sidebar navigation."""
    docs_dir = os.path.join(project_dir, "docs")
    guide_md = os.path.join(docs_dir, "guide.md")
    with open(guide_md, "w", encoding="utf-8") as f:
        f.write("# Guide\n\nContent.\n")

    build(str(project_dir))

    output_dir = os.path.join(project_dir, "docs", "_build")
    with open(os.path.join(output_dir, "index.html"), "r", encoding="utf-8") as f:
        content = f.read()

    # Sidebar should link to guide.html
    assert "guide.html" in content
    assert '<nav class="sidebar" id="sidebar" aria-label="Site navigation">' in content


def test_robots_txt_with_base_url(tmp_path):
    """robots.txt includes Sitemap line when base_url is set."""
    path = _generate_robots_txt(str(tmp_path), "https://example.com")
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    assert "User-agent: *\nAllow: /" in content
    assert "Sitemap: https://example.com/sitemap.xml" in content


def test_robots_txt_ai_crawlers(tmp_path):
    """robots.txt contains entries for all AI crawler user-agents."""
    path = _generate_robots_txt(str(tmp_path), "https://example.com")
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    for agent in ["GPTBot", "ChatGPT-User", "Google-Extended", "PerplexityBot", "ClaudeBot", "Googlebot", "OAI-SearchBot"]:
        assert f"User-agent: {agent}" in content


def test_headers_file(tmp_path):
    """_headers file contains correct security headers."""
    path = _generate_headers(str(tmp_path))
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    assert content.startswith("/*\n")
    assert "Strict-Transport-Security: max-age=31536000; includeSubDomains; preload" in content
    assert "X-Content-Type-Options: nosniff" in content
    assert "X-Frame-Options: DENY" in content
    assert "Referrer-Policy: strict-origin-when-cross-origin" in content
    assert "Permissions-Policy: camera=(), microphone=(), geolocation=()" in content
    assert "X-XSS-Protection: 0" in content
    # Cache-control for static assets
    assert "/style.css" in content
    assert "/*.svg" in content
    assert "Cache-Control: public, max-age=31536000, immutable" in content


def test_html_lang_attribute_from_config(project_dir):
    """HTML lang attribute matches the lang value from config."""
    # Update config with a custom lang
    config_path = os.path.join(project_dir, "selfdoc.json")
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
    config["lang"] = "fa"
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f)

    build(str(project_dir))

    output_dir = os.path.join(project_dir, "docs", "_build")
    with open(os.path.join(output_dir, "index.html"), "r", encoding="utf-8") as f:
        content = f.read()

    assert '<html lang="fa">' in content


def test_html_lang_default_en(project_dir):
    """HTML lang defaults to 'en' when not set in config."""
    build(str(project_dir))

    output_dir = os.path.join(project_dir, "docs", "_build")
    with open(os.path.join(output_dir, "index.html"), "r", encoding="utf-8") as f:
        content = f.read()

    assert '<html lang="en">' in content


def test_html_article_tag_present(project_dir):
    """Built HTML wraps content in an <article> tag."""
    build(str(project_dir))

    output_dir = os.path.join(project_dir, "docs", "_build")
    with open(os.path.join(output_dir, "index.html"), "r", encoding="utf-8") as f:
        content = f.read()

    assert "<article>" in content
    assert "</article>" in content


def test_html_site_footer_present(project_dir):
    """Built HTML contains the site footer."""
    build(str(project_dir))

    output_dir = os.path.join(project_dir, "docs", "_build")
    with open(os.path.join(output_dir, "index.html"), "r", encoding="utf-8") as f:
        content = f.read()

    assert '<footer class="site-footer">' in content
    assert "selfdoc" in content


def test_html_no_highlight_js(project_dir):
    """Built HTML does NOT contain highlight.js CDN links or hljs calls."""
    build(str(project_dir))

    output_dir = os.path.join(project_dir, "docs", "_build")
    with open(os.path.join(output_dir, "index.html"), "r", encoding="utf-8") as f:
        content = f.read()

    assert "highlight.js" not in content
    assert "hljs" not in content
    assert "cdnjs.cloudflare.com" not in content
    assert "hljs.highlightAll()" not in content


# --- Date infrastructure tests (Wave 2 Phase 0) ---


def _build_and_get_page_dates(project_dir):
    """Helper: run build and return page_dates dict by re-parsing frontmatter and mtime.

    Returns dict mapping filename -> (published, modified) tuple.
    """
    from datetime import datetime
    from selfdoc.config import load_config
    config = load_config(str(project_dir))
    docs_dir = os.path.join(project_dir, "docs")

    page_dates = {}
    for fname in os.listdir(docs_dir):
        if not fname.endswith(".md"):
            continue
        full_path = os.path.join(docs_dir, fname)
        with open(full_path, "r", encoding="utf-8") as f:
            content = f.read()
        metadata, _ = _parse_frontmatter(content)
        has_updated = "updated" in metadata
        has_date = "date" in metadata
        if has_updated and has_date:
            modified = str(metadata["updated"])
            published = str(metadata["date"])
        elif has_updated:
            modified = str(metadata["updated"])
            published = None
        elif has_date:
            modified = str(metadata["date"])
            published = str(metadata["date"])
        else:
            mtime = os.path.getmtime(full_path)
            mtime_str = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d")
            modified = mtime_str
            published = mtime_str
        page_dates[fname] = (published, modified)
    return page_dates


def test_page_date_from_updated_frontmatter(project_dir):
    """A page with 'updated' in frontmatter gets that date."""
    docs_dir = os.path.join(project_dir, "docs")
    page_md = os.path.join(docs_dir, "dated.md")
    with open(page_md, "w", encoding="utf-8") as f:
        f.write("---\nupdated: 2026-05-01\n---\n# Dated Page\n\nContent.\n")

    # Build succeeds
    build(str(project_dir))

    page_dates = _build_and_get_page_dates(project_dir)
    published, modified = page_dates["dated.md"]
    assert modified == "2026-05-01"
    assert published is None


def test_page_date_from_date_frontmatter(project_dir):
    """A page with 'date' (no 'updated') in frontmatter gets that date."""
    docs_dir = os.path.join(project_dir, "docs")
    page_md = os.path.join(docs_dir, "dated.md")
    with open(page_md, "w", encoding="utf-8") as f:
        f.write("---\ndate: 2026-01-15\n---\n# Dated Page\n\nContent.\n")

    build(str(project_dir))

    page_dates = _build_and_get_page_dates(project_dir)
    published, modified = page_dates["dated.md"]
    assert published == "2026-01-15"
    assert modified == "2026-01-15"


def test_page_date_from_mtime(project_dir):
    """A page with no date frontmatter gets a date from file mtime (YYYY-MM-DD)."""
    # The index.md created by the fixture has no date frontmatter
    build(str(project_dir))

    page_dates = _build_and_get_page_dates(project_dir)
    published, modified = page_dates["index.md"]
    assert re.match(r"^\d{4}-\d{2}-\d{2}$", modified), f"Expected YYYY-MM-DD, got {modified}"
    assert published == modified


def test_page_date_updated_takes_priority_over_date(project_dir):
    """'updated' takes priority over 'date' for modified date."""
    docs_dir = os.path.join(project_dir, "docs")
    page_md = os.path.join(docs_dir, "both.md")
    with open(page_md, "w", encoding="utf-8") as f:
        f.write("---\ndate: 2026-01-15\nupdated: 2026-05-01\n---\n# Both\n\nContent.\n")

    build(str(project_dir))

    page_dates = _build_and_get_page_dates(project_dir)
    published, modified = page_dates["both.md"]
    assert modified == "2026-05-01"
    assert published == "2026-01-15"


# --- Phase 2.1: Visible dates, JSON-LD dateModified, sitemap lastmod ---


def test_last_updated_visible_in_html(project_dir):
    """Built HTML contains 'Last updated' with a formatted date and <time> element."""
    docs_dir = os.path.join(project_dir, "docs")
    page_md = os.path.join(docs_dir, "dated.md")
    with open(page_md, "w", encoding="utf-8") as f:
        f.write("---\nupdated: 2026-05-01\n---\n# Dated Page\n\nContent.\n")

    build(str(project_dir))

    output_dir = os.path.join(project_dir, "docs", "_build")
    with open(os.path.join(output_dir, "dated.html"), "r", encoding="utf-8") as f:
        content = f.read()

    assert "Last updated" in content
    assert '<time datetime="2026-05-01">' in content
    assert "May 1, 2026" in content


def test_json_ld_date_modified(project_dir):
    """Built HTML JSON-LD contains dateModified when page has a date."""
    docs_dir = os.path.join(project_dir, "docs")
    # Need base_url for JSON-LD to be generated
    config_path = os.path.join(project_dir, "selfdoc.json")
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
    config["base_url"] = "https://example.com"
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f)

    page_md = os.path.join(docs_dir, "dated.md")
    with open(page_md, "w", encoding="utf-8") as f:
        f.write("---\nupdated: 2026-05-01\n---\n# Dated Page\n\nContent.\n")

    build(str(project_dir))

    output_dir = os.path.join(project_dir, "docs", "_build")
    with open(os.path.join(output_dir, "dated.html"), "r", encoding="utf-8") as f:
        content = f.read()

    assert '"dateModified": "2026-05-01"' in content


def test_sitemap_lastmod(project_dir):
    """sitemap.xml contains <lastmod> entries when page_dates are available."""
    # Set base_url so sitemap is generated
    config_path = os.path.join(project_dir, "selfdoc.json")
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
    config["base_url"] = "https://example.com"
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f)

    docs_dir = os.path.join(project_dir, "docs")
    page_md = os.path.join(docs_dir, "dated.md")
    with open(page_md, "w", encoding="utf-8") as f:
        f.write("---\nupdated: 2026-05-01\n---\n# Dated Page\n\nContent.\n")

    build(str(project_dir))

    output_dir = os.path.join(project_dir, "docs", "_build")
    with open(os.path.join(output_dir, "sitemap.xml"), "r", encoding="utf-8") as f:
        content = f.read()

    assert "<lastmod>2026-05-01</lastmod>" in content


# --- Phase 2.2: BreadcrumbList, WebSite, author, SoftwareSourceCode JSON-LD ---


def test_breadcrumb_list_on_non_index_page(project_dir):
    """BreadcrumbList JSON-LD appears on non-index pages when base_url is set."""
    config_path = os.path.join(project_dir, "selfdoc.json")
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
    config["base_url"] = "https://example.com"
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f)

    docs_dir = os.path.join(project_dir, "docs")
    with open(os.path.join(docs_dir, "guide.md"), "w", encoding="utf-8") as f:
        f.write("# Guide\n\nContent.\n")

    build(str(project_dir))

    output_dir = os.path.join(project_dir, "docs", "_build")

    # Non-index page should have BreadcrumbList
    with open(os.path.join(output_dir, "guide.html"), "r", encoding="utf-8") as f:
        guide_html = f.read()
    assert '"BreadcrumbList"' in guide_html
    assert '"Home"' in guide_html
    assert "https://example.com/index.html" in guide_html

    # Index page should NOT have BreadcrumbList
    with open(os.path.join(output_dir, "index.html"), "r", encoding="utf-8") as f:
        index_html = f.read()
    assert '"BreadcrumbList"' not in index_html


def test_website_search_action_on_index_only(project_dir):
    """WebSite+SearchAction JSON-LD appears only on index page when base_url is set."""
    config_path = os.path.join(project_dir, "selfdoc.json")
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
    config["base_url"] = "https://example.com"
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f)

    docs_dir = os.path.join(project_dir, "docs")
    with open(os.path.join(docs_dir, "guide.md"), "w", encoding="utf-8") as f:
        f.write("# Guide\n\nContent.\n")

    build(str(project_dir))

    output_dir = os.path.join(project_dir, "docs", "_build")

    # Index page should have WebSite with SearchAction
    with open(os.path.join(output_dir, "index.html"), "r", encoding="utf-8") as f:
        index_html = f.read()
    assert '"WebSite"' in index_html
    assert '"SearchAction"' in index_html
    assert "https://example.com/" in index_html

    # Non-index page should NOT have WebSite
    with open(os.path.join(output_dir, "guide.html"), "r", encoding="utf-8") as f:
        guide_html = f.read()
    assert '"WebSite"' not in guide_html


def test_author_from_config_in_json_ld(project_dir):
    """Author from config appears in TechArticle JSON-LD."""
    config_path = os.path.join(project_dir, "selfdoc.json")
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
    config["base_url"] = "https://example.com"
    config["author"] = {"name": "Jane Doe", "type": "Person", "url": "https://jane.dev"}
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f)

    build(str(project_dir))

    output_dir = os.path.join(project_dir, "docs", "_build")
    with open(os.path.join(output_dir, "index.html"), "r", encoding="utf-8") as f:
        content = f.read()

    assert '"Person"' in content
    assert '"Jane Doe"' in content
    assert '"https://jane.dev"' in content


def test_default_author_when_no_config_author(project_dir):
    """Default author (project name as Organization) when no config author."""
    config_path = os.path.join(project_dir, "selfdoc.json")
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
    config["base_url"] = "https://example.com"
    # No "author" key in config
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f)

    build(str(project_dir))

    output_dir = os.path.join(project_dir, "docs", "_build")
    with open(os.path.join(output_dir, "index.html"), "r", encoding="utf-8") as f:
        content = f.read()

    # Should use project name as Organization
    assert '"Organization"' in content


def test_software_source_code_on_pages_with_code(project_dir):
    """SoftwareSourceCode JSON-LD appears on pages containing code blocks."""
    config_path = os.path.join(project_dir, "selfdoc.json")
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
    config["base_url"] = "https://example.com"
    config["repo"] = "https://github.com/test/repo"
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f)

    docs_dir = os.path.join(project_dir, "docs")
    with open(os.path.join(docs_dir, "index.md"), "w", encoding="utf-8") as f:
        f.write("# Test\n\n```python\nprint('hi')\n```\n\n```go\nfmt.Println()\n```\n")

    build(str(project_dir))

    output_dir = os.path.join(project_dir, "docs", "_build")
    with open(os.path.join(output_dir, "index.html"), "r", encoding="utf-8") as f:
        content = f.read()

    assert '"SoftwareSourceCode"' in content
    assert '"python"' in content
    assert '"go"' in content
    assert '"https://github.com/test/repo"' in content


# --- Phase 2C: SoftwareSourceCode name property ---


def test_software_source_code_has_name():
    """SoftwareSourceCode JSON-LD includes name property from page title."""
    html_files = generate_html(
        {"index.md": "# API Reference\n\n```python\nprint('hi')\n```\n"},
        project_name="Test",
    )
    content = html_files["index.html"]

    ld_blocks = re.findall(
        r'<script type="application/ld\+json">\s*(.*?)\s*</script>',
        content,
        re.DOTALL,
    )
    source_code = None
    for block in ld_blocks:
        data = json.loads(block)
        if data.get("@type") == "SoftwareSourceCode":
            source_code = data
            break

    assert source_code is not None, "SoftwareSourceCode JSON-LD not found"
    assert source_code["name"] == "API Reference"


# --- Phase 2.3: OG tags, Twitter Cards, auto-generated meta descriptions ---


def test_og_url_present(project_dir):
    """og:url meta tag is present with correct absolute URL when base_url is set."""
    config_path = os.path.join(project_dir, "selfdoc.json")
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
    config["base_url"] = "https://example.com"
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f)

    build(str(project_dir))

    output_dir = os.path.join(project_dir, "docs", "_build")
    with open(os.path.join(output_dir, "index.html"), "r", encoding="utf-8") as f:
        content = f.read()

    assert '<meta property="og:url" content="https://example.com/index.html">' in content


def test_og_description_present(project_dir):
    """og:description meta tag is present when page has a description."""
    config_path = os.path.join(project_dir, "selfdoc.json")
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
    config["base_url"] = "https://example.com"
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f)

    docs_dir = os.path.join(project_dir, "docs")
    with open(os.path.join(docs_dir, "index.md"), "w", encoding="utf-8") as f:
        f.write("---\ndescription: My project description\n---\n# Test\n\nContent.\n")

    build(str(project_dir))

    output_dir = os.path.join(project_dir, "docs", "_build")
    with open(os.path.join(output_dir, "index.html"), "r", encoding="utf-8") as f:
        content = f.read()

    assert '<meta property="og:description" content="My project description">' in content


def test_og_image_absolute_url(project_dir):
    """og:image uses an absolute URL starting with base_url."""
    config_path = os.path.join(project_dir, "selfdoc.json")
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
    config["base_url"] = "https://example.com"
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f)

    build(str(project_dir))

    output_dir = os.path.join(project_dir, "docs", "_build")
    with open(os.path.join(output_dir, "index.html"), "r", encoding="utf-8") as f:
        content = f.read()

    assert '<meta property="og:image" content="https://example.com/og-index.png">' in content


def test_twitter_card_and_title_present(project_dir):
    """twitter:card and twitter:title meta tags are present when base_url is set."""
    config_path = os.path.join(project_dir, "selfdoc.json")
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
    config["base_url"] = "https://example.com"
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f)

    build(str(project_dir))

    output_dir = os.path.join(project_dir, "docs", "_build")
    with open(os.path.join(output_dir, "index.html"), "r", encoding="utf-8") as f:
        content = f.read()

    assert '<meta name="twitter:card" content="summary_large_image">' in content
    assert re.search(r'<meta name="twitter:title" content="Test Project - [^"]+">', content)


def test_no_auto_generated_description(project_dir):
    """Without frontmatter description, meta description is empty (no auto-extraction)."""
    config_path = os.path.join(project_dir, "selfdoc.json")
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
    config["base_url"] = "https://example.com"
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f)

    docs_dir = os.path.join(project_dir, "docs")
    with open(os.path.join(docs_dir, "index.md"), "w", encoding="utf-8") as f:
        f.write("# Test\n\nThis is the first paragraph of the page.\n")

    build(str(project_dir))

    output_dir = os.path.join(project_dir, "docs", "_build")
    with open(os.path.join(output_dir, "index.html"), "r", encoding="utf-8") as f:
        content = f.read()

    # No auto-extraction: no meta description tag should be emitted
    assert '<meta name="description"' not in content


def test_frontmatter_description_takes_priority(project_dir):
    """Frontmatter description takes priority over auto-generated."""
    config_path = os.path.join(project_dir, "selfdoc.json")
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
    config["base_url"] = "https://example.com"
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f)

    docs_dir = os.path.join(project_dir, "docs")
    with open(os.path.join(docs_dir, "index.md"), "w", encoding="utf-8") as f:
        f.write("---\ndescription: Custom description from frontmatter\n---\n# Test\n\nThis is the first paragraph.\n")

    build(str(project_dir))

    output_dir = os.path.join(project_dir, "docs", "_build")
    with open(os.path.join(output_dir, "index.html"), "r", encoding="utf-8") as f:
        content = f.read()

    assert '<meta name="description" content="Custom description from frontmatter">' in content
    assert "This is the first paragraph" not in content.split('<meta name="description"')[0].split('<meta name="description"')[-1]
    # Verify frontmatter description is used in OG tags too
    assert '<meta property="og:description" content="Custom description from frontmatter">' in content


def test_extract_first_paragraph_basic():
    """_extract_first_paragraph extracts text from first <p> tag."""
    html = '<h1>Title</h1>\n<p>Hello world</p>\n<p>Second para</p>'
    assert _extract_first_paragraph(html) == "Hello world"


def test_extract_first_paragraph_strips_html():
    """_extract_first_paragraph strips inner HTML tags."""
    html = '<p>Hello <strong>bold</strong> and <em>italic</em></p>'
    assert _extract_first_paragraph(html) == "Hello bold and italic"


def test_extract_first_paragraph_truncates_at_word_boundary():
    """_extract_first_paragraph truncates long text at a word boundary."""
    long_text = "word " * 40  # 200 chars
    html = f'<p>{long_text.strip()}</p>'
    result = _extract_first_paragraph(html)
    # Truncated at word boundary with "..." appended (max 155 + 3 = 158)
    assert len(result) <= 158
    assert result.endswith("...")
    # Should not cut mid-word (strip "..." to check)
    assert result[:-3].endswith("word")


def test_extract_first_paragraph_empty():
    """_extract_first_paragraph returns empty string when no <p> found."""
    assert _extract_first_paragraph('<h1>Only heading</h1>') == ""
    assert _extract_first_paragraph('') == ""


def test_extract_first_paragraph_unescapes_html_entities():
    """_extract_first_paragraph unescapes HTML entities to avoid double-escaping."""
    html = '<p>Use <code>a &amp; b</code> for joining</p>'
    assert _extract_first_paragraph(html) == "Use a & b for joining"


# --- Phase 2.4: Atom feed generation ---


def test_atom_feed_generated_with_base_url(project_dir):
    """feed.xml is generated when base_url is set in config."""
    config_path = os.path.join(project_dir, "selfdoc.json")
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
    config["base_url"] = "https://example.com"
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f)

    written = build(str(project_dir))

    output_dir = os.path.join(project_dir, "docs", "_build")
    feed_path = os.path.join(output_dir, "feed.xml")
    assert feed_path in written
    assert os.path.isfile(feed_path)


def test_atom_feed_contains_valid_structure(project_dir):
    """feed.xml contains <feed>, <entry>, correct title, and correct URLs."""
    config_path = os.path.join(project_dir, "selfdoc.json")
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
    config["base_url"] = "https://example.com"
    config["description"] = "A test project"
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f)

    docs_dir = os.path.join(project_dir, "docs")
    with open(os.path.join(docs_dir, "guide.md"), "w", encoding="utf-8") as f:
        f.write("---\nupdated: 2026-05-01\n---\n# Guide Page\n\nThis is a guide.\n")

    build(str(project_dir))

    output_dir = os.path.join(project_dir, "docs", "_build")
    with open(os.path.join(output_dir, "feed.xml"), "r", encoding="utf-8") as f:
        content = f.read()

    # Feed-level structure
    assert '<feed xmlns="http://www.w3.org/2005/Atom">' in content
    assert "</feed>" in content
    assert "<title>" in content
    assert "Documentation</title>" in content
    assert '<link href="https://example.com/feed.xml" rel="self"/>' in content
    assert '<link href="https://example.com/"/>' in content
    assert "<id>https://example.com/</id>" in content
    assert "<subtitle>A test project</subtitle>" in content

    # Entry structure
    assert "<entry>" in content
    assert "</entry>" in content
    assert "<title>Guide Page</title>" in content
    assert '<link href="https://example.com/guide.html"/>' in content
    assert "<id>https://example.com/guide.html</id>" in content
    assert "<updated>2026-05-01T00:00:00Z</updated>" in content
    assert "<summary>This is a guide.</summary>" in content


def test_atom_feed_link_in_html_with_base_url(project_dir):
    """HTML pages contain Atom feed <link> tag when base_url is set."""
    config_path = os.path.join(project_dir, "selfdoc.json")
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
    config["base_url"] = "https://example.com"
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f)

    build(str(project_dir))

    output_dir = os.path.join(project_dir, "docs", "_build")
    with open(os.path.join(output_dir, "index.html"), "r", encoding="utf-8") as f:
        content = f.read()

    assert '<link rel="alternate" type="application/atom+xml"' in content
    assert 'href="feed.xml">' in content


# --- Phase 2.5: Improved 404 page ---


# --- Phase 2.6: Visible page summary from frontmatter description ---


def test_page_summary_shown_with_description(project_dir):
    """A page with frontmatter description shows a .page-summary block."""
    docs_dir = os.path.join(project_dir, "docs")
    with open(os.path.join(docs_dir, "summary.md"), "w", encoding="utf-8") as f:
        f.write("---\ndescription: This is my page summary\n---\n# Summary Page\n\nContent.\n")

    build(str(project_dir))

    output_dir = os.path.join(project_dir, "docs", "_build")
    with open(os.path.join(output_dir, "summary.html"), "r", encoding="utf-8") as f:
        content = f.read()

    assert '<div class="page-summary">' in content
    assert "This is my page summary" in content


def test_no_page_summary_without_frontmatter(project_dir):
    """A page without frontmatter description gets no .page-summary div (no auto-extraction)."""
    docs_dir = os.path.join(project_dir, "docs")
    with open(os.path.join(docs_dir, "index.md"), "w", encoding="utf-8") as f:
        f.write("# Test Project\n\nThis is a substantial first paragraph with enough text.\n")

    build(str(project_dir))

    output_dir = os.path.join(project_dir, "docs", "_build")
    with open(os.path.join(output_dir, "index.html"), "r", encoding="utf-8") as f:
        content = f.read()

    assert '<div class="page-summary">' not in content


def test_page_summary_text_matches_description(project_dir):
    """The summary text matches the frontmatter description exactly."""
    docs_dir = os.path.join(project_dir, "docs")
    desc_text = "A detailed description of what this page covers"
    with open(os.path.join(docs_dir, "detailed.md"), "w", encoding="utf-8") as f:
        f.write(f"---\ndescription: {desc_text}\n---\n# Detailed\n\nBody text.\n")

    build(str(project_dir))

    output_dir = os.path.join(project_dir, "docs", "_build")
    with open(os.path.join(output_dir, "detailed.html"), "r", encoding="utf-8") as f:
        content = f.read()

    assert f"<p>{desc_text}</p>" in content


def test_page_summary_frontmatter_takes_priority(project_dir):
    """A page with frontmatter description uses that for summary, not auto-generated."""
    docs_dir = os.path.join(project_dir, "docs")
    with open(os.path.join(docs_dir, "index.md"), "w", encoding="utf-8") as f:
        f.write("---\ndescription: Frontmatter desc\n---\n# Test\n\nFirst paragraph text.\n")

    build(str(project_dir))

    output_dir = os.path.join(project_dir, "docs", "_build")
    with open(os.path.join(output_dir, "index.html"), "r", encoding="utf-8") as f:
        content = f.read()

    assert '<div class="page-summary">' in content
    assert "Frontmatter desc" in content


def test_no_auto_summary_from_first_paragraph(project_dir):
    """A page with no frontmatter description gets no .page-summary div (no auto-extraction)."""
    docs_dir = os.path.join(project_dir, "docs")
    with open(os.path.join(docs_dir, "autosummary.md"), "w", encoding="utf-8") as f:
        f.write("# Auto Summary\n\nSelfdoc is a code-aware static site generator that resolves directive blocks.\n")

    build(str(project_dir))

    output_dir = os.path.join(project_dir, "docs", "_build")
    with open(os.path.join(output_dir, "autosummary.html"), "r", encoding="utf-8") as f:
        content = f.read()

    assert '<div class="page-summary">' not in content


def test_explicit_summary_takes_precedence(project_dir):
    """A page with frontmatter description uses that for summary, not auto-generated text."""
    docs_dir = os.path.join(project_dir, "docs")
    with open(os.path.join(docs_dir, "explicit.md"), "w", encoding="utf-8") as f:
        f.write(
            "---\ndescription: Explicit description from frontmatter\n---\n"
            "# Explicit\n\nThis is the first paragraph which should not appear as summary.\n"
        )

    build(str(project_dir))

    output_dir = os.path.join(project_dir, "docs", "_build")
    with open(os.path.join(output_dir, "explicit.html"), "r", encoding="utf-8") as f:
        content = f.read()

    assert '<div class="page-summary">' in content
    assert "Explicit description from frontmatter" in content
    # The auto-extracted text should NOT appear in the summary block
    assert "should not appear as summary" not in content.split('<div class="page-summary">')[1].split('</div>')[0]


def test_no_summary_for_short_content(project_dir):
    """A page with a very short first paragraph gets no page-summary div."""
    docs_dir = os.path.join(project_dir, "docs")
    with open(os.path.join(docs_dir, "short.md"), "w", encoding="utf-8") as f:
        f.write("# Short\n\nHi.\n")

    build(str(project_dir))

    output_dir = os.path.join(project_dir, "docs", "_build")
    with open(os.path.join(output_dir, "short.html"), "r", encoding="utf-8") as f:
        content = f.read()

    assert '<div class="page-summary">' not in content


def test_tech_article_has_description_field(project_dir):
    """TechArticle JSON-LD includes a description field when description exists."""
    config_path = os.path.join(project_dir, "selfdoc.json")
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
    config["base_url"] = "https://example.com"
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f)

    docs_dir = os.path.join(project_dir, "docs")
    with open(os.path.join(docs_dir, "index.md"), "w", encoding="utf-8") as f:
        f.write("---\ndescription: My page description\n---\n# Test\n\nContent.\n")

    build(str(project_dir))

    output_dir = os.path.join(project_dir, "docs", "_build")
    with open(os.path.join(output_dir, "index.html"), "r", encoding="utf-8") as f:
        content = f.read()

    # Extract TechArticle JSON-LD
    ld_blocks = re.findall(
        r'<script type="application/ld\+json">\s*(.*?)\s*</script>',
        content,
        re.DOTALL,
    )
    tech_article = None
    for block in ld_blocks:
        data = json.loads(block)
        if data.get("@type") == "TechArticle":
            tech_article = data
            break

    assert tech_article is not None, "TechArticle JSON-LD not found"
    assert tech_article["description"] == "My page description"


def test_tech_article_no_auto_description(project_dir):
    """TechArticle JSON-LD has empty description when no frontmatter description (no auto-extraction)."""
    config_path = os.path.join(project_dir, "selfdoc.json")
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
    config["base_url"] = "https://example.com"
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f)

    docs_dir = os.path.join(project_dir, "docs")
    with open(os.path.join(docs_dir, "index.md"), "w", encoding="utf-8") as f:
        f.write("# Test\n\nThis is content without frontmatter description.\n")

    build(str(project_dir))

    output_dir = os.path.join(project_dir, "docs", "_build")
    with open(os.path.join(output_dir, "index.html"), "r", encoding="utf-8") as f:
        content = f.read()

    ld_blocks = re.findall(
        r'<script type="application/ld\+json">\s*(.*?)\s*</script>',
        content,
        re.DOTALL,
    )
    tech_article = None
    for block in ld_blocks:
        data = json.loads(block)
        if data.get("@type") == "TechArticle":
            tech_article = data
            break

    assert tech_article is not None, "TechArticle JSON-LD not found"
    # No auto-extraction: description field should be absent
    assert "description" not in tech_article


def test_404_contains_sidebar_navigation(project_dir):
    """404.html contains sidebar navigation links matching other pages."""
    docs_dir = os.path.join(project_dir, "docs")
    with open(os.path.join(docs_dir, "guide.md"), "w", encoding="utf-8") as f:
        f.write("# Guide\n\nContent.\n")

    build(str(project_dir))

    output_dir = os.path.join(project_dir, "docs", "_build")
    with open(os.path.join(output_dir, "404.html"), "r", encoding="utf-8") as f:
        content = f.read()

    assert '<nav class="sidebar" id="sidebar" aria-label="Site navigation">' in content
    assert "guide.html" in content
    assert "index.html" in content


def test_404_contains_search_button(project_dir):
    """404.html contains a search button/prompt to help users find content."""
    build(str(project_dir))

    output_dir = os.path.join(project_dir, "docs", "_build")
    with open(os.path.join(output_dir, "404.html"), "r", encoding="utf-8") as f:
        content = f.read()

    assert "Try searching for what you need:" in content
    assert "Search documentation</button>" in content
    assert "search-dialog" in content


def test_404_contains_popular_page_links(project_dir):
    """404.html contains a 'Popular pages' section with links to nav items."""
    docs_dir = os.path.join(project_dir, "docs")
    with open(os.path.join(docs_dir, "guide.md"), "w", encoding="utf-8") as f:
        f.write("# Guide\n\nContent.\n")
    with open(os.path.join(docs_dir, "api.md"), "w", encoding="utf-8") as f:
        f.write("# API\n\nAPI docs.\n")

    build(str(project_dir))

    output_dir = os.path.join(project_dir, "docs", "_build")
    with open(os.path.join(output_dir, "404.html"), "r", encoding="utf-8") as f:
        content = f.read()

    assert "Popular pages" in content
    assert "guide.html" in content
    assert "api.html" in content
    assert "index.html" in content


# --- Wave 3 Phase 0: Pygments build-time syntax highlighting ---


def test_pygments_code_blocks_have_spans(project_dir):
    """Code blocks with language annotation contain Pygments-generated <span> elements."""
    docs_dir = os.path.join(project_dir, "docs")
    with open(os.path.join(docs_dir, "index.md"), "w", encoding="utf-8") as f:
        f.write("# Test\n\n```python\ndef hello():\n    return 42\n```\n")

    build(str(project_dir))

    output_dir = os.path.join(project_dir, "docs", "_build")
    with open(os.path.join(output_dir, "index.html"), "r", encoding="utf-8") as f:
        content = f.read()

    # Pygments wraps tokens in <span> elements with short class names
    # such as "k" (keyword), "n" (name), "nf" (function name), etc.
    from selfdoc.html import HAS_PYGMENTS
    if HAS_PYGMENTS:
        assert 'class="k"' in content or 'class="kd"' in content
        assert "<span" in content
    else:
        # Without Pygments, code is plain-text escaped
        assert "def hello():" in content


def test_code_blocks_without_lang_are_plain(project_dir):
    """Code blocks without language annotation do not contain Pygments spans."""
    docs_dir = os.path.join(project_dir, "docs")
    with open(os.path.join(docs_dir, "index.md"), "w", encoding="utf-8") as f:
        f.write("# Test\n\n```\nplain text here\n```\n")

    build(str(project_dir))

    output_dir = os.path.join(project_dir, "docs", "_build")
    with open(os.path.join(output_dir, "index.html"), "r", encoding="utf-8") as f:
        content = f.read()

    # Find the code block content -- no Pygments class spans should appear
    code_match = re.search(r"<code>(.*?)</code>", content, re.DOTALL)
    assert code_match is not None
    code_content = code_match.group(1)
    assert 'class="' not in code_content
    assert "plain text here" in code_content


def test_diff_code_blocks_still_work(project_dir):
    """Diff code blocks still have .line-add and .line-remove spans."""
    docs_dir = os.path.join(project_dir, "docs")
    with open(os.path.join(docs_dir, "index.md"), "w", encoding="utf-8") as f:
        f.write("# Test\n\n```diff\n+added line\n-removed line\n same line\n```\n")

    build(str(project_dir))

    output_dir = os.path.join(project_dir, "docs", "_build")
    with open(os.path.join(output_dir, "index.html"), "r", encoding="utf-8") as f:
        content = f.read()

    assert 'class="line line-add"' in content
    assert 'class="line line-remove"' in content


def test_style_css_contains_pygments_rules(project_dir):
    """style.css contains Pygments CSS rules when Pygments is available."""
    build(str(project_dir))

    output_dir = os.path.join(project_dir, "docs", "_build")
    with open(os.path.join(output_dir, "style.css"), "r", encoding="utf-8") as f:
        content = f.read()

    from selfdoc.html import HAS_PYGMENTS
    if HAS_PYGMENTS:
        assert ".code-block code" in content
        # CSS is minified, so spaces around colon are removed
        assert "prefers-color-scheme:dark" in content


def test_no_highlight_js_in_built_html(project_dir):
    """Built HTML does NOT contain any highlight.js references."""
    docs_dir = os.path.join(project_dir, "docs")
    with open(os.path.join(docs_dir, "index.md"), "w", encoding="utf-8") as f:
        f.write("# Test\n\n```python\nprint('hi')\n```\n")

    build(str(project_dir))

    output_dir = os.path.join(project_dir, "docs", "_build")
    with open(os.path.join(output_dir, "index.html"), "r", encoding="utf-8") as f:
        content = f.read()

    assert "highlight.min.js" not in content
    assert "hljs.highlightAll()" not in content
    assert "hljs-light" not in content
    assert "hljs-dark" not in content


# --- Phase 3.1: Build-time CSS, JS, and HTML minification ---


def test_minify_css_removes_comments():
    """_minify_css removes CSS comments."""
    css = "body { /* page background */ color: red; }"
    result = _minify_css(css)
    assert "/* page background */" not in result
    assert "color" in result


def test_minify_css_collapses_whitespace():
    """_minify_css collapses whitespace and removes spaces around symbols."""
    css = "body  {\n  color :  red ;\n  margin : 0 ;\n}\n"
    result = _minify_css(css)
    assert "  " not in result
    assert "\n" not in result
    assert "color:red" in result


def test_minify_css_removes_trailing_semicolons():
    """_minify_css removes trailing semicolons before }."""
    css = "body { color: red; margin: 0; }"
    result = _minify_css(css)
    assert ";}" not in result
    assert "margin:0}" in result


def test_minify_js_removes_comments():
    """_minify_js removes single-line and multi-line comments."""
    js = "/* header */\nvar x = 1;\n// set y\nvar y = 2;\n"
    result = _minify_js(js)
    assert "/* header */" not in result
    assert "set y" not in result
    assert "x" in result
    assert "y" in result


def test_minify_js_preserves_urls():
    """_minify_js does not break URLs containing //."""
    js = "var url = 'https://example.com/path';\n"
    result = _minify_js(js)
    assert "https://example.com/path" in result


def test_minify_html_removes_comments():
    """_minify_html removes HTML comments."""
    html = "<div><!-- a comment --><p>text</p></div>"
    result = _minify_html(html)
    assert "<!-- a comment -->" not in result
    assert "<p>text</p>" in result


def test_minify_html_preserves_pre_content():
    """_minify_html preserves whitespace inside <pre> tags."""
    html = '<p>  hello  </p>\n<pre>  line1\n  line2  </pre>\n<p>world</p>'
    result = _minify_html(html)
    # Whitespace inside <pre> must be kept verbatim
    assert "  line1\n  line2  " in result
    # Whitespace outside <pre> may be collapsed
    assert "\n<p>" not in result or "> <p>" in result


def test_minify_html_preserves_code_content():
    """_minify_html preserves whitespace inside <code> tags."""
    html = '<code>  a  +  b  </code>'
    result = _minify_html(html)
    assert "  a  +  b  " in result


def test_built_style_css_is_minified(project_dir):
    """Built style.css is smaller than the raw theme CSS (minification applied)."""
    from selfdoc.html import get_css, generate_pygments_css
    raw_css = get_css("minimal")
    pygments_css = generate_pygments_css()
    if pygments_css:
        raw_css = raw_css + "\n\n/* Pygments syntax highlighting */\n" + pygments_css

    build(str(project_dir))

    output_dir = os.path.join(project_dir, "docs", "_build")
    with open(os.path.join(output_dir, "style.css"), "r", encoding="utf-8") as f:
        built_css = f.read()

    assert len(built_css) < len(raw_css), (
        f"Minified CSS ({len(built_css)} bytes) should be smaller "
        f"than raw CSS ({len(raw_css)} bytes)"
    )


def test_built_html_has_no_html_comments(project_dir):
    """Built HTML has no <!-- ... --> comments."""
    build(str(project_dir))

    output_dir = os.path.join(project_dir, "docs", "_build")
    with open(os.path.join(output_dir, "index.html"), "r", encoding="utf-8") as f:
        content = f.read()

    assert "<!--" not in content


# --- Phase 3.2: Critical CSS inlining ---


def test_built_html_contains_inline_style_block(project_dir):
    """Built HTML contains a <style> block with critical CSS inlined in <head>."""
    build(str(project_dir))

    output_dir = os.path.join(project_dir, "docs", "_build")
    with open(os.path.join(output_dir, "index.html"), "r", encoding="utf-8") as f:
        content = f.read()

    assert "<style>" in content
    assert "</style>" in content


def test_built_html_loads_stylesheet_async(project_dir):
    """Built HTML loads the full stylesheet asynchronously via media="print" onload."""
    build(str(project_dir))

    output_dir = os.path.join(project_dir, "docs", "_build")
    with open(os.path.join(output_dir, "index.html"), "r", encoding="utf-8") as f:
        content = f.read()

    assert 'media="print"' in content
    assert "onload=\"this.media='all'\"" in content


def test_built_html_has_noscript_fallback(project_dir):
    """Built HTML has a <noscript> fallback for the full stylesheet."""
    build(str(project_dir))

    output_dir = os.path.join(project_dir, "docs", "_build")
    with open(os.path.join(output_dir, "index.html"), "r", encoding="utf-8") as f:
        content = f.read()

    assert "<noscript>" in content
    assert '<link rel="stylesheet" href="style.css">' in content


def test_critical_css_contains_root_variables(project_dir):
    """Critical CSS inlined in HTML contains :root custom properties."""
    build(str(project_dir))

    output_dir = os.path.join(project_dir, "docs", "_build")
    with open(os.path.join(output_dir, "index.html"), "r", encoding="utf-8") as f:
        content = f.read()

    # Extract the <style> block content
    style_match = re.search(r"<style>(.*?)</style>", content, re.DOTALL)
    assert style_match is not None
    style_content = style_match.group(1)

    assert ":root" in style_content
    assert "--bg" in style_content


def test_critical_css_contains_layout(project_dir):
    """Critical CSS inlined in HTML contains .layout grid styles."""
    build(str(project_dir))

    output_dir = os.path.join(project_dir, "docs", "_build")
    with open(os.path.join(output_dir, "index.html"), "r", encoding="utf-8") as f:
        content = f.read()

    style_match = re.search(r"<style>(.*?)</style>", content, re.DOTALL)
    assert style_match is not None
    style_content = style_match.group(1)

    assert ".layout" in style_content


def test_critical_css_excludes_admonition(project_dir):
    """Critical CSS does NOT contain .admonition styles."""
    build(str(project_dir))

    output_dir = os.path.join(project_dir, "docs", "_build")
    with open(os.path.join(output_dir, "index.html"), "r", encoding="utf-8") as f:
        content = f.read()

    style_match = re.search(r"<style>(.*?)</style>", content, re.DOTALL)
    assert style_match is not None
    style_content = style_match.group(1)

    assert ".admonition" not in style_content


def test_critical_css_excludes_print_styles(project_dir):
    """Critical CSS does NOT contain @media print styles."""
    build(str(project_dir))

    output_dir = os.path.join(project_dir, "docs", "_build")
    with open(os.path.join(output_dir, "index.html"), "r", encoding="utf-8") as f:
        content = f.read()

    style_match = re.search(r"<style>(.*?)</style>", content, re.DOTALL)
    assert style_match is not None
    style_content = style_match.group(1)

    # Minified CSS: @media print becomes @media print (no space stripped)
    assert "@media print" not in style_content


def test_extract_critical_css_splits_on_marker():
    """_extract_critical_css splits CSS at the NON-CRITICAL marker."""
    css = ":root { --bg: #fff; }\n/* --- NON-CRITICAL --- */\n.admonition { color: red; }"
    critical, full = _extract_critical_css(css)

    assert ":root" in critical
    assert ".admonition" not in critical
    assert ":root" in full
    assert ".admonition" in full


def test_extract_critical_css_no_marker():
    """_extract_critical_css returns full CSS as critical when no marker exists."""
    css = ":root { --bg: #fff; }\n.admonition { color: red; }"
    critical, full = _extract_critical_css(css)

    assert critical == full


# --- Phase 3.3: Image fetchpriority and width/height ---


def _make_minimal_png(width, height):
    """Create a minimal valid PNG file content with the given dimensions.

    Produces a valid PNG with an IHDR chunk (dimensions encoded in bytes
    16-23) followed by a minimal IDAT and IEND. The image data is a single
    transparent pixel row repeated, but the important part is the header.
    """
    import zlib

    # PNG signature
    sig = b"\x89PNG\r\n\x1a\n"

    # IHDR chunk: width(4) + height(4) + bit_depth(1) + color_type(1)
    #             + compression(1) + filter(1) + interlace(1) = 13 bytes
    ihdr_data = struct.pack(">II", width, height) + b"\x08\x02\x00\x00\x00"
    ihdr_crc = struct.pack(">I", zlib.crc32(b"IHDR" + ihdr_data) & 0xFFFFFFFF)
    ihdr = struct.pack(">I", 13) + b"IHDR" + ihdr_data + ihdr_crc

    # IDAT chunk: minimal compressed image data (one row of zeros)
    raw_data = b"\x00" + b"\x00" * (width * 3)  # filter byte + RGB pixels
    raw_rows = raw_data * height
    compressed = zlib.compress(raw_rows)
    idat_crc = struct.pack(">I", zlib.crc32(b"IDAT" + compressed) & 0xFFFFFFFF)
    idat = struct.pack(">I", len(compressed)) + b"IDAT" + compressed + idat_crc

    # IEND chunk
    iend_crc = struct.pack(">I", zlib.crc32(b"IEND") & 0xFFFFFFFF)
    iend = struct.pack(">I", 0) + b"IEND" + iend_crc

    return sig + ihdr + idat + iend


def _make_minimal_gif(width, height):
    """Create a minimal valid GIF file content with the given dimensions.

    GIF header: signature(3) + version(3) + width(2 LE) + height(2 LE)
    followed by minimal global color table and trailer.
    """
    # GIF89a header
    header = b"GIF89a"
    dims = struct.pack("<HH", width, height)
    # Packed field: no global color table, color resolution=1, not sorted, size=0
    packed = b"\x00"
    bg_color = b"\x00"
    aspect = b"\x00"
    trailer = b"\x3b"  # GIF trailer
    return header + dims + packed + bg_color + aspect + trailer


def test_first_image_gets_fetchpriority_high():
    """The first image in md_to_html output gets fetchpriority='high' and loading='eager'."""
    md = "![first](a.png)\n\n![second](b.png)"
    result = md_to_html(md)

    # First image: eager with high priority
    assert 'fetchpriority="high"' in result
    assert 'loading="eager"' in result
    # Second image: still lazy
    assert 'loading="lazy"' in result


def test_subsequent_images_keep_lazy():
    """Images after the first one retain loading='lazy' without fetchpriority."""
    md = "![one](a.png)\n\n![two](b.png)\n\n![three](c.png)"
    result = md_to_html(md)

    # Count occurrences
    assert result.count('loading="lazy"') == 2
    assert result.count('fetchpriority="high"') == 1
    assert result.count('loading="eager"') == 1


def test_single_image_gets_fetchpriority():
    """A page with only one image still gets fetchpriority='high'."""
    md = "# Title\n\n![logo](logo.png)"
    result = md_to_html(md)

    assert 'fetchpriority="high"' in result
    assert 'loading="eager"' in result
    assert 'loading="lazy"' not in result


def test_no_images_no_fetchpriority():
    """A page with no images does not contain fetchpriority attributes."""
    md = "# Title\n\nJust text."
    result = md_to_html(md)

    assert "fetchpriority" not in result
    assert 'loading="eager"' not in result
    assert 'loading="lazy"' not in result


def test_png_image_gets_width_height(tmp_path):
    """PNG images get width and height attributes added by _add_image_dimensions."""
    # Create a 42x17 PNG in the docs dir
    docs_dir = str(tmp_path)
    png_path = os.path.join(docs_dir, "logo.png")
    with open(png_path, "wb") as f:
        f.write(_make_minimal_png(42, 17))

    html = '<p><img src="logo.png" alt="Logo" loading="lazy"></p>'
    result = _add_image_dimensions(html, docs_dir, "index.md")

    assert 'width="42"' in result
    assert 'height="17"' in result


def test_gif_image_gets_width_height(tmp_path):
    """GIF images get width and height attributes added by _add_image_dimensions."""
    docs_dir = str(tmp_path)
    gif_path = os.path.join(docs_dir, "anim.gif")
    with open(gif_path, "wb") as f:
        f.write(_make_minimal_gif(100, 50))

    html = '<p><img src="anim.gif" alt="Animation" loading="lazy"></p>'
    result = _add_image_dimensions(html, docs_dir, "index.md")

    assert 'width="100"' in result
    assert 'height="50"' in result


def test_non_image_files_not_affected(tmp_path):
    """Non-image src values are not modified by _add_image_dimensions."""
    docs_dir = str(tmp_path)
    # Create a .txt file (not an image)
    txt_path = os.path.join(docs_dir, "data.txt")
    with open(txt_path, "w") as f:
        f.write("hello")

    html = '<p><img src="data.txt" alt="data" loading="lazy"></p>'
    result = _add_image_dimensions(html, docs_dir, "index.md")

    assert "width=" not in result
    assert "height=" not in result


def test_external_images_not_affected(tmp_path):
    """External (http/https) image URLs are not modified."""
    docs_dir = str(tmp_path)
    html = '<p><img src="https://example.com/img.png" alt="ext" loading="lazy"></p>'
    result = _add_image_dimensions(html, docs_dir, "index.md")

    assert "width=" not in result
    assert "height=" not in result


def test_missing_image_file_not_affected(tmp_path):
    """Images referencing non-existent files are not modified."""
    docs_dir = str(tmp_path)
    html = '<p><img src="missing.png" alt="gone" loading="lazy"></p>'
    result = _add_image_dimensions(html, docs_dir, "index.md")

    assert "width=" not in result
    assert "height=" not in result


def test_build_adds_png_dimensions(project_dir):
    """Full build pipeline adds width/height to images referencing PNG files in docs/."""
    docs_dir = os.path.join(project_dir, "docs")

    # Create a 10x20 PNG
    png_path = os.path.join(docs_dir, "photo.png")
    with open(png_path, "wb") as f:
        f.write(_make_minimal_png(10, 20))

    # Reference the image in a markdown page
    with open(os.path.join(docs_dir, "index.md"), "w", encoding="utf-8") as f:
        f.write("# Test\n\n![photo](photo.png)\n")

    build(str(project_dir))

    output_dir = os.path.join(project_dir, "docs", "_build")
    with open(os.path.join(output_dir, "index.html"), "r", encoding="utf-8") as f:
        content = f.read()

    assert 'width="10"' in content
    assert 'height="20"' in content


# --- Phase 0B: JPEG and WebP image dimension parsing ---


def _make_minimal_jpeg(width, height):
    """Create a minimal valid JPEG file content with the given dimensions.

    Produces a valid JPEG with SOI marker, a SOF0 frame header containing
    the dimensions, and an EOI marker. Not a displayable image, but has
    valid structure for dimension parsing.
    """
    soi = b"\xff\xd8"
    # SOF0 marker: \xff\xc0
    # Segment length: 2 bytes (includes itself) = 8 for our minimal frame
    # Precision: 1 byte (8 bits)
    # Height: 2 bytes BE
    # Width: 2 bytes BE
    # Number of components: 1 byte (1 = grayscale)
    # Component spec: 3 bytes (id, sampling, quant table)
    sof_data = struct.pack(">H", 11)  # length = 11 (2+1+2+2+1+3)
    sof_data += struct.pack("B", 8)  # precision
    sof_data += struct.pack(">H", height)
    sof_data += struct.pack(">H", width)
    sof_data += struct.pack("B", 1)  # 1 component
    sof_data += b"\x01\x11\x00"  # component spec
    sof = b"\xff\xc0" + sof_data
    eoi = b"\xff\xd9"
    return soi + sof + eoi


def _make_minimal_webp_lossy(width, height):
    """Create a minimal valid lossy WebP (VP8) file content.

    The VP8 bitstream header at bytes 26-29 encodes width and height
    as little-endian uint16 values (lower 14 bits used).
    """
    # VP8 bitstream: starts with 3-byte frame tag + 3-byte sync code
    # then 2-byte width (LE) + 2-byte height (LE)
    # Frame tag: keyframe (bit 0=0), version=0, show_frame=1, partition_size
    frame_tag = b"\x9d\x01\x2a"  # sync code for VP8 keyframe
    # We need bytes 0-25 to be the RIFF+WEBP+VP8 header, then 26-29 for dims
    # Total VP8 chunk data: frame_tag(3) + sync(3) + width(2) + height(2) = 10 min
    vp8_payload = b"\x00\x00\x00"  # 3-byte frame tag (keyframe, version 0)
    vp8_payload += frame_tag  # sync code
    vp8_payload += struct.pack("<H", width & 0x3FFF)
    vp8_payload += struct.pack("<H", height & 0x3FFF)

    chunk = b"VP8 " + struct.pack("<I", len(vp8_payload)) + vp8_payload
    file_size = 4 + len(chunk)  # "WEBP" + chunk
    return b"RIFF" + struct.pack("<I", file_size) + b"WEBP" + chunk


def _make_minimal_webp_lossless(width, height):
    """Create a minimal valid lossless WebP (VP8L) file content.

    The VP8L header at byte 21 encodes a uint32 where bits 0-13 = width-1
    and bits 14-27 = height-1.
    """
    # VP8L signature byte: 0x2f, then 4-byte LE uint32 with packed dims
    sig_byte = b"\x2f"
    bits = ((width - 1) & 0x3FFF) | (((height - 1) & 0x3FFF) << 14)
    packed = struct.pack("<I", bits)
    vp8l_payload = sig_byte + packed

    chunk = b"VP8L" + struct.pack("<I", len(vp8l_payload)) + vp8l_payload
    file_size = 4 + len(chunk)
    return b"RIFF" + struct.pack("<I", file_size) + b"WEBP" + chunk


def _make_minimal_webp_extended(width, height):
    """Create a minimal valid extended WebP (VP8X) file content.

    VP8X chunk at bytes 24-29 encodes width-1 and height-1 as uint24 LE.
    """
    # VP8X chunk: 10 bytes of data
    # Flags (4 bytes) + canvas width-1 (3 bytes LE) + canvas height-1 (3 bytes LE)
    flags = b"\x00\x00\x00\x00"
    w_bytes = (width - 1).to_bytes(3, "little")
    h_bytes = (height - 1).to_bytes(3, "little")
    vp8x_payload = flags + w_bytes + h_bytes

    chunk = b"VP8X" + struct.pack("<I", len(vp8x_payload)) + vp8x_payload
    file_size = 4 + len(chunk)
    return b"RIFF" + struct.pack("<I", file_size) + b"WEBP" + chunk


def test_jpeg_dimensions_basic(tmp_path):
    """JPEG reader returns correct dimensions for a valid JPEG file."""
    jpeg_path = os.path.join(tmp_path, "test.jpg")
    with open(jpeg_path, "wb") as f:
        f.write(_make_minimal_jpeg(320, 240))

    result = _read_jpeg_dimensions(jpeg_path)
    assert result == (320, 240)


def test_jpeg_dimensions_invalid_soi(tmp_path):
    """JPEG reader returns None for a file without a valid SOI marker."""
    bad_path = os.path.join(tmp_path, "bad.jpg")
    with open(bad_path, "wb") as f:
        f.write(b"\x00\x00\x00\x00")

    assert _read_jpeg_dimensions(bad_path) is None


def test_jpeg_dimensions_truncated(tmp_path):
    """JPEG reader returns None for a truncated file."""
    trunc_path = os.path.join(tmp_path, "trunc.jpg")
    with open(trunc_path, "wb") as f:
        f.write(b"\xff\xd8\xff\xc0")  # SOI + SOF0 marker, but no data

    assert _read_jpeg_dimensions(trunc_path) is None


def test_jpeg_dimensions_nonexistent():
    """JPEG reader returns None for a nonexistent file."""
    assert _read_jpeg_dimensions("/nonexistent/test.jpg") is None


def test_jpeg_image_gets_width_height(tmp_path):
    """JPEG images get width and height attributes via _add_image_dimensions."""
    docs_dir = str(tmp_path)
    jpeg_path = os.path.join(docs_dir, "photo.jpg")
    with open(jpeg_path, "wb") as f:
        f.write(_make_minimal_jpeg(800, 600))

    html = '<p><img src="photo.jpg" alt="Photo" loading="lazy"></p>'
    result = _add_image_dimensions(html, docs_dir, "index.md")

    assert 'width="800"' in result
    assert 'height="600"' in result


def test_jpeg_extension_case_insensitive(tmp_path):
    """JPEG reader works with .jpeg extension too."""
    docs_dir = str(tmp_path)
    jpeg_path = os.path.join(docs_dir, "photo.jpeg")
    with open(jpeg_path, "wb") as f:
        f.write(_make_minimal_jpeg(640, 480))

    html = '<p><img src="photo.jpeg" alt="Photo" loading="lazy"></p>'
    result = _add_image_dimensions(html, docs_dir, "index.md")

    assert 'width="640"' in result
    assert 'height="480"' in result


def test_webp_lossy_dimensions(tmp_path):
    """WebP reader returns correct dimensions for a lossy VP8 file."""
    webp_path = os.path.join(tmp_path, "test.webp")
    with open(webp_path, "wb") as f:
        f.write(_make_minimal_webp_lossy(200, 150))

    result = _read_webp_dimensions(webp_path)
    assert result == (200, 150)


def test_webp_lossless_dimensions(tmp_path):
    """WebP reader returns correct dimensions for a lossless VP8L file."""
    webp_path = os.path.join(tmp_path, "test.webp")
    with open(webp_path, "wb") as f:
        f.write(_make_minimal_webp_lossless(100, 75))

    result = _read_webp_dimensions(webp_path)
    assert result == (100, 75)


def test_webp_extended_dimensions(tmp_path):
    """WebP reader returns correct dimensions for an extended VP8X file."""
    webp_path = os.path.join(tmp_path, "test.webp")
    with open(webp_path, "wb") as f:
        f.write(_make_minimal_webp_extended(1920, 1080))

    result = _read_webp_dimensions(webp_path)
    assert result == (1920, 1080)


def test_webp_invalid_header(tmp_path):
    """WebP reader returns None for a file without a valid RIFF/WEBP header."""
    bad_path = os.path.join(tmp_path, "bad.webp")
    with open(bad_path, "wb") as f:
        f.write(b"\x00\x00\x00\x00" * 8)

    assert _read_webp_dimensions(bad_path) is None


def test_webp_truncated(tmp_path):
    """WebP reader returns None for a truncated file."""
    trunc_path = os.path.join(tmp_path, "trunc.webp")
    with open(trunc_path, "wb") as f:
        f.write(b"RIFF\x00\x00\x00\x00WEBP")  # Valid header but too short

    assert _read_webp_dimensions(trunc_path) is None


def test_webp_nonexistent():
    """WebP reader returns None for a nonexistent file."""
    assert _read_webp_dimensions("/nonexistent/test.webp") is None


def test_webp_image_gets_width_height(tmp_path):
    """WebP images get width and height attributes via _add_image_dimensions."""
    docs_dir = str(tmp_path)
    webp_path = os.path.join(docs_dir, "photo.webp")
    with open(webp_path, "wb") as f:
        f.write(_make_minimal_webp_lossy(400, 300))

    html = '<p><img src="photo.webp" alt="Photo" loading="lazy"></p>'
    result = _add_image_dimensions(html, docs_dir, "index.md")

    assert 'width="400"' in result
    assert 'height="300"' in result


# --- Phase 3.4: ARIA attributes for code tabs and search ---


def test_code_tabs_aria_tablist():
    """Code tabs have role='tablist' on the tab bar."""
    md = "```python\nprint('hi')\n```\n```go\nfmt.Println()\n```\n"
    result = md_to_html(md)

    assert 'role="tablist"' in result


def test_code_tabs_aria_tab_roles():
    """Code tab buttons have role='tab' and aria-selected attributes."""
    md = "```python\nprint('hi')\n```\n```go\nfmt.Println()\n```\n"
    result = md_to_html(md)

    assert 'role="tab"' in result
    assert 'aria-selected="true"' in result
    assert 'aria-selected="false"' in result


def test_code_tabs_aria_controls():
    """Code tab buttons have aria-controls pointing to panel ids."""
    md = "```python\nprint('hi')\n```\n```go\nfmt.Println()\n```\n"
    result = md_to_html(md)

    assert 'aria-controls="panel-python"' in result
    assert 'aria-controls="panel-go"' in result


def test_code_tabs_aria_tabpanel():
    """Code tab panels have role='tabpanel', id, and aria-labelledby."""
    md = "```python\nprint('hi')\n```\n```go\nfmt.Println()\n```\n"
    result = md_to_html(md)

    assert 'role="tabpanel"' in result
    assert 'id="panel-python"' in result
    assert 'id="panel-go"' in result
    assert 'aria-labelledby="tab-python"' in result
    assert 'aria-labelledby="tab-go"' in result


def test_code_tabs_aria_tab_ids():
    """Code tab buttons have id attributes for aria-labelledby references."""
    md = "```python\nprint('hi')\n```\n```go\nfmt.Println()\n```\n"
    result = md_to_html(md)

    assert 'id="tab-python"' in result
    assert 'id="tab-go"' in result


def test_search_dialog_aria_listbox():
    """Search results list has role='listbox' and id='search-results'."""
    html_files = generate_html(
        {"index.md": "# Test\n\nContent.\n"},
        project_name="Test",
    )
    content = html_files["index.html"]

    assert 'role="listbox"' in content
    assert 'id="search-results"' in content


def test_search_input_aria_controls():
    """Search input has aria-controls='search-results'."""
    html_files = generate_html(
        {"index.md": "# Test\n\nContent.\n"},
        project_name="Test",
    )
    content = html_files["index.html"]

    assert 'aria-controls="search-results"' in content


# --- ItemList JSON-LD via frontmatter schema flag ---


def test_itemlist_jsonld_with_schema_frontmatter(project_dir):
    """A page with schema: itemlist frontmatter gets ItemList JSON-LD."""
    config_path = os.path.join(project_dir, "selfdoc.json")
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
    config["base_url"] = "https://example.com"
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f)

    docs_dir = os.path.join(project_dir, "docs")
    with open(os.path.join(docs_dir, "features.md"), "w", encoding="utf-8") as f:
        f.write(
            "---\nschema: itemlist\n---\n"
            "# Features\n\n"
            "- Alpha feature\n"
            "- Beta feature\n"
            "- Gamma feature\n"
        )

    build(str(project_dir))

    output_dir = os.path.join(project_dir, "docs", "_build")
    with open(os.path.join(output_dir, "features.html"), "r", encoding="utf-8") as f:
        content = f.read()

    assert '"ItemList"' in content
    assert '"ListItem"' in content


def test_itemlist_jsonld_contains_correct_items(project_dir):
    """ItemList JSON-LD contains the correct list items from the page."""
    config_path = os.path.join(project_dir, "selfdoc.json")
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
    config["base_url"] = "https://example.com"
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f)

    docs_dir = os.path.join(project_dir, "docs")
    with open(os.path.join(docs_dir, "features.md"), "w", encoding="utf-8") as f:
        f.write(
            "---\nschema: itemlist\n---\n"
            "# Features\n\n"
            "1. First item\n"
            "2. Second item\n"
            "3. Third item\n"
        )

    build(str(project_dir))

    output_dir = os.path.join(project_dir, "docs", "_build")
    with open(os.path.join(output_dir, "features.html"), "r", encoding="utf-8") as f:
        content = f.read()

    # Extract the ItemList JSON-LD block
    ld_blocks = re.findall(
        r'<script type="application/ld\+json">\s*(.*?)\s*</script>',
        content,
        re.DOTALL,
    )
    item_list_data = None
    for block in ld_blocks:
        data = json.loads(block)
        if data.get("@type") == "ItemList":
            item_list_data = data
            break

    assert item_list_data is not None, "ItemList JSON-LD not found"
    elements = item_list_data["itemListElement"]
    assert len(elements) == 3
    assert elements[0]["position"] == 1
    assert elements[0]["name"] == "First item"
    assert elements[1]["position"] == 2
    assert elements[1]["name"] == "Second item"
    assert elements[2]["position"] == 3
    assert elements[2]["name"] == "Third item"


def test_no_itemlist_jsonld_without_schema_frontmatter(project_dir):
    """A page WITHOUT schema: itemlist does NOT get ItemList JSON-LD."""
    config_path = os.path.join(project_dir, "selfdoc.json")
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
    config["base_url"] = "https://example.com"
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f)

    docs_dir = os.path.join(project_dir, "docs")
    with open(os.path.join(docs_dir, "index.md"), "w", encoding="utf-8") as f:
        f.write("# Test\n\n- Item one\n- Item two\n")

    build(str(project_dir))

    output_dir = os.path.join(project_dir, "docs", "_build")
    with open(os.path.join(output_dir, "index.html"), "r", encoding="utf-8") as f:
        content = f.read()

    assert '"ItemList"' not in content


# --- :::glossary directive ---


def test_glossary_directive_resolves_to_dl(project_dir):
    """:::glossary directive resolves to HTML with <dl>, <dt>, <dfn>, <dd>."""
    docs_dir = os.path.join(project_dir, "docs")
    with open(os.path.join(docs_dir, "glossary.md"), "w", encoding="utf-8") as f:
        f.write(
            "# Glossary\n\n"
            ":::glossary\n"
            "**API**: Application Programming Interface\n"
            "**SDK**: Software Development Kit\n"
            ":::\n"
        )

    build(str(project_dir))

    output_dir = os.path.join(project_dir, "docs", "_build")
    with open(os.path.join(output_dir, "glossary.html"), "r", encoding="utf-8") as f:
        content = f.read()

    assert '<div class="glossary">' in content
    assert "<dl>" in content
    assert "<dt><dfn>API</dfn></dt>" in content
    assert "<dd>Application Programming Interface</dd>" in content
    assert "<dt><dfn>SDK</dfn></dt>" in content
    assert "<dd>Software Development Kit</dd>" in content


def test_glossary_defined_term_set_jsonld_with_base_url(project_dir):
    """DefinedTermSet JSON-LD is emitted when glossary is present and base_url is set."""
    config_path = os.path.join(project_dir, "selfdoc.json")
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
    config["base_url"] = "https://example.com"
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f)

    docs_dir = os.path.join(project_dir, "docs")
    with open(os.path.join(docs_dir, "glossary.md"), "w", encoding="utf-8") as f:
        f.write(
            "# Terms\n\n"
            ":::glossary\n"
            "**API**: Application Programming Interface\n"
            "**CLI**: Command Line Interface\n"
            ":::\n"
        )

    build(str(project_dir))

    output_dir = os.path.join(project_dir, "docs", "_build")
    with open(os.path.join(output_dir, "glossary.html"), "r", encoding="utf-8") as f:
        content = f.read()

    assert '"DefinedTermSet"' in content

    # Extract and validate the JSON-LD block
    ld_blocks = re.findall(
        r'<script type="application/ld\+json">\s*(.*?)\s*</script>',
        content,
        re.DOTALL,
    )
    term_set_data = None
    for block in ld_blocks:
        data = json.loads(block)
        if data.get("@type") == "DefinedTermSet":
            term_set_data = data
            break

    assert term_set_data is not None, "DefinedTermSet JSON-LD not found"
    assert term_set_data["name"] == "Terms Glossary"
    terms = term_set_data["hasDefinedTerm"]
    assert len(terms) == 2
    assert terms[0]["@type"] == "DefinedTerm"
    assert terms[0]["name"] == "API"
    assert terms[0]["description"] == "Application Programming Interface"
    assert terms[1]["name"] == "CLI"
    assert terms[1]["description"] == "Command Line Interface"


def test_glossary_integration_end_to_end(project_dir):
    """End-to-end: :::glossary directive produces HTML and DefinedTermSet JSON-LD."""
    docs_dir = os.path.join(project_dir, "docs")
    with open(os.path.join(docs_dir, "index.md"), "w", encoding="utf-8") as f:
        f.write(
            "# Glossary\n\n"
            ":::glossary\n"
            "**Directive**: A special block in Markdown templates\n"
            "**Extractor**: A language-specific code parser\n"
            "**Resolver**: The factory that dispatches directives\n"
            ":::\n"
        )

    build(str(project_dir))

    output_dir = os.path.join(project_dir, "docs", "_build")
    with open(os.path.join(output_dir, "index.html"), "r", encoding="utf-8") as f:
        content = f.read()

    # Verify glossary HTML structure
    assert '<div class="glossary">' in content
    assert "<dl>" in content
    assert "<dt><dfn>Directive</dfn></dt>" in content
    assert "<dd>A special block in Markdown templates</dd>" in content
    assert "<dt><dfn>Extractor</dfn></dt>" in content
    assert "<dd>A language-specific code parser</dd>" in content
    assert "<dt><dfn>Resolver</dfn></dt>" in content
    assert "<dd>The factory that dispatches directives</dd>" in content

    # Verify DefinedTermSet JSON-LD
    assert '<script type="application/ld+json">' in content
    assert '"DefinedTermSet"' in content

    ld_blocks = re.findall(
        r'<script type="application/ld\+json">\s*(.*?)\s*</script>',
        content,
        re.DOTALL,
    )
    term_set_data = None
    for block in ld_blocks:
        data = json.loads(block)
        if data.get("@type") == "DefinedTermSet":
            term_set_data = data
            break

    assert term_set_data is not None, "DefinedTermSet JSON-LD not found"
    terms = term_set_data["hasDefinedTerm"]
    assert len(terms) == 3
    term_names = [t["name"] for t in terms]
    assert "Directive" in term_names
    assert "Extractor" in term_names
    assert "Resolver" in term_names
    # Verify descriptions are present
    for t in terms:
        assert t["@type"] == "DefinedTerm"
        assert len(t["description"]) > 0


def test_definition_list_two_terms():
    """Definition list with 2 terms renders correct HTML."""
    md = "Term One\n: Definition of term one\n\nTerm Two\n: Definition of term two\n"
    result = md_to_html(md)

    assert '<div class="glossary">' in result
    assert "<dl>" in result
    assert "<dt><dfn>Term One</dfn></dt>" in result
    assert "<dd>Definition of term one</dd>" in result
    assert "<dt><dfn>Term Two</dfn></dt>" in result
    assert "<dd>Definition of term two</dd>" in result


def test_definition_list_multiple_definitions_per_term():
    """Definition list with multiple definitions for one term."""
    md = "Term One\n: First definition\n: Second definition\n"
    result = md_to_html(md)

    assert "<dt><dfn>Term One</dfn></dt>" in result
    assert "<dd>First definition</dd>" in result
    assert "<dd>Second definition</dd>" in result
    assert result.count("<dt>") == 1
    assert result.count("<dd>") == 2


def test_definition_list_generates_defined_term_set_jsonld(project_dir):
    """DefinedTermSet JSON-LD is auto-generated from definition list syntax (no :::glossary)."""
    docs_dir = os.path.join(project_dir, "docs")
    with open(os.path.join(docs_dir, "index.md"), "w", encoding="utf-8") as f:
        f.write(
            "# Terms\n\n"
            "API\n"
            ": Application Programming Interface\n\n"
            "CLI\n"
            ": Command Line Interface\n"
        )

    build(str(project_dir))

    output_dir = os.path.join(project_dir, "docs", "_build")
    with open(os.path.join(output_dir, "index.html"), "r", encoding="utf-8") as f:
        content = f.read()

    assert '<div class="glossary">' in content
    assert '"DefinedTermSet"' in content

    ld_blocks = re.findall(
        r'<script type="application/ld\+json">\s*(.*?)\s*</script>',
        content,
        re.DOTALL,
    )
    term_set_data = None
    for block in ld_blocks:
        data = json.loads(block)
        if data.get("@type") == "DefinedTermSet":
            term_set_data = data
            break

    assert term_set_data is not None, "DefinedTermSet JSON-LD not found"
    terms = term_set_data["hasDefinedTerm"]
    assert len(terms) == 2
    assert terms[0]["name"] == "API"
    assert terms[0]["description"] == "Application Programming Interface"
    assert terms[1]["name"] == "CLI"
    assert terms[1]["description"] == "Command Line Interface"


def test_definition_list_no_false_match_on_paragraphs():
    """Regular paragraphs near definition lists render correctly (no false matches)."""
    md = (
        "This is a regular paragraph.\n\n"
        "Term\n: Definition\n\n"
        "Another regular paragraph.\n"
    )
    result = md_to_html(md)

    assert "<p>This is a regular paragraph.</p>" in result
    assert "<p>Another regular paragraph.</p>" in result
    assert "<dt><dfn>Term</dfn></dt>" in result
    assert "<dd>Definition</dd>" in result


def test_itemlist_auto_detected_on_list_heavy_page(project_dir):
    """Page with 8 list items and 2 paragraphs gets ItemList JSON-LD automatically."""
    docs_dir = os.path.join(project_dir, "docs")
    with open(os.path.join(docs_dir, "index.md"), "w", encoding="utf-8") as f:
        f.write(
            "# Features\n\n"
            "Overview paragraph.\n\n"
            "- Feature one\n"
            "- Feature two\n"
            "- Feature three\n"
            "- Feature four\n"
            "- Feature five\n"
            "- Feature six\n"
            "- Feature seven\n"
            "- Feature eight\n\n"
            "Closing paragraph.\n"
        )

    build(str(project_dir))

    output_dir = os.path.join(project_dir, "docs", "_build")
    with open(os.path.join(output_dir, "index.html"), "r", encoding="utf-8") as f:
        content = f.read()

    assert '"ItemList"' in content
    assert '"ListItem"' in content

    ld_blocks = re.findall(
        r'<script type="application/ld\+json">\s*(.*?)\s*</script>',
        content,
        re.DOTALL,
    )
    item_list_data = None
    for block in ld_blocks:
        data = json.loads(block)
        if data.get("@type") == "ItemList":
            item_list_data = data
            break

    assert item_list_data is not None, "ItemList JSON-LD not found"
    assert len(item_list_data["itemListElement"]) == 8


def test_itemlist_not_auto_detected_on_paragraph_heavy_page(project_dir):
    """Page with 2 list items and 5 paragraphs does NOT get ItemList."""
    docs_dir = os.path.join(project_dir, "docs")
    with open(os.path.join(docs_dir, "index.md"), "w", encoding="utf-8") as f:
        f.write(
            "# Article\n\n"
            "First paragraph.\n\n"
            "Second paragraph.\n\n"
            "Third paragraph.\n\n"
            "Fourth paragraph.\n\n"
            "Fifth paragraph.\n\n"
            "- Item one\n"
            "- Item two\n"
        )

    build(str(project_dir))

    output_dir = os.path.join(project_dir, "docs", "_build")
    with open(os.path.join(output_dir, "index.html"), "r", encoding="utf-8") as f:
        content = f.read()

    assert '"ItemList"' not in content


def test_itemlist_explicit_schema_still_works(project_dir):
    """Page with explicit schema: itemlist frontmatter still works (no regression)."""
    docs_dir = os.path.join(project_dir, "docs")
    with open(os.path.join(docs_dir, "features.md"), "w", encoding="utf-8") as f:
        f.write(
            "---\nschema: itemlist\n---\n"
            "# Features\n\n"
            "- Alpha\n"
            "- Beta\n"
            "- Gamma\n"
        )

    build(str(project_dir))

    output_dir = os.path.join(project_dir, "docs", "_build")
    with open(os.path.join(output_dir, "features.html"), "r", encoding="utf-8") as f:
        content = f.read()

    assert '"ItemList"' in content


def test_itemlist_not_auto_detected_below_threshold(project_dir):
    """Page with fewer than 5 list items does NOT trigger auto-detection even if li > p."""
    docs_dir = os.path.join(project_dir, "docs")
    with open(os.path.join(docs_dir, "index.md"), "w", encoding="utf-8") as f:
        f.write(
            "# Short List\n\n"
            "- Item one\n"
            "- Item two\n"
            "- Item three\n"
            "- Item four\n"
        )

    build(str(project_dir))

    output_dir = os.path.join(project_dir, "docs", "_build")
    with open(os.path.join(output_dir, "index.html"), "r", encoding="utf-8") as f:
        content = f.read()

    assert '"ItemList"' not in content


# --- Phase 2D: ItemList URL extraction ---


def test_itemlist_extracts_urls_from_links():
    """ListItem entries include 'item' URL when <li> contains <a> link."""
    html_files = generate_html(
        {"index.md": (
            "---\nschema: itemlist\n---\n"
            "# Links\n\n"
            "- [Alpha](https://alpha.com)\n"
            "- [Beta](https://beta.com)\n"
            "- Plain item\n"
        )},
        project_name="Test",
        frontmatter={"index.md": {"schema": "itemlist"}},
    )
    content = html_files["index.html"]

    ld_blocks = re.findall(
        r'<script type="application/ld\+json">\s*(.*?)\s*</script>',
        content,
        re.DOTALL,
    )
    item_list = None
    for block in ld_blocks:
        data = json.loads(block)
        if data.get("@type") == "ItemList":
            item_list = data
            break

    assert item_list is not None, "ItemList JSON-LD not found"
    elements = item_list["itemListElement"]
    # First two have links, third does not
    assert elements[0]["item"] == "https://alpha.com"
    assert elements[1]["item"] == "https://beta.com"
    assert "item" not in elements[2]


def test_itemlist_no_urls_without_links():
    """ListItem entries without <a> links have only name, no item."""
    html_files = generate_html(
        {"index.md": (
            "---\nschema: itemlist\n---\n"
            "# Plain\n\n"
            "- First item\n"
            "- Second item\n"
        )},
        project_name="Test",
        frontmatter={"index.md": {"schema": "itemlist"}},
    )
    content = html_files["index.html"]

    ld_blocks = re.findall(
        r'<script type="application/ld\+json">\s*(.*?)\s*</script>',
        content,
        re.DOTALL,
    )
    item_list = None
    for block in ld_blocks:
        data = json.loads(block)
        if data.get("@type") == "ItemList":
            item_list = data
            break

    assert item_list is not None, "ItemList JSON-LD not found"
    for elem in item_list["itemListElement"]:
        assert "item" not in elem
        assert "name" in elem


def test_glossary_terms_correctly_extracted():
    """Glossary resolver correctly parses terms and definitions."""
    from selfdoc.resolver import _resolve_glossary

    body = [
        "**Router**: Handles HTTP routing",
        "**Middleware**: Intercepts requests",
        "",
        "**Handler**: Processes the request",
    ]
    result = _resolve_glossary(body)

    assert "<dt><dfn>Router</dfn></dt>" in result
    assert "<dd>Handles HTTP routing</dd>" in result
    assert "<dt><dfn>Middleware</dfn></dt>" in result
    assert "<dd>Intercepts requests</dd>" in result
    assert "<dt><dfn>Handler</dfn></dt>" in result
    assert "<dd>Processes the request</dd>" in result
    # Empty lines should be skipped, not produce entries
    assert result.count("<dt>") == 3


def test_tech_article_has_date_published(project_dir):
    """TechArticle JSON-LD includes datePublished field."""
    config_path = os.path.join(project_dir, "selfdoc.json")
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
    config["base_url"] = "https://example.com"
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f)

    docs_dir = os.path.join(project_dir, "docs")
    with open(os.path.join(docs_dir, "index.md"), "w", encoding="utf-8") as f:
        f.write("---\ndate: 2025-01-15\n---\n# Test\n\nContent.\n")

    build(str(project_dir))

    output_dir = os.path.join(project_dir, "docs", "_build")
    with open(os.path.join(output_dir, "index.html"), "r", encoding="utf-8") as f:
        content = f.read()

    ld_blocks = re.findall(
        r'<script type="application/ld\+json">\s*(.*?)\s*</script>',
        content,
        re.DOTALL,
    )
    tech_article = None
    for block in ld_blocks:
        data = json.loads(block)
        if data.get("@type") == "TechArticle":
            tech_article = data
            break

    assert tech_article is not None, "TechArticle JSON-LD not found"
    assert tech_article["datePublished"] == "2025-01-15"


def test_tech_article_has_publisher_organization(project_dir):
    """TechArticle JSON-LD includes publisher with @type Organization."""
    build(str(project_dir))

    output_dir = os.path.join(project_dir, "docs", "_build")
    with open(os.path.join(output_dir, "index.html"), "r", encoding="utf-8") as f:
        content = f.read()

    ld_blocks = re.findall(
        r'<script type="application/ld\+json">\s*(.*?)\s*</script>',
        content,
        re.DOTALL,
    )
    tech_article = None
    for block in ld_blocks:
        data = json.loads(block)
        if data.get("@type") == "TechArticle":
            tech_article = data
            break

    assert tech_article is not None, "TechArticle JSON-LD not found"
    assert "publisher" in tech_article
    assert tech_article["publisher"]["@type"] == "Organization"


def test_tech_article_has_in_language(project_dir):
    """TechArticle JSON-LD includes inLanguage field."""
    build(str(project_dir))

    output_dir = os.path.join(project_dir, "docs", "_build")
    with open(os.path.join(output_dir, "index.html"), "r", encoding="utf-8") as f:
        content = f.read()

    ld_blocks = re.findall(
        r'<script type="application/ld\+json">\s*(.*?)\s*</script>',
        content,
        re.DOTALL,
    )
    tech_article = None
    for block in ld_blocks:
        data = json.loads(block)
        if data.get("@type") == "TechArticle":
            tech_article = data
            break

    assert tech_article is not None, "TechArticle JSON-LD not found"
    assert tech_article["inLanguage"] == "en"


def test_og_site_name_present(project_dir):
    """og:site_name meta tag is present with project name."""
    build(str(project_dir))

    output_dir = os.path.join(project_dir, "docs", "_build")
    with open(os.path.join(output_dir, "index.html"), "r", encoding="utf-8") as f:
        content = f.read()

    # project_name is derived from directory name
    project_name = os.path.basename(str(project_dir))
    assert f'<meta property="og:site_name" content="{project_name}">' in content


def test_twitter_image_present_with_base_url(project_dir):
    """twitter:image meta tag is present when base_url is set."""
    config_path = os.path.join(project_dir, "selfdoc.json")
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
    config["base_url"] = "https://example.com"
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f)

    build(str(project_dir))

    output_dir = os.path.join(project_dir, "docs", "_build")
    with open(os.path.join(output_dir, "index.html"), "r", encoding="utf-8") as f:
        content = f.read()

    assert '<meta name="twitter:image" content="https://example.com/og-index.png">' in content


def test_og_image_dimensions_present(project_dir):
    """og:image:width and og:image:height meta tags are present when base_url is set."""
    config_path = os.path.join(project_dir, "selfdoc.json")
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
    config["base_url"] = "https://example.com"
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f)

    build(str(project_dir))

    output_dir = os.path.join(project_dir, "docs", "_build")
    with open(os.path.join(output_dir, "index.html"), "r", encoding="utf-8") as f:
        content = f.read()

    assert '<meta property="og:image:width" content="1200">' in content
    assert '<meta property="og:image:height" content="630">' in content


def test_twitter_card_summary_large_image_with_base_url(project_dir):
    """twitter:card is summary_large_image when base_url is set (og:image exists)."""
    config_path = os.path.join(project_dir, "selfdoc.json")
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
    config["base_url"] = "https://example.com"
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f)

    build(str(project_dir))

    output_dir = os.path.join(project_dir, "docs", "_build")
    with open(os.path.join(output_dir, "index.html"), "r", encoding="utf-8") as f:
        content = f.read()

    assert '<meta name="twitter:card" content="summary_large_image">' in content


def test_organization_schema_on_index_page(project_dir):
    """Organization JSON-LD schema is present on the index page."""
    build(str(project_dir))

    output_dir = os.path.join(project_dir, "docs", "_build")
    with open(os.path.join(output_dir, "index.html"), "r", encoding="utf-8") as f:
        content = f.read()

    ld_blocks = re.findall(
        r'<script type="application/ld\+json">\s*(.*?)\s*</script>',
        content,
        re.DOTALL,
    )
    org_data = None
    for block in ld_blocks:
        data = json.loads(block)
        if data.get("@type") == "Organization":
            org_data = data
            break

    assert org_data is not None, "Organization JSON-LD not found on index page"


def test_organization_schema_absent_on_non_index(project_dir):
    """Organization JSON-LD schema is absent on non-index pages."""
    docs_dir = os.path.join(project_dir, "docs")
    with open(os.path.join(docs_dir, "guide.md"), "w", encoding="utf-8") as f:
        f.write("# Guide\n\nContent.\n")

    build(str(project_dir))

    output_dir = os.path.join(project_dir, "docs", "_build")
    with open(os.path.join(output_dir, "guide.html"), "r", encoding="utf-8") as f:
        content = f.read()

    ld_blocks = re.findall(
        r'<script type="application/ld\+json">\s*(.*?)\s*</script>',
        content,
        re.DOTALL,
    )
    for block in ld_blocks:
        data = json.loads(block)
        assert data.get("@type") != "Organization", \
            "Organization JSON-LD should not appear on non-index pages"


def test_organization_schema_has_correct_name(project_dir):
    """Organization JSON-LD has the correct project name."""
    build(str(project_dir))

    output_dir = os.path.join(project_dir, "docs", "_build")
    with open(os.path.join(output_dir, "index.html"), "r", encoding="utf-8") as f:
        content = f.read()

    # project_name is derived from directory name
    project_name = os.path.basename(str(project_dir))

    ld_blocks = re.findall(
        r'<script type="application/ld\+json">\s*(.*?)\s*</script>',
        content,
        re.DOTALL,
    )
    org_data = None
    for block in ld_blocks:
        data = json.loads(block)
        if data.get("@type") == "Organization":
            org_data = data
            break

    assert org_data is not None, "Organization JSON-LD not found"
    assert org_data["name"] == project_name


# --- Phase 2B: Person schema and sameAs on homepage ---


def test_person_schema_on_homepage_with_person_author():
    """Config with author.type: 'Person' produces @type: Person on homepage."""
    html_files = generate_html(
        {"index.md": "# Test\n\nContent.\n"},
        project_name="Test",
        author={"name": "Jane Doe", "type": "Person", "url": "https://jane.dev"},
    )
    content = html_files["index.html"]

    ld_blocks = re.findall(
        r'<script type="application/ld\+json">\s*(.*?)\s*</script>',
        content,
        re.DOTALL,
    )
    entity = None
    for block in ld_blocks:
        data = json.loads(block)
        if data.get("@type") in ("Person", "Organization") and "potentialAction" not in data:
            entity = data
            break

    assert entity is not None, "Person/Organization JSON-LD not found"
    assert entity["@type"] == "Person"
    assert entity["name"] == "Jane Doe"


def test_same_as_twitter_on_homepage():
    """Config with author.twitter produces sameAs with twitter URL."""
    html_files = generate_html(
        {"index.md": "# Test\n\nContent.\n"},
        project_name="Test",
        author={"name": "Jane Doe", "type": "Person", "twitter": "@janedoe"},
    )
    content = html_files["index.html"]

    ld_blocks = re.findall(
        r'<script type="application/ld\+json">\s*(.*?)\s*</script>',
        content,
        re.DOTALL,
    )
    entity = None
    for block in ld_blocks:
        data = json.loads(block)
        if data.get("@type") in ("Person", "Organization") and "potentialAction" not in data:
            entity = data
            break

    assert entity is not None, "Person/Organization JSON-LD not found"
    assert "sameAs" in entity
    assert "https://twitter.com/janedoe" in entity["sameAs"]


def test_organization_schema_still_works_on_homepage():
    """Config with author.type: 'Organization' still produces @type: Organization (regression)."""
    html_files = generate_html(
        {"index.md": "# Test\n\nContent.\n"},
        project_name="Test",
        author={"name": "Acme Corp", "type": "Organization", "url": "https://acme.com"},
    )
    content = html_files["index.html"]

    ld_blocks = re.findall(
        r'<script type="application/ld\+json">\s*(.*?)\s*</script>',
        content,
        re.DOTALL,
    )
    entity = None
    for block in ld_blocks:
        data = json.loads(block)
        if data.get("@type") in ("Person", "Organization") and "potentialAction" not in data:
            entity = data
            break

    assert entity is not None, "Organization JSON-LD not found"
    assert entity["@type"] == "Organization"


# --- Phase 4B: CSS preload hint ---


def test_css_preload_hint():
    """Output HTML contains a preload link for the stylesheet."""
    html_files = generate_html(
        {"index.md": "# Test\n\nContent.\n"},
        project_name="Test",
    )
    content = html_files["index.html"]

    assert 'rel="preload"' in content
    assert 'as="style"' in content
    # The preload link should reference style.css
    assert '<link rel="preload" href="style.css" as="style">' in content


# --- Phase 7C: Tab keyboard navigation (WAI-ARIA) ---


def test_code_tabs_keyboard_navigation():
    """Generated JS contains ArrowRight and ArrowLeft when code tabs present."""
    # Page with consecutive code blocks (different langs) triggers code tabs
    md = "# Test\n\n```python\nprint(1)\n```\n```go\nfmt.Println(1)\n```\n"
    html_files = generate_html(
        {"index.md": md},
        project_name="Test",
    )
    content = html_files["index.html"]

    assert "ArrowRight" in content
    assert "ArrowLeft" in content


# --- Phase 5A: gzip/brotli pre-compression ---


def test_build_creates_gz_companions(project_dir):
    """After building, .gz files exist alongside .html and .css files."""
    build(str(project_dir))
    output_dir = os.path.join(project_dir, "docs", "_build")

    # Check that index.html.gz exists
    assert os.path.isfile(os.path.join(output_dir, "index.html.gz"))
    # Check that style.css.gz exists
    assert os.path.isfile(os.path.join(output_dir, "style.css.gz"))


def test_gz_files_are_valid_gzip(project_dir):
    """Verify .gz files are valid gzip and match original content."""
    build(str(project_dir))
    output_dir = os.path.join(project_dir, "docs", "_build")

    html_path = os.path.join(output_dir, "index.html")
    gz_path = html_path + ".gz"

    with open(html_path, "rb") as f:
        original = f.read()

    with gzip_module.open(gz_path, "rb") as f:
        decompressed = f.read()

    assert decompressed == original


def test_non_text_files_not_compressed(project_dir):
    """Files with non-text extensions (e.g. images) do NOT get compressed."""
    docs_dir = os.path.join(project_dir, "docs")
    # Create a dummy image file
    img_path = os.path.join(docs_dir, "logo.png")
    with open(img_path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n" + b"\x00" * 16)

    build(str(project_dir))
    output_dir = os.path.join(project_dir, "docs", "_build")

    # The PNG should be copied but NOT have a .gz companion
    assert os.path.isfile(os.path.join(output_dir, "logo.png"))
    assert not os.path.isfile(os.path.join(output_dir, "logo.png.gz"))


# --- Phase 5B: Conditional JS inclusion ---


def test_conditional_js_excludes_copy_and_tabs_when_not_needed():
    """Page with no code blocks or tabs excludes copy-btn and code-tabs JS."""
    html_files = generate_html(
        {"index.md": "# Hello\n\nJust text, no code.\n"},
        project_name="Test",
    )
    content = html_files["index.html"]

    # copy-btn JS should NOT be present (no <pre> in body)
    assert "copy-btn" not in content
    # code-tabs JS should NOT be present (no code-tabs in body)
    assert "code-tabs" not in content


def test_conditional_js_includes_all_when_needed():
    """Page with code blocks and tabs includes all JS blocks."""
    # Two consecutive code blocks with different languages produce tabs
    md = (
        "# API\n\n"
        "```python\nprint('hello')\n```\n"
        "```go\nfmt.Println(\"hello\")\n```\n"
    )
    html_files = generate_html(
        {"index.md": md},
        project_name="Test",
    )
    content = html_files["index.html"]

    # copy-btn JS present (has <pre>)
    assert "copy-btn" in content
    # code-tabs JS present (has code-tabs)
    assert "code-tabs" in content
    # run-btn JS present (has code-label)
    assert "run-btn" in content
    # Always-present JS blocks
    assert "theme-toggle" in content
    assert "hamburger" in content
    assert "search-dialog" in content


# -- Phase 6A: Auto-detect definition patterns --


def test_dfn_plain_text_after_heading():
    """Plain text 'X is a ...' after H2 gets <dfn> wrapping."""
    md = "## Overview\n\nselfdoc is a static site generator.\n"
    result = md_to_html(md)
    assert "<dfn>selfdoc</dfn> is a" in result


def test_dfn_code_after_heading():
    """`code` subject after heading wraps outer <code> in <dfn>."""
    md = "## Function\n\n`parse_directives` is a function.\n"
    result = md_to_html(md)
    assert "<dfn><code>parse_directives</code></dfn> is a" in result


def test_dfn_inverted_form():
    """'A directive refers to' after heading wraps subject in <dfn>."""
    md = "### Directives\n\nA directive refers to a block.\n"
    result = md_to_html(md)
    assert "<dfn>directive</dfn> refers to" in result


def test_dfn_not_applied_without_heading():
    """Paragraph NOT after a heading does NOT get <dfn> treatment."""
    md = "selfdoc is a static site generator.\n"
    result = md_to_html(md)
    assert "<dfn>" not in result


def test_dfn_not_applied_to_second_paragraph():
    """Second paragraph after heading does NOT get <dfn> treatment."""
    md = (
        "## Overview\n\n"
        "First paragraph here.\n\n"
        "selfdoc is a static site generator.\n"
    )
    result = md_to_html(md)
    # The first paragraph has no definitional pattern, and the second
    # should not be treated since it is not the first after the heading.
    assert "<dfn>" not in result


# --- Phase 2E: DefinedTerm from standalone dfn tags ---


def test_inline_dfn_produces_defined_term_jsonld():
    """A page with a definitional pattern (triggering _apply_definitions)
    produces a DefinedTerm JSON-LD entry."""
    html_files = generate_html(
        {"index.md": (
            "## Overview\n\n"
            "Selfdoc is a static site generator.\n"
        )},
        project_name="Test",
    )
    content = html_files["index.html"]

    ld_blocks = re.findall(
        r'<script type="application/ld\+json">\s*(.*?)\s*</script>',
        content,
        re.DOTALL,
    )
    term_set = None
    for block in ld_blocks:
        data = json.loads(block)
        if data.get("@type") == "DefinedTermSet":
            term_set = data
            break

    assert term_set is not None, "DefinedTermSet JSON-LD not found"
    terms = term_set["hasDefinedTerm"]
    names = [t["name"] for t in terms]
    assert "Selfdoc" in names


def test_glossary_and_inline_dfn_no_duplicates():
    """A page with both glossary terms and inline definitions produces
    entries for both without duplicates."""
    html_files = generate_html(
        {"index.md": (
            "## Overview\n\n"
            "Parser is a core component.\n\n"
            "Parser\n"
            ": Breaks input into tokens\n\n"
            "Lexer\n"
            ": Tokenizes raw text\n"
        )},
        project_name="Test",
    )
    content = html_files["index.html"]

    ld_blocks = re.findall(
        r'<script type="application/ld\+json">\s*(.*?)\s*</script>',
        content,
        re.DOTALL,
    )
    term_set = None
    for block in ld_blocks:
        data = json.loads(block)
        if data.get("@type") == "DefinedTermSet":
            term_set = data
            break

    assert term_set is not None, "DefinedTermSet JSON-LD not found"
    terms = term_set["hasDefinedTerm"]
    names = [t["name"] for t in terms]
    # Parser should appear once (from glossary), Lexer once (from glossary),
    # inline Parser should be deduplicated
    assert names.count("Parser") == 1
    assert "Lexer" in names


# --- Phase 7A: Trailing slash redirect rules ---


def test_redirects_file_exists_after_build(project_dir):
    """After build, _redirects file exists in the output directory."""
    build(str(project_dir))

    output_dir = os.path.join(project_dir, "docs", "_build")
    redirects_path = os.path.join(output_dir, "_redirects")
    assert os.path.isfile(redirects_path)


def test_redirects_contains_trailing_slash_rule(project_dir):
    """_redirects file contains the trailing slash redirect rule."""
    build(str(project_dir))

    output_dir = os.path.join(project_dir, "docs", "_build")
    redirects_path = os.path.join(output_dir, "_redirects")
    with open(redirects_path, "r", encoding="utf-8") as f:
        content = f.read()

    assert "/:path/ /:path 301" in content


def test_heading_anchor_aria_label():
    """Heading anchors include aria-label with readable section name."""
    from selfdoc.html import md_to_html

    result = md_to_html("## parse_directives")
    assert 'aria-label="Link to section: parse directives"' in result

    result2 = md_to_html("## Hello <code>World</code>")
    assert 'aria-label="Link to section: Hello World"' in result2


# --- Phase 1.3: OG type and 404 OG suppression ---


def test_og_type_website_on_index(project_dir):
    """Homepage (index.html) should have og:type 'website', not 'article'."""
    build(str(project_dir))

    output_dir = os.path.join(project_dir, "docs", "_build")
    index_html = os.path.join(output_dir, "index.html")
    with open(index_html, "r", encoding="utf-8") as f:
        content = f.read()

    assert 'og:type" content="website"' in content
    assert 'og:type" content="article"' not in content


def test_og_type_article_on_other_pages(project_dir):
    """Non-index pages should have og:type 'article'."""
    docs_dir = os.path.join(project_dir, "docs")
    guide_md = os.path.join(docs_dir, "guide.md")
    with open(guide_md, "w", encoding="utf-8") as f:
        f.write("# Guide\n\nA guide page.\n")

    build(str(project_dir))

    output_dir = os.path.join(project_dir, "docs", "_build")
    guide_html = os.path.join(output_dir, "guide.html")
    with open(guide_html, "r", encoding="utf-8") as f:
        content = f.read()

    assert 'og:type" content="article"' in content
    assert 'og:type" content="website"' not in content


def test_404_no_og_tags(project_dir):
    """404 page should not contain OG meta tags."""
    build(str(project_dir))

    output_dir = os.path.join(project_dir, "docs", "_build")
    four_oh_four = os.path.join(output_dir, "404.html")
    with open(four_oh_four, "r", encoding="utf-8") as f:
        content = f.read()

    assert "og:type" not in content
    assert "og:title" not in content


def test_twitter_site_meta_tag(project_dir):
    """Build with twitter config emits twitter:site meta tag in output HTML."""
    # Rewrite selfdoc.json with twitter field
    config_path = os.path.join(project_dir, "selfdoc.json")
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump({
            "language": "python",
            "source": ["src/"],
            "docs": "docs/",
            "output": "docs/_build/",
            "base_url": "https://example.com",
            "twitter": "@selfdoc",
        }, f)

    build(str(project_dir))

    output_dir = os.path.join(project_dir, "docs", "_build")
    index_html = os.path.join(output_dir, "index.html")
    with open(index_html, "r", encoding="utf-8") as f:
        content = f.read()

    assert 'twitter:site" content="@selfdoc"' in content


def test_breadcrumbs_flat_page(project_dir):
    """Flat page produces two-level breadcrumb: Home / Page Title."""
    docs_dir = os.path.join(project_dir, "docs")
    guide_md = os.path.join(docs_dir, "guide.md")
    with open(guide_md, "w", encoding="utf-8") as f:
        f.write("# Guide\n\nA guide page.\n")

    build(str(project_dir))

    output_dir = os.path.join(project_dir, "docs", "_build")
    with open(os.path.join(output_dir, "guide.html"), "r", encoding="utf-8") as f:
        content = f.read()

    assert '<nav class="breadcrumbs" aria-label="Breadcrumbs">' in content
    assert '<a href="index.html">Home</a>' in content
    assert '<span>Guide</span>' in content
    assert " / " in content


def test_breadcrumbs_subdirectory_page(project_dir):
    """Subdirectory page produces multi-level breadcrumb with dir links."""
    docs_dir = os.path.join(project_dir, "docs")
    api_dir = os.path.join(docs_dir, "api")
    os.makedirs(api_dir)
    with open(os.path.join(api_dir, "endpoints.md"), "w", encoding="utf-8") as f:
        f.write("# Endpoints\n\nAPI endpoints.\n")

    build(str(project_dir))

    output_dir = os.path.join(project_dir, "docs", "_build")
    endpoints_html = os.path.join(output_dir, "api", "endpoints.html")
    assert os.path.isfile(endpoints_html)

    with open(endpoints_html, "r", encoding="utf-8") as f:
        content = f.read()

    assert '<nav class="breadcrumbs" aria-label="Breadcrumbs">' in content
    assert '<a href="../index.html">Home</a>' in content
    assert '<a href="../api/index.html">Api</a>' in content
    assert '<span>Endpoints</span>' in content


def test_breadcrumbs_json_ld_nested(project_dir):
    """Subdirectory page produces BreadcrumbList JSON-LD with 3 items."""
    # Add base_url to config
    config_path = os.path.join(project_dir, "selfdoc.json")
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump({
            "language": "python",
            "source": ["src/"],
            "docs": "docs/",
            "output": "docs/_build/",
            "base_url": "https://example.com",
        }, f)

    docs_dir = os.path.join(project_dir, "docs")
    api_dir = os.path.join(docs_dir, "api")
    os.makedirs(api_dir)
    with open(os.path.join(api_dir, "endpoints.md"), "w", encoding="utf-8") as f:
        f.write("# Endpoints\n\nAPI endpoints.\n")

    build(str(project_dir))

    output_dir = os.path.join(project_dir, "docs", "_build")
    endpoints_html = os.path.join(output_dir, "api", "endpoints.html")
    with open(endpoints_html, "r", encoding="utf-8") as f:
        content = f.read()

    # Extract BreadcrumbList JSON-LD
    ld_blocks = re.findall(
        r'<script type="application/ld\+json">\s*(.*?)\s*</script>',
        content, re.DOTALL,
    )
    breadcrumb_lds = [
        json.loads(b) for b in ld_blocks
        if '"BreadcrumbList"' in b
    ]
    assert len(breadcrumb_lds) == 1
    bc = breadcrumb_lds[0]
    items = bc["itemListElement"]
    assert len(items) == 3
    assert items[0]["position"] == 1
    assert items[0]["name"] == "Home"
    assert items[0]["item"] == "https://example.com/index.html"
    assert items[1]["position"] == 2
    assert items[1]["name"] == "Api"
    assert items[1]["item"] == "https://example.com/api/"
    assert items[2]["position"] == 3
    assert items[2]["name"] == "Endpoints"
    assert "item" not in items[2]


# --- Phase 0A: Separate datePublished from dateModified ---


def test_date_published_differs_from_modified(project_dir):
    """Page with both 'date' and 'updated' frontmatter produces different
    datePublished and dateModified in JSON-LD."""
    config_path = os.path.join(project_dir, "selfdoc.json")
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
    config["base_url"] = "https://example.com"
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f)

    docs_dir = os.path.join(project_dir, "docs")
    with open(os.path.join(docs_dir, "index.md"), "w", encoding="utf-8") as f:
        f.write("---\ndate: 2025-01-15\nupdated: 2026-03-20\n---\n# Test\n\nContent.\n")

    build(str(project_dir))

    output_dir = os.path.join(project_dir, "docs", "_build")
    with open(os.path.join(output_dir, "index.html"), "r", encoding="utf-8") as f:
        content = f.read()

    ld_blocks = re.findall(
        r'<script type="application/ld\+json">\s*(.*?)\s*</script>',
        content, re.DOTALL,
    )
    tech_article = None
    for block in ld_blocks:
        data = json.loads(block)
        if data.get("@type") == "TechArticle":
            tech_article = data
            break

    assert tech_article is not None, "TechArticle JSON-LD not found"
    assert tech_article["datePublished"] == "2025-01-15"
    assert tech_article["dateModified"] == "2026-03-20"


def test_date_only_uses_for_both(project_dir):
    """Page with only 'date' uses it for both datePublished and dateModified."""
    config_path = os.path.join(project_dir, "selfdoc.json")
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
    config["base_url"] = "https://example.com"
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f)

    docs_dir = os.path.join(project_dir, "docs")
    with open(os.path.join(docs_dir, "index.md"), "w", encoding="utf-8") as f:
        f.write("---\ndate: 2025-06-01\n---\n# Test\n\nContent.\n")

    build(str(project_dir))

    output_dir = os.path.join(project_dir, "docs", "_build")
    with open(os.path.join(output_dir, "index.html"), "r", encoding="utf-8") as f:
        content = f.read()

    ld_blocks = re.findall(
        r'<script type="application/ld\+json">\s*(.*?)\s*</script>',
        content, re.DOTALL,
    )
    tech_article = None
    for block in ld_blocks:
        data = json.loads(block)
        if data.get("@type") == "TechArticle":
            tech_article = data
            break

    assert tech_article is not None
    assert tech_article["datePublished"] == "2025-06-01"
    assert tech_article["dateModified"] == "2025-06-01"


def test_updated_only_uses_fallback_for_published(project_dir):
    """Page with only 'updated' uses it for dateModified, falls back for
    datePublished."""
    config_path = os.path.join(project_dir, "selfdoc.json")
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
    config["base_url"] = "https://example.com"
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f)

    docs_dir = os.path.join(project_dir, "docs")
    with open(os.path.join(docs_dir, "index.md"), "w", encoding="utf-8") as f:
        f.write("---\nupdated: 2026-04-10\n---\n# Test\n\nContent.\n")

    build(str(project_dir))

    output_dir = os.path.join(project_dir, "docs", "_build")
    with open(os.path.join(output_dir, "index.html"), "r", encoding="utf-8") as f:
        content = f.read()

    ld_blocks = re.findall(
        r'<script type="application/ld\+json">\s*(.*?)\s*</script>',
        content, re.DOTALL,
    )
    tech_article = None
    for block in ld_blocks:
        data = json.loads(block)
        if data.get("@type") == "TechArticle":
            tech_article = data
            break

    assert tech_article is not None
    assert tech_article["dateModified"] == "2026-04-10"
    # published falls back to modified when no date frontmatter
    assert tech_article["datePublished"] == "2026-04-10"


def test_no_date_frontmatter_uses_mtime(project_dir):
    """Page with no date frontmatter uses mtime for both datePublished and
    dateModified."""
    config_path = os.path.join(project_dir, "selfdoc.json")
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
    config["base_url"] = "https://example.com"
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f)

    build(str(project_dir))

    output_dir = os.path.join(project_dir, "docs", "_build")
    with open(os.path.join(output_dir, "index.html"), "r", encoding="utf-8") as f:
        content = f.read()

    ld_blocks = re.findall(
        r'<script type="application/ld\+json">\s*(.*?)\s*</script>',
        content, re.DOTALL,
    )
    tech_article = None
    for block in ld_blocks:
        data = json.loads(block)
        if data.get("@type") == "TechArticle":
            tech_article = data
            break

    assert tech_article is not None
    # Both should be the same mtime-derived date
    assert re.match(r"^\d{4}-\d{2}-\d{2}$", tech_article["datePublished"])
    assert tech_article["datePublished"] == tech_article["dateModified"]


# --- Phase 2A: Independent datePublished in JSON-LD via generate_html ---


def test_generate_html_independent_date_published():
    """generate_html with different date_published and date_modified produces
    both distinct dates in TechArticle JSON-LD."""
    html_files = generate_html(
        {"index.md": "# Test\n\nContent.\n"},
        project_name="Test",
        base_url="https://example.com",
        page_dates={"index.md": ("2024-06-01", "2026-03-15")},
    )
    content = html_files["index.html"]

    ld_blocks = re.findall(
        r'<script type="application/ld\+json">\s*(.*?)\s*</script>',
        content,
        re.DOTALL,
    )
    tech_article = None
    for block in ld_blocks:
        data = json.loads(block)
        if data.get("@type") == "TechArticle":
            tech_article = data
            break

    assert tech_article is not None, "TechArticle JSON-LD not found"
    assert tech_article["datePublished"] == "2024-06-01"
    assert tech_article["dateModified"] == "2026-03-15"
    assert tech_article["datePublished"] != tech_article["dateModified"]


# --- Phase 0B: OG Image Size Upgrade ---


def test_og_png_dimensions_1200x630(project_dir):
    """Generated OG PNG images are 1200x630."""
    build(str(project_dir))

    output_dir = os.path.join(project_dir, "docs", "_build")
    png_path = os.path.join(output_dir, "og-index.png")
    assert os.path.isfile(png_path)

    with open(png_path, "rb") as f:
        data = f.read()

    # PNG signature
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    # IHDR chunk: 4 bytes length, 4 bytes "IHDR", then width (4 bytes) and height (4 bytes)
    ihdr_width = struct.unpack(">I", data[16:20])[0]
    ihdr_height = struct.unpack(">I", data[20:24])[0]
    assert ihdr_width == 1200
    assert ihdr_height == 630


# --- Phase 1A: Google Fonts deferred loading ---


def test_google_fonts_deferred_loading():
    """Google Fonts stylesheet is deferred, not render-blocking."""
    html_files = generate_html(
        {"index.md": "# Test\n\nContent.\n"},
        project_name="Test",
    )
    content = html_files["index.html"]

    fonts_url = "https://fonts.googleapis.com/css2?family=Inter"

    # Preconnect hints must be present
    assert '<link rel="preconnect" href="https://fonts.googleapis.com">' in content
    assert '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>' in content

    # Must have preload hint for the fonts stylesheet
    assert f'<link rel="preload" href="{fonts_url}' in content
    assert 'as="style"' in content

    # Must use media="print" with onload swap (deferred pattern)
    assert f'href="{fonts_url}' in content
    assert 'media="print"' in content
    assert "onload=\"this.media='all'\"" in content

    # Must have noscript fallback
    assert f'<noscript><link rel="stylesheet" href="{fonts_url}' in content

    # Must NOT have a plain render-blocking stylesheet for Google Fonts
    # (i.e., no <link href="...fonts..." rel="stylesheet"> without media="print")
    import re
    blocking_pattern = re.compile(
        r'<link\s+href="https://fonts\.googleapis\.com/[^"]*"\s+rel="stylesheet"\s*>'
    )
    assert not blocking_pattern.search(content), (
        "Google Fonts link should be deferred, not render-blocking"
    )


def test_long_frontmatter_description_truncated_in_meta():
    """A 300-char frontmatter description is truncated in <meta> to <= 158 chars."""
    long_desc = "A" * 50 + " " + "B" * 50 + " " + "C" * 50 + " " + "D" * 50 + " " + "E" * 50 + " " + "F" * 50
    assert len(long_desc) == 305  # 6*50 + 5 spaces

    html_files = generate_html(
        {"index.md": "# Test\n\nSome content here.\n"},
        project_name="Test",
        frontmatter={"index.md": {"description": long_desc}},
    )
    content = html_files["index.html"]

    # Extract the meta description content
    match = re.search(r'<meta name="description" content="([^"]*)"', content)
    assert match, "meta description tag must be present"
    meta_desc = match.group(1)
    # Must be at most 158 chars (155 + "...")
    assert len(meta_desc) <= 158, f"meta description is {len(meta_desc)} chars, expected <= 158"
    assert meta_desc.endswith("..."), "truncated description must end with '...'"


def test_short_frontmatter_description_unchanged_in_meta():
    """A 100-char frontmatter description is kept unchanged in <meta>."""
    short_desc = "This is a short description for testing purposes, well under the limit of one hundred fifty five."
    assert len(short_desc) < 155

    html_files = generate_html(
        {"index.md": "# Test\n\nSome content here.\n"},
        project_name="Test",
        frontmatter={"index.md": {"description": short_desc}},
    )
    content = html_files["index.html"]

    match = re.search(r'<meta name="description" content="([^"]*)"', content)
    assert match, "meta description tag must be present"
    meta_desc = match.group(1)
    assert meta_desc == short_desc, f"short description should be unchanged"


def test_inline_stat_markup_percentage():
    """==99.9%== produces <data value="99.9%">99.9%</data>."""
    result = md_to_html("Uptime is ==99.9%== guaranteed.")
    assert '<data value="99.9%">99.9%</data>' in result


def test_inline_stat_markup_number():
    """==42== produces <data value="42">42</data>."""
    result = md_to_html("There are ==42== modules.")
    assert '<data value="42">42</data>' in result


def test_inline_stat_markup_phrase():
    """==1.5x faster== produces <data value="1.5x faster">1.5x faster</data>."""
    result = md_to_html("It runs ==1.5x faster== than before.")
    assert '<data value="1.5x faster">1.5x faster</data>' in result


def test_inline_stat_markup_no_false_positive_assignment():
    """Regular text with = signs like a = b is NOT affected."""
    result = md_to_html("Set a = b in the config.")
    assert "<data" not in result


def test_inline_stat_markup_no_false_positive_equality():
    """Comparison operator == is NOT affected."""
    result = md_to_html("Check if x == y in the code.")
    assert "<data" not in result


def test_inline_stat_markup_not_in_code_block():
    """Text inside code blocks is NOT affected by stat markup."""
    result = md_to_html("```\n==42==\n```")
    assert "<data" not in result


def test_og_locale_default_en(project_dir):
    """og:locale defaults to en_US when lang is not set."""
    build(str(project_dir))

    output_dir = os.path.join(project_dir, "docs", "_build")
    with open(os.path.join(output_dir, "index.html"), "r", encoding="utf-8") as f:
        content = f.read()

    assert '<meta property="og:locale" content="en_US">' in content


def test_og_locale_custom_language(project_dir):
    """og:locale uses the correct locale for a custom language."""
    config_path = os.path.join(project_dir, "selfdoc.json")
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
    config["lang"] = "fa"
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f)

    build(str(project_dir))

    output_dir = os.path.join(project_dir, "docs", "_build")
    with open(os.path.join(output_dir, "index.html"), "r", encoding="utf-8") as f:
        content = f.read()

    assert '<meta property="og:locale" content="fa_IR">' in content


def test_og_image_alt_with_description(project_dir):
    """og:image:alt uses page description when available."""
    docs_dir = os.path.join(project_dir, "docs")
    with open(os.path.join(docs_dir, "index.md"), "w", encoding="utf-8") as f:
        f.write("---\ndescription: My project overview\n---\n# Test\n\nContent.\n")

    build(str(project_dir))

    output_dir = os.path.join(project_dir, "docs", "_build")
    with open(os.path.join(output_dir, "index.html"), "r", encoding="utf-8") as f:
        content = f.read()

    assert '<meta property="og:image:alt" content="My project overview">' in content


def test_og_image_alt_falls_back_to_title(project_dir):
    """og:image:alt falls back to page title when no description is available."""
    docs_dir = os.path.join(project_dir, "docs")
    with open(os.path.join(docs_dir, "index.md"), "w", encoding="utf-8") as f:
        f.write("# My Page Title\n")

    build(str(project_dir))

    output_dir = os.path.join(project_dir, "docs", "_build")
    with open(os.path.join(output_dir, "index.html"), "r", encoding="utf-8") as f:
        content = f.read()

    assert '<meta property="og:image:alt" content="My Page Title">' in content


# --- Externalized search JS ---


def test_search_js_file_generated(project_dir):
    """search.js exists in the output directory with correct contents."""
    build(str(project_dir))
    output_dir = os.path.join(project_dir, "docs", "_build")

    search_js_path = os.path.join(output_dir, "search.js")
    assert os.path.isfile(search_js_path)

    with open(search_js_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Must contain the fetch URL for the search index
    assert "search-index.json" in content
    # Must read prefix from data attribute
    assert "search-prefix" in content or "searchPrefix" in content


def test_search_js_deferred(project_dir):
    """HTML references search.js via a deferred script tag, not inline."""
    build(str(project_dir))
    output_dir = os.path.join(project_dir, "docs", "_build")

    with open(os.path.join(output_dir, "index.html"), "r", encoding="utf-8") as f:
        content = f.read()

    # External deferred script tag must point to search.js
    assert '<script defer src="search.js">' in content

    # The inline <script> block must NOT contain search index logic
    inline_match = re.search(r"<script>(.*?)</script>", content, re.DOTALL)
    assert inline_match is not None
    inline_js = inline_match.group(1)
    assert "search-index" not in inline_js


# --- Subdirectory-based nested nav groups ---


def test_subdirectory_pages_grouped_in_nav(project_dir):
    """Pages in subdirectories appear inside a nav-group with details/summary."""
    docs_dir = os.path.join(project_dir, "docs")
    guides_dir = os.path.join(docs_dir, "guides")
    os.makedirs(guides_dir)
    with open(os.path.join(guides_dir, "intro.md"), "w", encoding="utf-8") as f:
        f.write("# Introduction\n\nIntro content.\n")
    with open(os.path.join(guides_dir, "setup.md"), "w", encoding="utf-8") as f:
        f.write("# Setup\n\nSetup content.\n")

    build(str(project_dir))

    output_dir = os.path.join(project_dir, "docs", "_build")
    with open(os.path.join(output_dir, "index.html"), "r", encoding="utf-8") as f:
        content = f.read()

    assert 'class="nav-group"' in content
    assert 'class="nav-group-title"' in content
    assert "Guides" in content
    assert 'class="nav-group-items"' in content
    assert 'href="guides/intro.html"' in content
    assert 'href="guides/setup.html"' in content


def test_top_level_pages_ungrouped(project_dir):
    """Pages in docs/ root appear as flat list items without a group wrapper."""
    docs_dir = os.path.join(project_dir, "docs")
    with open(os.path.join(docs_dir, "faq.md"), "w", encoding="utf-8") as f:
        f.write("# FAQ\n\nFrequently asked questions.\n")

    build(str(project_dir))

    output_dir = os.path.join(project_dir, "docs", "_build")
    with open(os.path.join(output_dir, "index.html"), "r", encoding="utf-8") as f:
        content = f.read()

    # FAQ link should exist as a direct nav-list child, not inside a group
    assert 'href="faq.html"' in content
    # The nav-list should not contain any nav-group since there are no subdirs
    assert 'class="nav-group"' not in content


def test_nav_group_frontmatter_override(project_dir):
    """nav_group frontmatter overrides the directory-based group title."""
    docs_dir = os.path.join(project_dir, "docs")
    api_dir = os.path.join(docs_dir, "api")
    os.makedirs(api_dir)
    with open(os.path.join(api_dir, "config.md"), "w", encoding="utf-8") as f:
        f.write("---\nnav_group: Custom Title\n---\n# Configuration\n\nConfig.\n")

    build(str(project_dir))

    output_dir = os.path.join(project_dir, "docs", "_build")
    with open(os.path.join(output_dir, "index.html"), "r", encoding="utf-8") as f:
        content = f.read()

    assert "Custom Title" in content
    # The default "Api" should not appear as a group title
    assert '>Api<' not in content


def test_nav_order_frontmatter(project_dir):
    """nav_order frontmatter controls sort order within a group."""
    docs_dir = os.path.join(project_dir, "docs")
    guides_dir = os.path.join(docs_dir, "guides")
    os.makedirs(guides_dir)
    # setup has nav_order 1, intro has nav_order 2 -- so setup should come first
    with open(os.path.join(guides_dir, "intro.md"), "w", encoding="utf-8") as f:
        f.write("---\ntitle: Introduction\nnav_order: 2\n---\n# Introduction\n\nIntro.\n")
    with open(os.path.join(guides_dir, "setup.md"), "w", encoding="utf-8") as f:
        f.write("---\ntitle: Setup\nnav_order: 1\n---\n# Setup\n\nSetup.\n")

    build(str(project_dir))

    output_dir = os.path.join(project_dir, "docs", "_build")
    with open(os.path.join(output_dir, "index.html"), "r", encoding="utf-8") as f:
        content = f.read()

    # Find positions of the two links within the nav-group-items
    setup_pos = content.find('guides/setup.html')
    intro_pos = content.find('guides/intro.html')
    assert setup_pos < intro_pos, "Setup (nav_order=1) should appear before Introduction (nav_order=2)"


def test_active_group_auto_expands(project_dir):
    """The details element containing the active page has the open attribute."""
    docs_dir = os.path.join(project_dir, "docs")
    guides_dir = os.path.join(docs_dir, "guides")
    os.makedirs(guides_dir)
    with open(os.path.join(guides_dir, "intro.md"), "w", encoding="utf-8") as f:
        f.write("# Introduction\n\nIntro content.\n")

    build(str(project_dir))

    output_dir = os.path.join(project_dir, "docs", "_build")
    # Check the intro page itself -- its group should be open
    with open(os.path.join(output_dir, "guides", "intro.html"), "r", encoding="utf-8") as f:
        content = f.read()

    assert '<details open>' in content
    # Check that the index page (different group) does NOT have it open
    with open(os.path.join(output_dir, "index.html"), "r", encoding="utf-8") as f:
        index_content = f.read()

    # On index page, the group should be closed (no active page in it)
    assert '<details open>' not in index_content
    assert '<details>' in index_content


def test_nav_groups_sorted_alphabetically(project_dir):
    """Multiple nav groups appear sorted alphabetically by group name."""
    docs_dir = os.path.join(project_dir, "docs")
    # Create two subdirectories: "api" and "guides"
    api_dir = os.path.join(docs_dir, "api")
    guides_dir = os.path.join(docs_dir, "guides")
    os.makedirs(api_dir)
    os.makedirs(guides_dir)
    with open(os.path.join(api_dir, "ref.md"), "w", encoding="utf-8") as f:
        f.write("# API Reference\n\nRef.\n")
    with open(os.path.join(guides_dir, "start.md"), "w", encoding="utf-8") as f:
        f.write("# Getting Started\n\nStart.\n")

    build(str(project_dir))

    output_dir = os.path.join(project_dir, "docs", "_build")
    with open(os.path.join(output_dir, "index.html"), "r", encoding="utf-8") as f:
        content = f.read()

    # "Api" comes before "Guides" alphabetically
    api_pos = content.find('>Api<')
    guides_pos = content.find('>Guides<')
    assert api_pos < guides_pos, "Api group should appear before Guides group"


# --- Bug fixes: meta separator, sticky header, search no-results, search close ---


def test_page_meta_has_flex_layout():
    """page-meta contains edit link and date as separate child elements."""
    html_files = generate_html(
        {"index.md": "# Test\n\nContent.\n"},
        project_name="Test",
        repo="https://github.com/test/repo",
        page_dates={"index.md": ("2025-01-01", "2025-06-15")},
    )
    content = html_files["index.html"]

    # The page-meta div should exist
    assert 'class="page-meta"' in content
    # Edit link and date should be wrapped in separate <span> elements
    assert "<span>" in content
    # Both the edit link and the date should be present
    assert "edit-link" in content
    assert "2025" in content
    # They should not be directly concatenated (each in its own <span>)
    meta_match = re.search(r'<div class="page-meta">(.*?)</div>', content, re.DOTALL)
    assert meta_match is not None
    meta_inner = meta_match.group(1)
    # Should have at least two <span> children
    spans = re.findall(r'<span>.*?</span>', meta_inner, re.DOTALL)
    assert len(spans) >= 2, f"Expected at least 2 <span> children, got {len(spans)}"


def test_sticky_thead_offset(project_dir):
    """CSS contains thead with top: 52px, not top: 0."""
    build(str(project_dir))
    output_dir = os.path.join(project_dir, "docs", "_build")
    css_path = os.path.join(output_dir, "style.css")
    with open(css_path, "r", encoding="utf-8") as f:
        css = f.read()

    assert "top:52px" in css or "top: 52px" in css
    # Should NOT have top:0 for thead
    # Find the thead rule and check it uses 52px
    assert "top:0" not in css.split("thead")[1].split("}")[0] if "thead" in css else True


def test_search_no_results_element(project_dir):
    """search.js contains search-no-results class for empty results."""
    build(str(project_dir))
    output_dir = os.path.join(project_dir, "docs", "_build")
    search_js_path = os.path.join(output_dir, "search.js")
    with open(search_js_path, "r", encoding="utf-8") as f:
        js = f.read()

    assert "search-no-results" in js
    assert "No results for" in js


def test_search_closes_on_click(project_dir):
    """search.js contains closeSearch call within result rendering."""
    build(str(project_dir))
    output_dir = os.path.join(project_dir, "docs", "_build")
    search_js_path = os.path.join(output_dir, "search.js")
    with open(search_js_path, "r", encoding="utf-8") as f:
        js = f.read()

    # The closeSearch() call should appear in the result link click handler
    assert "closeSearch()" in js
    # Specifically, there should be an addEventListener('click'... closeSearch pattern
    assert "addEventListener" in js
    assert "closeSearch" in js


# --- OG PNG predraw integration ---


def test_og_png_basic_fallback(project_dir):
    """When predraw is unavailable, OG PNGs are valid basic PNGs."""
    with mock.patch("selfdoc.build._HAS_PREDRAW", False):
        build(str(project_dir))

    output_dir = os.path.join(project_dir, "docs", "_build")
    png_path = os.path.join(output_dir, "og-index.png")
    assert os.path.isfile(png_path)

    with open(png_path, "rb") as f:
        data = f.read()

    # Verify PNG signature
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    # Verify 1200x630 dimensions from IHDR
    ihdr_width = struct.unpack(">I", data[16:20])[0]
    ihdr_height = struct.unpack(">I", data[20:24])[0]
    assert ihdr_width == 1200
    assert ihdr_height == 630


def test_og_png_rich_when_predraw_available(project_dir):
    """When predraw is installed, rich PNGs are larger than basic ones."""
    try:
        from predraw.model import Scene, Element, Font
        from predraw.renderer import render_svg
        import cairosvg
    except ImportError:
        pytest.skip("predraw or cairosvg not installed")

    # Build with predraw enabled (real import)
    with mock.patch("selfdoc.build._HAS_PREDRAW", True):
        build(str(project_dir))

    output_dir = os.path.join(project_dir, "docs", "_build")
    rich_png_path = os.path.join(output_dir, "og-index.png")
    assert os.path.isfile(rich_png_path)
    rich_size = os.path.getsize(rich_png_path)

    with open(rich_png_path, "rb") as f:
        rich_data = f.read()

    # Verify valid PNG
    assert rich_data[:8] == b"\x89PNG\r\n\x1a\n"

    # Compare with basic version
    basic_bytes = _generate_og_png_basic()
    assert rich_size > len(basic_bytes)


# === Search trigger tests ===


def test_search_trigger_icon_default(project_dir):
    """Build without search config renders the icon trigger by default."""
    build(str(project_dir))
    output_dir = os.path.join(project_dir, "docs", "_build")
    index_html = os.path.join(output_dir, "index.html")
    with open(index_html, "r", encoding="utf-8") as f:
        content = f.read()
    assert 'class="search-trigger"' in content
    assert 'class="search-bar-trigger"' not in content


def test_search_trigger_icon_explicit(project_dir):
    """Build with search: "icon" renders the icon trigger."""
    config_path = os.path.join(project_dir, "selfdoc.json")
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
    config["search"] = "icon"
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f)
    build(str(project_dir))
    output_dir = os.path.join(project_dir, "docs", "_build")
    index_html = os.path.join(output_dir, "index.html")
    with open(index_html, "r", encoding="utf-8") as f:
        content = f.read()
    assert 'class="search-trigger"' in content
    assert 'class="search-bar-trigger"' not in content


def test_search_trigger_bar(project_dir):
    """Build with search: "bar" renders the bar trigger."""
    config_path = os.path.join(project_dir, "selfdoc.json")
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
    config["search"] = "bar"
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f)
    build(str(project_dir))
    output_dir = os.path.join(project_dir, "docs", "_build")
    index_html = os.path.join(output_dir, "index.html")
    with open(index_html, "r", encoding="utf-8") as f:
        content = f.read()
    assert 'class="search-bar-trigger"' in content
    assert 'class="search-trigger"' not in content
    assert 'class="search-bar-text"' in content
    assert 'class="search-bar-kbd"' in content


def test_search_trigger_hidden(project_dir):
    """Build with search: "hidden" renders no trigger in topbar."""
    config_path = os.path.join(project_dir, "selfdoc.json")
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
    config["search"] = "hidden"
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f)
    build(str(project_dir))
    output_dir = os.path.join(project_dir, "docs", "_build")
    index_html = os.path.join(output_dir, "index.html")
    with open(index_html, "r", encoding="utf-8") as f:
        content = f.read()
    assert 'search-trigger' not in content
    assert 'search-bar-trigger' not in content


def test_search_cmd_k_always_works(project_dir):
    """Search dialog HTML and search.js are always present regardless of search config."""
    for search_val in [None, "icon", "bar", "hidden"]:
        config_path = os.path.join(project_dir, "selfdoc.json")
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
        if search_val is not None:
            config["search"] = search_val
        elif "search" in config:
            del config["search"]
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config, f)
        build(str(project_dir))
        output_dir = os.path.join(project_dir, "docs", "_build")
        index_html = os.path.join(output_dir, "index.html")
        with open(index_html, "r", encoding="utf-8") as f:
            content = f.read()
        assert 'id="search-dialog"' in content, f"search dialog missing for search={search_val}"
        search_js = os.path.join(output_dir, "search.js")
        assert os.path.isfile(search_js), f"search.js missing for search={search_val}"


# --- Feedback widget: webhook POST and Google Analytics ---


def test_feedback_hidden_without_config():
    """Build without feedback config produces no feedback widget."""
    html_files = generate_html(
        {"index.md": "# Hello\n\nWorld.\n"},
        project_name="Test",
    )
    content = html_files["index.html"]
    assert 'class="feedback"' not in content


def test_feedback_rendered_with_webhook():
    """Feedback widget appears with data-webhook when webhook is configured."""
    html_files = generate_html(
        {"index.md": "# Hello\n\nWorld.\n"},
        project_name="Test",
        feedback={"webhook": "https://example.com/hook"},
    )
    content = html_files["index.html"]
    assert 'class="feedback"' in content
    assert 'data-webhook="https://example.com/hook"' in content


def test_feedback_rendered_with_ga():
    """Feedback widget appears with data-ga and GA script when ga is configured."""
    html_files = generate_html(
        {"index.md": "# Hello\n\nWorld.\n"},
        project_name="Test",
        feedback={"ga": "G-XXXXX"},
    )
    content = html_files["index.html"]
    assert 'class="feedback"' in content
    assert 'data-ga="G-XXXXX"' in content
    assert "googletagmanager.com/gtag/js?id=G-XXXXX" in content


def test_feedback_rendered_with_both():
    """Feedback widget includes both webhook and GA when both are configured."""
    html_files = generate_html(
        {"index.md": "# Hello\n\nWorld.\n"},
        project_name="Test",
        feedback={"webhook": "https://example.com/hook", "ga": "G-XXXXX"},
    )
    content = html_files["index.html"]
    assert 'class="feedback"' in content
    assert 'data-webhook="https://example.com/hook"' in content
    assert 'data-ga="G-XXXXX"' in content
    assert "googletagmanager.com/gtag/js?id=G-XXXXX" in content


def test_feedback_js_has_fetch():
    """Feedback JS block contains fetch() for webhook POST when feedback is configured."""
    html_files = generate_html(
        {"index.md": "# Hello\n\nWorld.\n"},
        project_name="Test",
        feedback={"webhook": "https://example.com/hook"},
    )
    content = html_files["index.html"]
    assert "fetch(" in content


def test_edit_link_uses_config_branch():
    """Edit URL uses branch from config when provided."""
    html_files = generate_html(
        {"index.md": "# Hello\n\nWorld.\n"},
        project_name="Test",
        repo="https://github.com/user/repo",
        docs_dir_name="docs",
        branch="develop",
    )
    content = html_files["index.html"]
    assert "/edit/develop/" in content


def test_edit_link_default_branch():
    """Edit URL defaults to 'main' when no branch config and git fails."""
    html_files = generate_html(
        {"index.md": "# Hello\n\nWorld.\n"},
        project_name="Test",
        repo="https://github.com/user/repo",
        docs_dir_name="docs",
    )
    content = html_files["index.html"]
    assert "/edit/main/" in content


def test_edit_link_top_and_bottom():
    """Both top and bottom edit links are present when repo is configured."""
    html_files = generate_html(
        {"index.md": "# Hello\n\nWorld.\n"},
        project_name="Test",
        repo="https://github.com/user/repo",
        docs_dir_name="docs",
    )
    content = html_files["index.html"]
    assert 'edit-link-top' in content
    assert 'edit-link" href=' in content
    # The bottom edit link is inside page-footer
    assert 'class="page-footer"' in content
    assert 'Edit this page on GitHub' in content


def test_content_header_flex():
    """Content header wraps breadcrumbs and top edit link on non-index pages."""
    html_files = generate_html(
        {
            "index.md": "# Home\n\nWelcome.\n",
            "guide.md": "# Guide\n\nContent.\n",
        },
        project_name="Test",
        repo="https://github.com/user/repo",
        docs_dir_name="docs",
    )
    content = html_files["guide.html"]
    assert 'class="content-header"' in content
    assert 'class="breadcrumbs"' in content
    assert 'edit-link-top' in content


# --- Accessibility tests ---


def test_sidebar_nav_aria_label():
    """Sidebar nav has aria-label='Site navigation'."""
    html_files = generate_html(
        {"index.md": "# Home\n\nWelcome.\n"},
        project_name="Test",
    )
    content = html_files["index.html"]
    assert 'aria-label="Site navigation"' in content
    assert '<nav class="sidebar" id="sidebar" aria-label="Site navigation">' in content


def test_toc_nav_aria_label():
    """TOC nav has aria-label='Table of contents'."""
    # Need enough headings to trigger TOC (>=2 h2/h3)
    md = "# Home\n\n## Section One\n\nText.\n\n## Section Two\n\nMore text.\n"
    html_files = generate_html(
        {"index.md": md},
        project_name="Test",
    )
    content = html_files["index.html"]
    assert '<nav class="toc-nav" aria-label="Table of contents">' in content


def test_search_dialog_aria_label():
    """Search dialog has aria-label='Search documentation'."""
    html_files = generate_html(
        {"index.md": "# Home\n\nWelcome.\n"},
        project_name="Test",
    )
    content = html_files["index.html"]
    assert 'aria-label="Search documentation"' in content
    assert '<dialog' in content


def test_theme_toggle_dynamic_aria():
    """Theme toggle JS contains dynamic aria-label updates."""
    html_files = generate_html(
        {"index.md": "# Home\n\nWelcome.\n"},
        project_name="Test",
    )
    content = html_files["index.html"]
    assert "Theme: system. Click for light mode" in content
    assert "Theme: light. Click for dark mode" in content
    assert "Theme: dark. Click for system theme" in content


def test_code_tabs_roving_tabindex():
    """Code tabs JS contains tabindex management for roving tabindex."""
    # Build a page with code tabs (consecutive fenced blocks with different langs)
    md = (
        "# Home\n\n"
        "```python\nprint('hello')\n```\n\n"
        "```javascript\nconsole.log('hello');\n```\n"
    )
    html_files = generate_html(
        {"index.md": md},
        project_name="Test",
    )
    content = html_files["index.html"]
    # The code tabs JS should contain tabindex management
    assert "tabindex" in content
    assert "setAttribute" in content


def test_search_input_no_autofocus():
    """Search input does NOT have autofocus attribute."""
    html_files = generate_html(
        {"index.md": "# Home\n\nWelcome.\n"},
        project_name="Test",
    )
    content = html_files["index.html"]
    # The search input should exist but without autofocus
    assert 'class="search-input"' in content
    # Find the search input tag and verify no autofocus
    search_input_match = re.search(r'<input[^>]*class="search-input"[^>]*>', content)
    assert search_input_match is not None
    assert "autofocus" not in search_input_match.group(0)


def test_copy_button_always_visible():
    """Copy button CSS uses opacity 0.5 (always visible), not opacity 0."""
    from selfdoc.themes import get_theme

    css = get_theme("minimal")
    # The .copy-btn rule should use opacity: 0.5, not opacity: 0
    assert "opacity: 0.5" in css
    # There should be no bare "opacity: 0;" for .copy-btn.
    # Extract the .copy-btn block and verify it does not contain "opacity: 0;"
    import re

    copy_btn_match = re.search(r"\.copy-btn\s*\{([^}]+)\}", css)
    assert copy_btn_match is not None
    copy_btn_body = copy_btn_match.group(1)
    # Should contain opacity: 0.5, not opacity: 0
    assert "opacity: 0.5" in copy_btn_body
    assert "opacity: 0;" not in copy_btn_body


def test_table_has_caption():
    """Tables get a sr-only caption from the preceding heading."""
    md = "# Home\n\n## Data Summary\n\n| Name | Value |\n| ---- | ----- |\n| A | 1 |\n| B | 2 |\n"
    result = md_to_html(md)
    assert '<caption class="sr-only">Data Summary</caption>' in result
