"""Tests for selfdoc.build."""

import json
import os
import re

import pytest

from selfdoc.build import build, _parse_frontmatter, _generate_robots_txt, _generate_headers, _generate_sitemap
from selfdoc.html import generate_html, generate_404_page, _extract_first_paragraph


@pytest.fixture()
def project_dir(tmp_path):
    """Create a minimal selfdoc project in a temp directory."""
    # Write selfdoc.json
    config = {
        "language": "python",
        "source": ["src/"],
        "docs": "docs/",
        "output": "docs/_build/",
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
    assert '<h1 id="test-project"><a class="heading-link" href="#test-project">#</a>Test Project</h1>' in content
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
    # 2 HTML + 1 style.css + 1 search-index.json + 2 OG SVGs + 2 llms files
    # + 1 404.html + 1 favicon.svg + 1 robots.txt + 1 _headers
    assert len(written) == 12
    assert os.path.isfile(os.path.join(output_dir, "style.css"))
    assert os.path.isfile(os.path.join(output_dir, "search-index.json"))
    assert os.path.isfile(os.path.join(output_dir, "og-index.svg"))
    assert os.path.isfile(os.path.join(output_dir, "og-guide.svg"))
    assert os.path.isfile(os.path.join(output_dir, "llms.txt"))
    assert os.path.isfile(os.path.join(output_dir, "llms-full.txt"))
    assert os.path.isfile(os.path.join(output_dir, "404.html"))
    assert os.path.isfile(os.path.join(output_dir, "favicon.svg"))


def test_build_no_config_raises(tmp_path):
    """Build without selfdoc.json raises an error."""
    with pytest.raises(RuntimeError, match="No selfdoc.json found"):
        build(str(tmp_path))


def test_build_no_docs_dir_raises(tmp_path):
    """Build without docs/ directory raises an error."""
    config = {"language": "python", "source": ["src/"], "docs": "docs/", "output": "docs/_build/"}
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
    assert '<nav class="sidebar" id="sidebar">' in content


def test_robots_txt_with_base_url(tmp_path):
    """robots.txt includes Sitemap line when base_url is set."""
    path = _generate_robots_txt(str(tmp_path), "https://example.com")
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    assert "User-agent: *\nAllow: /" in content
    assert "Sitemap: https://example.com/sitemap.xml" in content


def test_robots_txt_without_base_url(tmp_path):
    """robots.txt omits Sitemap line when base_url is None."""
    path = _generate_robots_txt(str(tmp_path), None)
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    assert "User-agent: *\nAllow: /" in content
    assert "Sitemap" not in content


def test_robots_txt_ai_crawlers(tmp_path):
    """robots.txt contains entries for all AI crawler user-agents."""
    path = _generate_robots_txt(str(tmp_path), None)
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    for agent in ["GPTBot", "ChatGPT-User", "Google-Extended", "PerplexityBot", "ClaudeBot"]:
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


def test_html_cdnjs_preconnect(project_dir):
    """Built HTML contains preconnect link for cdnjs.cloudflare.com."""
    build(str(project_dir))

    output_dir = os.path.join(project_dir, "docs", "_build")
    with open(os.path.join(output_dir, "index.html"), "r", encoding="utf-8") as f:
        content = f.read()

    assert '<link rel="preconnect" href="https://cdnjs.cloudflare.com" crossorigin>' in content


# --- Date infrastructure tests (Wave 2 Phase 0) ---


def _build_and_get_page_dates(project_dir):
    """Helper: run build and return page_dates dict by re-parsing frontmatter and mtime."""
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
        if "updated" in metadata:
            page_dates[fname] = str(metadata["updated"])
        elif "date" in metadata:
            page_dates[fname] = str(metadata["date"])
        else:
            mtime = os.path.getmtime(full_path)
            page_dates[fname] = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d")
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
    assert page_dates["dated.md"] == "2026-05-01"


def test_page_date_from_date_frontmatter(project_dir):
    """A page with 'date' (no 'updated') in frontmatter gets that date."""
    docs_dir = os.path.join(project_dir, "docs")
    page_md = os.path.join(docs_dir, "dated.md")
    with open(page_md, "w", encoding="utf-8") as f:
        f.write("---\ndate: 2026-01-15\n---\n# Dated Page\n\nContent.\n")

    build(str(project_dir))

    page_dates = _build_and_get_page_dates(project_dir)
    assert page_dates["dated.md"] == "2026-01-15"


def test_page_date_from_mtime(project_dir):
    """A page with no date frontmatter gets a date from file mtime (YYYY-MM-DD)."""
    # The index.md created by the fixture has no date frontmatter
    build(str(project_dir))

    page_dates = _build_and_get_page_dates(project_dir)
    date_str = page_dates["index.md"]
    assert re.match(r"^\d{4}-\d{2}-\d{2}$", date_str), f"Expected YYYY-MM-DD, got {date_str}"


def test_page_date_updated_takes_priority_over_date(project_dir):
    """'updated' takes priority over 'date' in frontmatter."""
    docs_dir = os.path.join(project_dir, "docs")
    page_md = os.path.join(docs_dir, "both.md")
    with open(page_md, "w", encoding="utf-8") as f:
        f.write("---\ndate: 2026-01-15\nupdated: 2026-05-01\n---\n# Both\n\nContent.\n")

    build(str(project_dir))

    page_dates = _build_and_get_page_dates(project_dir)
    assert page_dates["both.md"] == "2026-05-01"


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

    assert '<meta property="og:image" content="https://example.com/og-index.svg">' in content


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

    assert '<meta name="twitter:card" content="summary">' in content
    assert re.search(r'<meta name="twitter:title" content="Test Project - [^"]+">', content)


def test_auto_generated_description(project_dir):
    """Description is auto-generated from first paragraph when no frontmatter description."""
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

    assert '<meta name="description" content="This is the first paragraph of the page.">' in content
    assert '<meta property="og:description" content="This is the first paragraph of the page.">' in content
    assert '<meta name="twitter:description" content="This is the first paragraph of the page.">' in content


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
    assert len(result) <= 155
    assert not result.endswith(" ")
    # Should not cut mid-word
    assert result.endswith("word")


def test_extract_first_paragraph_empty():
    """_extract_first_paragraph returns empty string when no <p> found."""
    assert _extract_first_paragraph('<h1>Only heading</h1>') == ""
    assert _extract_first_paragraph('') == ""
