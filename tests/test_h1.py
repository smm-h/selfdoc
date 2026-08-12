"""Tests for Phase 3: H1 auto-generation and validation.

Verifies that:
- The first '# Heading' is consumed as the page title and not rendered in body
- An auto-generated H1 appears in the output with proper id and anchor
- Frontmatter title works as an alternative to '# Heading'
- Frontmatter title takes precedence over '# Heading'
- Multiple H1 headings cause a build error
- Missing title source (no H1 and no frontmatter title) causes a build error
- Hero pages have exactly one H1 (the hero H1)
- Non-hero pages have exactly one H1 (the auto-generated H1)
"""

import re

import pytest

from selfdoc.html import generate_html, md_to_html, _extract_title
from conftest import TEST_AUTHOR


class TestH1Extraction:
    """Test that the first H1 is consumed as title and removed from body."""

    def test_h1_consumed_as_title_not_in_body(self):
        """A page with '# Title' has the title extracted; the H1 does NOT
        appear in the md_to_html body output."""
        body = md_to_html("# My Page Title\n\nSome content.\n")
        # The H1 should NOT be in the body HTML
        assert "<h1" not in body
        # But the content should still be there
        assert "Some content." in body

    def test_auto_generated_h1_in_output(self):
        """The auto-generated H1 appears in the full HTML page output."""
        html_files = generate_html(
            {"index.md": "# My Page\n\nContent here.\n"},
            project_name="TestProject",
            author=TEST_AUTHOR,
        )
        content = html_files["index.html"]
        # Should have exactly one H1 -- the auto-generated one
        h1_matches = re.findall(r"<h1[^>]*>.*?</h1>", content)
        assert len(h1_matches) == 1
        assert "My Page" in h1_matches[0]

    def test_auto_h1_has_id_and_anchor(self):
        """The auto-generated H1 has an id attribute and heading link anchor."""
        html_files = generate_html(
            {"index.md": "# My Page\n\nContent here.\n"},
            project_name="TestProject",
            author=TEST_AUTHOR,
        )
        content = html_files["index.html"]
        h1_match = re.search(r'<h1 id="([^"]+)">(.*?)</h1>', content)
        assert h1_match is not None, "Auto-generated H1 with id not found"
        h1_id = h1_match.group(1)
        h1_inner = h1_match.group(2)
        assert h1_id == "my-page"
        assert 'class="heading-link"' in h1_inner
        assert 'href="#my-page"' in h1_inner

    def test_h1_not_in_body_content(self):
        """The body_html (between article tags) does not contain the original
        H1 -- only the auto-generated one at the top."""
        html_files = generate_html(
            {"index.md": "# Original Title\n\n## Section\n\nText.\n"},
            project_name="TestProject",
            author=TEST_AUTHOR,
        )
        content = html_files["index.html"]
        # Count H1s -- should be exactly 1 (auto-generated)
        h1_count = len(re.findall(r"<h1[^>]*>", content))
        assert h1_count == 1
        # The H2 should still be present
        assert "<h2" in content


class TestFrontmatterTitle:
    """Test frontmatter title as an alternative to H1 heading."""

    def test_frontmatter_title_no_h1_works(self):
        """A page with frontmatter title and no H1 heading builds correctly."""
        html_files = generate_html(
            {"index.md": "## Section\n\nContent.\n"},
            project_name="TestProject",
            frontmatter={"index.md": {"title": "From Frontmatter"}},
            author=TEST_AUTHOR,
        )
        content = html_files["index.html"]
        # Should have auto-generated H1 from frontmatter title
        h1_matches = re.findall(r"<h1[^>]*>.*?</h1>", content)
        assert len(h1_matches) == 1
        assert "From Frontmatter" in h1_matches[0]

    def test_frontmatter_title_overrides_h1(self):
        """When both frontmatter title and H1 exist, frontmatter wins for
        the page title (but H1 is still consumed/stripped from body)."""
        html_files = generate_html(
            {"index.md": "# Markdown Title\n\nContent.\n"},
            project_name="TestProject",
            frontmatter={"index.md": {"title": "Frontmatter Title"}},
            author=TEST_AUTHOR,
        )
        content = html_files["index.html"]
        # The <title> tag should use frontmatter title
        assert "<title>Frontmatter Title - TestProject</title>" in content
        # The auto-generated H1 should also use frontmatter title
        h1_matches = re.findall(r"<h1[^>]*>.*?</h1>", content)
        assert len(h1_matches) == 1
        assert "Frontmatter Title" in h1_matches[0]
        # The markdown H1 text should NOT appear as a separate H1
        body_h1s = re.findall(r"<h1[^>]*>.*?Markdown Title.*?</h1>", content)
        assert len(body_h1s) == 0


class TestMultipleH1Error:
    """Test that multiple H1 headings cause a build error."""

    def test_two_h1_headings_errors(self):
        """A page with two '# ' headings raises RuntimeError during build."""
        with pytest.raises(RuntimeError, match="multiple H1 headings"):
            generate_html(
                {"index.md": "# First\n\nText.\n\n# Second\n\nMore.\n"},
                project_name="TestProject",
                author=TEST_AUTHOR,
            )

    def test_three_h1_headings_errors(self):
        """A page with three '# ' headings also raises RuntimeError."""
        with pytest.raises(RuntimeError, match="multiple H1 headings"):
            generate_html(
                {"index.md": "# A\n\n# B\n\n# C\n"},
                project_name="TestProject",
                author=TEST_AUTHOR,
            )


class TestMissingTitleError:
    """Test that missing title source causes a build error."""

    def test_no_h1_no_frontmatter_title_errors(self):
        """A page with neither H1 heading nor frontmatter title errors."""
        with pytest.raises(RuntimeError, match="no title source"):
            generate_html(
                {"index.md": "## Only H2\n\nContent.\n"},
                project_name="TestProject",
                author=TEST_AUTHOR,
            )

    def test_no_h1_with_frontmatter_title_ok(self):
        """A page with frontmatter title but no H1 is valid."""
        # Should not raise
        html_files = generate_html(
            {"index.md": "## Section\n\nContent.\n"},
            project_name="TestProject",
            frontmatter={"index.md": {"title": "My Title"}},
            author=TEST_AUTHOR,
        )
        assert "index.html" in html_files


class TestHeroH1:
    """Test that hero pages have exactly one H1 (from the hero section)."""

    def test_hero_page_has_one_h1(self):
        """Index page with branding/hero has exactly one H1 (the hero H1)."""
        branding = {
            "tagline": "A test project",
            "cta_text": "Get Started",
            "cta_link": "#",
        }
        html_files = generate_html(
            {"index.md": "# Welcome\n\nSome intro text.\n"},
            project_name="TestProject",
            branding=branding,
            author=TEST_AUTHOR,
        )
        content = html_files["index.html"]
        h1_matches = re.findall(r"<h1[^>]*>.*?</h1>", content)
        assert len(h1_matches) == 1
        # The H1 should be the hero title, not a duplicate
        assert "hero-title" in h1_matches[0]

    def test_hero_page_no_auto_h1(self):
        """Index page with hero should NOT have auto-generated H1 besides hero."""
        branding = {
            "tagline": "A test project",
        }
        html_files = generate_html(
            {"index.md": "# Welcome\n\nContent.\n"},
            project_name="TestProject",
            branding=branding,
            author=TEST_AUTHOR,
        )
        content = html_files["index.html"]
        # No auto-generated H1 with heading-link class outside hero
        auto_h1 = re.findall(r'<h1 id="[^"]*"><a class="heading-link"', content)
        assert len(auto_h1) == 0


class TestNonHeroH1:
    """Test that non-hero pages have exactly one H1."""

    def test_regular_page_has_one_h1(self):
        """A regular (non-hero) page has exactly one auto-generated H1."""
        html_files = generate_html(
            {
                "index.md": "# Home\n\nWelcome.\n",
                "guide.md": "# Guide\n\n## Section\n\nContent.\n",
            },
            project_name="TestProject",
            author=TEST_AUTHOR,
        )
        guide_content = html_files["guide/index.html"]
        h1_matches = re.findall(r"<h1[^>]*>.*?</h1>", guide_content)
        assert len(h1_matches) == 1
        assert "Guide" in h1_matches[0]

    def test_page_with_only_h2_and_frontmatter_title(self):
        """A page with only H2s and frontmatter title has one auto H1."""
        html_files = generate_html(
            {
                "index.md": "# Home\n\nWelcome.\n",
                "ref.md": "## Overview\n\nContent.\n",
            },
            project_name="TestProject",
            frontmatter={"ref.md": {"title": "API Reference"}},
            author=TEST_AUTHOR,
        )
        ref_content = html_files["ref/index.html"]
        h1_matches = re.findall(r"<h1[^>]*>.*?</h1>", ref_content)
        assert len(h1_matches) == 1
        assert "API Reference" in h1_matches[0]


class TestExtractTitle:
    """Test that _extract_title still works correctly."""

    def test_extracts_h1_text(self):
        """_extract_title returns the first H1 heading text."""
        assert _extract_title("# Hello World\n\nContent.", "fallback") == "Hello World"

    def test_fallback_when_no_h1(self):
        """_extract_title returns fallback when no H1 is found."""
        assert _extract_title("## Only H2\n\nContent.", "fallback") == "fallback"

    def test_h1_with_inline_formatting(self):
        """_extract_title handles H1 with inline Markdown formatting."""
        assert _extract_title("# Hello `World`\n\nContent.", "fallback") == "Hello `World`"
