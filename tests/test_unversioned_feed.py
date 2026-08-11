"""Tests for Phase 2 Task 2.3: unversioned feed (_make_feed_entry and _generate_atom_feed)."""

import os

from selfdoc.build import _make_feed_entry, _generate_atom_feed, SimpleURLBuilder
from conftest import page_addresses_for


# --- _make_feed_entry tests ---


def test_make_feed_entry_basic():
    """Basic entry with all fields returns correct tuple and XML."""
    date, xml = _make_feed_entry(
        title="Getting Started",
        url="https://example.com/getting-started/",
        date="2024-06-01",
        summary="A quick introduction to the project.",
    )
    assert date == "2024-06-01"
    assert "<title>Getting Started</title>" in xml
    assert '<link href="https://example.com/getting-started/"/>' in xml
    assert "<id>https://example.com/getting-started/</id>" in xml
    assert "<updated>2024-06-01T00:00:00Z</updated>" in xml
    assert "<summary>A quick introduction to the project.</summary>" in xml
    assert xml.strip().startswith("<entry>")
    assert xml.strip().endswith("</entry>")


def test_make_feed_entry_no_summary():
    """Entry with empty summary omits the <summary> element."""
    date, xml = _make_feed_entry(
        title="No Summary Page",
        url="https://example.com/no-summary/",
        date="2024-01-15",
        summary="",
    )
    assert "<summary>" not in xml
    assert "<title>No Summary Page</title>" in xml


def test_make_feed_entry_escapes_html():
    """HTML special characters in title and summary are escaped."""
    date, xml = _make_feed_entry(
        title="Config <file> & settings",
        url="https://example.com/config/",
        date="2024-03-10",
        summary='Use "key" < 5 & value > 3',
    )
    assert "<title>Config &lt;file&gt; &amp; settings</title>" in xml
    assert "<summary>Use &quot;key&quot; &lt; 5 &amp; value &gt; 3</summary>" in xml


def test_make_feed_entry_page_type_accepted():
    """page_type parameter is accepted without error (reserved for Phase 3)."""
    date, xml = _make_feed_entry(
        title="Guide Page",
        url="https://example.com/guide/",
        date="2024-04-20",
        summary="A guide.",
        page_type="guide",
    )
    assert date == "2024-04-20"
    assert "<title>Guide Page</title>" in xml


# --- _generate_atom_feed tests ---


def test_generate_atom_feed_includes_pages(tmp_path):
    """Feed includes entries for all pages in markdown_files."""
    markdown_files = {
        "guide.md": "# Guide\n\nThis is a guide.",
        "faq.md": "# FAQ\n\nFrequently asked questions.",
    }
    page_dates = {
        "guide.md": ("2024-01-01", "2024-01-01"),
        "faq.md": ("2024-02-01", "2024-02-01"),
    }
    path = _generate_atom_feed(
        output_dir=str(tmp_path),
        base_url="https://example.com",
        project_name="TestProject",
        description="Test docs",
        markdown_files=markdown_files,
        frontmatter={},
        page_dates=page_dates,
        url_builder=SimpleURLBuilder("https://example.com"),
        page_addresses=page_addresses_for(markdown_files),
    )
    content = open(path).read()
    assert "<title>Guide</title>" in content
    assert "<title>FAQ</title>" in content
    assert content.count("<entry>") == 2


def test_generate_atom_feed_with_mixed_versioned_unversioned(tmp_path):
    """Feed processes all pages regardless of versioned/unversioned origin.

    The feed function receives a merged markdown_files dict and does not
    distinguish between versioned and unversioned content.
    """
    markdown_files = {
        "api-reference.md": "# API Reference\n\nVersioned API docs.",
        "changelog.md": "# Changelog\n\nVersioned changelog.",
        "faq.md": "# FAQ\n\nUnversioned FAQ page.",
        "about.md": "# About\n\nUnversioned about page.",
    }
    page_dates = {
        "api-reference.md": ("2024-01-01", "2024-03-15"),
        "changelog.md": ("2024-01-01", "2024-04-01"),
        "faq.md": ("2024-02-01", "2024-02-01"),
        "about.md": ("2024-05-01", "2024-05-01"),
    }
    path = _generate_atom_feed(
        output_dir=str(tmp_path),
        base_url="https://docs.example.com",
        project_name="MixedProject",
        description="Mixed versioned and unversioned docs",
        markdown_files=markdown_files,
        frontmatter={},
        page_dates=page_dates,
        url_builder=SimpleURLBuilder("https://docs.example.com"),
        page_addresses=page_addresses_for(markdown_files),
    )
    content = open(path).read()
    assert "<title>API Reference</title>" in content
    assert "<title>Changelog</title>" in content
    assert "<title>FAQ</title>" in content
    assert "<title>About</title>" in content
    assert content.count("<entry>") == 4


def test_generate_atom_feed_skips_feed_false(tmp_path):
    """Pages with feed: false in frontmatter are excluded from the feed."""
    markdown_files = {
        "visible.md": "# Visible\n\nThis page appears in the feed.",
        "hidden.md": "# Hidden\n\nThis page should not appear.",
    }
    page_dates = {
        "visible.md": ("2024-01-01", "2024-01-01"),
        "hidden.md": ("2024-01-01", "2024-01-01"),
    }
    frontmatter = {
        "hidden.md": {"feed": False},
    }
    path = _generate_atom_feed(
        output_dir=str(tmp_path),
        base_url="https://example.com",
        project_name="TestProject",
        description="Test",
        markdown_files=markdown_files,
        frontmatter=frontmatter,
        page_dates=page_dates,
        url_builder=SimpleURLBuilder("https://example.com"),
        page_addresses=page_addresses_for(markdown_files),
    )
    content = open(path).read()
    assert "<title>Visible</title>" in content
    assert "Hidden" not in content
    assert content.count("<entry>") == 1


def test_generate_atom_feed_ordered_by_date(tmp_path):
    """Feed entries are ordered by date, most recent first."""
    markdown_files = {
        "old.md": "# Old Page\n\nOldest content.",
        "mid.md": "# Mid Page\n\nMiddle content.",
        "new.md": "# New Page\n\nNewest content.",
    }
    page_dates = {
        "old.md": ("2024-01-01", "2024-01-01"),
        "mid.md": ("2024-06-01", "2024-06-01"),
        "new.md": ("2024-12-01", "2024-12-01"),
    }
    path = _generate_atom_feed(
        output_dir=str(tmp_path),
        base_url="https://example.com",
        project_name="TestProject",
        description="Test",
        markdown_files=markdown_files,
        frontmatter={},
        page_dates=page_dates,
        url_builder=SimpleURLBuilder("https://example.com"),
        page_addresses=page_addresses_for(markdown_files),
    )
    content = open(path).read()
    pos_new = content.index("<title>New Page</title>")
    pos_mid = content.index("<title>Mid Page</title>")
    pos_old = content.index("<title>Old Page</title>")
    assert pos_new < pos_mid < pos_old, "Entries should be ordered newest first"


def test_generate_atom_feed_max_entries(tmp_path):
    """feed_max_entries truncates the feed to the N most recent entries."""
    markdown_files = {}
    page_dates = {}
    for i in range(5):
        name = f"page{i}.md"
        markdown_files[name] = f"# Page {i}\n\nContent for page {i}."
        month = str(i + 1).zfill(2)
        page_dates[name] = (f"2024-{month}-01", f"2024-{month}-01")

    path = _generate_atom_feed(
        output_dir=str(tmp_path),
        base_url="https://example.com",
        project_name="TestProject",
        description="Test",
        markdown_files=markdown_files,
        frontmatter={},
        page_dates=page_dates,
        url_builder=SimpleURLBuilder("https://example.com"),
        page_addresses=page_addresses_for(markdown_files),
        feed_max_entries=3,
    )
    content = open(path).read()
    assert content.count("<entry>") == 3
    # Most recent 3 are page4 (May), page3 (April), page2 (March)
    assert "<title>Page 4</title>" in content
    assert "<title>Page 3</title>" in content
    assert "<title>Page 2</title>" in content
    # Oldest 2 should be excluded
    assert "<title>Page 1</title>" not in content
    assert "<title>Page 0</title>" not in content
