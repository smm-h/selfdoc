"""Tests for selfdoc.build."""

import json
import os

import pytest

from selfdoc.build import build, _generate_robots_txt, _generate_headers


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
