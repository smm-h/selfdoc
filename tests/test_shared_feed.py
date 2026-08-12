"""Feed-specific tests for selfblog.shared module."""

from selfblog.shared import generate_unified_feed
from selfdoc.build import _make_feed_entry


def _make_manifest(name, slug, posts=None):
    return {
        "schema_version": 1,
        "name": name,
        "slug": slug,
        "version": "1.0.0",
        "description": "",
        "language": "python",
        "base_url": f"https://example.com/{slug}",
        "pages": [],
        "posts": posts or [],
        "last_gen": "2024-01-01T00:00:00+00:00",
    }


def _make_post(title, date, slug, tags=None):
    return {
        "path": f"posts/{slug}.md",
        "title": title,
        "date": date,
        "slug": slug,
        "tags": tags or [],
    }


# -- Feed entry reuse from _make_feed_entry --


def test_feed_entry_reuse():
    """Unified feed entries are produced by _make_feed_entry from selfdoc.build."""
    post = _make_post("Hello World", "2024-05-10", "hello-world")
    manifest = _make_manifest("proj", "proj", posts=[post])
    docs_base = "https://docs.example.com"

    feed = generate_unified_feed([manifest], docs_base)

    # Call _make_feed_entry directly with the same data the feed would use
    expected_url = f"{docs_base}/blog/hello-world/"
    _, entry_xml = _make_feed_entry(
        title="Hello World",
        url=expected_url,
        date="2024-05-10",
    )
    assert entry_xml in feed


def test_feed_entry_has_correct_url():
    """Entry link href uses the site-level {docs_base}/blog/{post_slug}/."""
    post = _make_post("My Post", "2024-02-20", "my-post")
    manifest = _make_manifest("alpha", "alpha", posts=[post])
    docs_base = "https://docs.example.com"

    feed = generate_unified_feed([manifest], docs_base)

    assert '<link href="https://docs.example.com/blog/my-post/"/>' in feed
    assert "alpha/posts" not in feed


def test_feed_entry_title_escaped():
    """HTML in post titles is escaped in the feed XML."""
    post = _make_post("<b>Bold</b>", "2024-04-01", "bold-post")
    manifest = _make_manifest("proj", "proj", posts=[post])

    feed = generate_unified_feed([manifest], "https://docs.example.com")

    assert "&lt;b&gt;Bold&lt;/b&gt;" in feed
    assert "<b>Bold</b>" not in feed.split("<title>")[1].split("</title>")[0]


# -- Feed ordering --


def test_feed_ordering_descending():
    """Entries are ordered by date descending (newest first)."""
    posts = [
        _make_post("January", "2024-01-01", "jan"),
        _make_post("June", "2024-06-15", "jun"),
        _make_post("March", "2024-03-20", "mar"),
    ]
    manifest = _make_manifest("proj", "proj", posts=posts)

    feed = generate_unified_feed([manifest], "https://docs.example.com")

    idx_jun = feed.index("June")
    idx_mar = feed.index("March")
    idx_jan = feed.index("January")
    assert idx_jun < idx_mar < idx_jan


def test_feed_ordering_across_projects():
    """Posts from multiple manifests are interleaved by date, not grouped by project."""
    m1 = _make_manifest("Alpha", "alpha", posts=[
        _make_post("A-Early", "2024-01-10", "a-early"),
        _make_post("A-Late", "2024-07-20", "a-late"),
    ])
    m2 = _make_manifest("Beta", "beta", posts=[
        _make_post("B-Mid", "2024-04-15", "b-mid"),
    ])

    feed = generate_unified_feed([m1, m2], "https://docs.example.com")

    idx_late = feed.index("A-Late")
    idx_mid = feed.index("B-Mid")
    idx_early = feed.index("A-Early")
    assert idx_late < idx_mid < idx_early


def test_feed_most_recent_date_in_updated():
    """Feed-level <updated> contains the most recent post date."""
    posts = [
        _make_post("Old", "2024-01-01", "old"),
        _make_post("New", "2024-09-30", "new"),
    ]
    manifest = _make_manifest("proj", "proj", posts=posts)

    feed = generate_unified_feed([manifest], "https://docs.example.com")

    # The feed-level <updated> should use the newest date
    # It appears before the first <entry>
    feed_header = feed.split("<entry>")[0]
    assert "<updated>2024-09-30T00:00:00Z</updated>" in feed_header


# -- Feed with empty posts --


def test_feed_empty_posts_single_manifest():
    """A manifest with no posts produces valid Atom XML with no entries."""
    manifest = _make_manifest("proj", "proj", posts=[])

    feed = generate_unified_feed([manifest], "https://docs.example.com")

    assert "<feed " in feed
    assert "</feed>" in feed
    assert "<entry>" not in feed


def test_feed_empty_posts_multiple_manifests():
    """Multiple manifests all with no posts still produce valid Atom XML."""
    manifests = [
        _make_manifest("alpha", "alpha", posts=[]),
        _make_manifest("beta", "beta", posts=[]),
        _make_manifest("gamma", "gamma", posts=[]),
    ]

    feed = generate_unified_feed(manifests, "https://docs.example.com")

    assert "<feed " in feed
    assert "</feed>" in feed
    assert "<entry>" not in feed


def test_feed_empty_posts_has_updated():
    """With no posts, the feed still has an <updated> element (using today's date)."""
    manifest = _make_manifest("proj", "proj", posts=[])

    feed = generate_unified_feed([manifest], "https://docs.example.com")

    assert "<updated>" in feed
    assert "</updated>" in feed
