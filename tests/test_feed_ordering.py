"""Tests for type-aware feed ordering in selfdoc's build module.

Posts (type: "post") use their frontmatter date for ordering;
docs use page_dates[md_path][1] (modified date). Entries are sorted
by date descending, with feed_max_entries truncation applied after sorting.
"""

import re

from selfdoc.build import _make_feed_entry, _generate_atom_feed


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _updated_dates_in_order(feed_xml):
    """Extract all <updated> values from entry elements in document order."""
    # Match only <updated> tags inside <entry> blocks (skip the feed-level one).
    entries = re.findall(r"<entry>.*?</entry>", feed_xml, re.DOTALL)
    dates = []
    for entry in entries:
        m = re.search(r"<updated>(\d{4}-\d{2}-\d{2})T", entry)
        if m:
            dates.append(m.group(1))
    return dates


# ---------------------------------------------------------------------------
# _make_feed_entry tests (1-3)
# ---------------------------------------------------------------------------


def test_make_feed_entry_basic():
    """Returns (date, xml) tuple with correct title, URL, and date."""
    date, xml = _make_feed_entry(
        title="Getting Started",
        url="https://example.com/getting-started/",
        date="2024-06-01",
    )
    assert date == "2024-06-01"
    assert "<title>Getting Started</title>" in xml
    assert '<link href="https://example.com/getting-started/"/>' in xml
    assert "<id>https://example.com/getting-started/</id>" in xml
    assert "<updated>2024-06-01T00:00:00Z</updated>" in xml
    assert xml.strip().startswith("<entry>")
    assert xml.strip().endswith("</entry>")


def test_make_feed_entry_with_summary():
    """Includes <summary> element when summary is provided."""
    date, xml = _make_feed_entry(
        title="Page",
        url="https://example.com/page/",
        date="2024-01-01",
        summary="A brief summary.",
    )
    assert "<summary>A brief summary.</summary>" in xml


def test_make_feed_entry_escapes_html():
    """HTML entities in title are escaped."""
    date, xml = _make_feed_entry(
        title="Config <file> & settings",
        url="https://example.com/config/",
        date="2024-03-10",
    )
    assert "<title>Config &lt;file&gt; &amp; settings</title>" in xml


# ---------------------------------------------------------------------------
# Shared fixtures for _generate_atom_feed tests (4-9)
# ---------------------------------------------------------------------------

def _base_fixtures():
    """Return the base markdown_files, frontmatter, and page_dates dicts."""
    markdown_files = {
        "index.md": "# Home\nWelcome.",
        "posts/hello.md": "# Hello\nPost content.",
        "guide.md": "# Guide\nGuide content.",
    }
    frontmatter = {
        "index.md": {"title": "Home"},
        "posts/hello.md": {"title": "Hello Post", "type": "post", "date": "2024-06-15"},
        "guide.md": {"title": "Guide"},
    }
    page_dates = {
        "index.md": ("2024-01-01", "2024-01-01"),
        "posts/hello.md": ("2024-06-15", "2024-06-15"),
        "guide.md": ("2024-03-10", "2024-03-10"),
    }
    return markdown_files, frontmatter, page_dates


def _generate_feed(tmp_path, markdown_files, frontmatter, page_dates,
                   feed_max_entries=None):
    """Call _generate_atom_feed and return the feed XML string."""
    _generate_atom_feed(
        output_dir=str(tmp_path),
        base_url="https://example.com",
        project_name="Test",
        description="Test desc",
        markdown_files=markdown_files,
        frontmatter=frontmatter,
        page_dates=page_dates,
        feed_max_entries=feed_max_entries,
    )
    return (tmp_path / "feed.xml").read_text()


# ---------------------------------------------------------------------------
# _generate_atom_feed tests (4-9)
# ---------------------------------------------------------------------------


def test_feed_post_uses_frontmatter_date(tmp_path):
    """Post entry uses frontmatter date, not page_dates."""
    markdown_files = {
        "posts/hello.md": "# Hello\nPost content.",
    }
    frontmatter = {
        "posts/hello.md": {"title": "Hello Post", "type": "post", "date": "2024-06-15"},
    }
    # Deliberately set page_dates modified date to a DIFFERENT value.
    page_dates = {
        "posts/hello.md": ("2024-01-01", "2024-01-01"),
    }
    feed_xml = _generate_feed(tmp_path, markdown_files, frontmatter, page_dates)

    dates = _updated_dates_in_order(feed_xml)
    assert len(dates) == 1
    # The entry must use the frontmatter date (2024-06-15), not page_dates (2024-01-01).
    assert dates[0] == "2024-06-15"


def test_feed_doc_uses_page_dates(tmp_path):
    """Doc entry uses page_dates modification date, not frontmatter."""
    markdown_files = {
        "guide.md": "# Guide\nGuide content.",
    }
    frontmatter = {
        "guide.md": {"title": "Guide"},
    }
    page_dates = {
        "guide.md": ("2024-01-01", "2024-03-10"),
    }
    feed_xml = _generate_feed(tmp_path, markdown_files, frontmatter, page_dates)

    dates = _updated_dates_in_order(feed_xml)
    assert len(dates) == 1
    # The entry must use page_dates[1] (modified date = 2024-03-10).
    assert dates[0] == "2024-03-10"


def test_feed_interleaved_chronological_order(tmp_path):
    """Posts and docs are sorted together by date descending."""
    markdown_files, frontmatter, page_dates = _base_fixtures()
    feed_xml = _generate_feed(tmp_path, markdown_files, frontmatter, page_dates)

    dates = _updated_dates_in_order(feed_xml)
    # Expected order: post 2024-06-15, guide 2024-03-10, index 2024-01-01
    assert dates == ["2024-06-15", "2024-03-10", "2024-01-01"]


def test_feed_post_before_older_doc(tmp_path):
    """A newer post appears before an older doc."""
    markdown_files = {
        "posts/new.md": "# New Post\nFresh content.",
        "guide.md": "# Guide\nGuide content.",
    }
    frontmatter = {
        "posts/new.md": {"title": "New Post", "type": "post", "date": "2024-09-01"},
        "guide.md": {"title": "Guide"},
    }
    page_dates = {
        "posts/new.md": ("2024-09-01", "2024-09-01"),
        "guide.md": ("2024-01-01", "2024-05-15"),
    }
    feed_xml = _generate_feed(tmp_path, markdown_files, frontmatter, page_dates)

    pos_post = feed_xml.index("<title>New Post</title>")
    pos_doc = feed_xml.index("<title>Guide</title>")
    assert pos_post < pos_doc, "Newer post should appear before older doc"

    dates = _updated_dates_in_order(feed_xml)
    assert dates == ["2024-09-01", "2024-05-15"]


def test_feed_doc_before_older_post(tmp_path):
    """A newer doc appears before an older post."""
    markdown_files = {
        "posts/old.md": "# Old Post\nOld content.",
        "reference.md": "# Reference\nRef content.",
    }
    frontmatter = {
        "posts/old.md": {"title": "Old Post", "type": "post", "date": "2024-02-01"},
        "reference.md": {"title": "Reference"},
    }
    page_dates = {
        "posts/old.md": ("2024-02-01", "2024-02-01"),
        "reference.md": ("2024-01-01", "2024-08-20"),
    }
    feed_xml = _generate_feed(tmp_path, markdown_files, frontmatter, page_dates)

    pos_doc = feed_xml.index("<title>Reference</title>")
    pos_post = feed_xml.index("<title>Old Post</title>")
    assert pos_doc < pos_post, "Newer doc should appear before older post"

    dates = _updated_dates_in_order(feed_xml)
    assert dates == ["2024-08-20", "2024-02-01"]


def test_feed_respects_max_entries(tmp_path):
    """Truncates to feed_max_entries after sorting by date descending."""
    markdown_files = {
        "posts/latest.md": "# Latest\nLatest post.",
        "posts/mid.md": "# Mid\nMid post.",
        "old-doc.md": "# Old Doc\nOld documentation.",
    }
    frontmatter = {
        "posts/latest.md": {"title": "Latest", "type": "post", "date": "2024-12-01"},
        "posts/mid.md": {"title": "Mid", "type": "post", "date": "2024-06-01"},
        "old-doc.md": {"title": "Old Doc"},
    }
    page_dates = {
        "posts/latest.md": ("2024-12-01", "2024-12-01"),
        "posts/mid.md": ("2024-06-01", "2024-06-01"),
        "old-doc.md": ("2024-01-01", "2024-01-01"),
    }
    feed_xml = _generate_feed(
        tmp_path, markdown_files, frontmatter, page_dates,
        feed_max_entries=2,
    )

    assert feed_xml.count("<entry>") == 2
    # The two most recent entries should be kept.
    assert "<title>Latest</title>" in feed_xml
    assert "<title>Mid</title>" in feed_xml
    # The oldest should be truncated.
    assert "<title>Old Doc</title>" not in feed_xml
