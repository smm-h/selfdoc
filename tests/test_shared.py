"""Tests for selfdoc.shared -- shared elements for multi-project documentation assembly."""

import json

from selfdoc.shared import (
    _page_path_to_url_segment,
    generate_blog_index,
    generate_homepage,
    generate_nav_json,
    generate_sitemap,
    generate_unified_feed,
    validate_cross_project_links,
)


def _make_manifest(name, slug, version, description="", pages=None, posts=None):
    return {
        "schema_version": 1,
        "name": name,
        "slug": slug,
        "version": version,
        "description": description,
        "language": "python",
        "base_url": f"https://example.com/{slug}",
        "pages": pages or [],
        "posts": posts or [],
        "last_gen": "2024-01-01T00:00:00+00:00",
    }


# -- generate_homepage --------------------------------------------------------


def test_homepage_with_two_projects():
    """Two manifests: both names appear, links correct, sorted alphabetically."""
    manifests = [
        _make_manifest("Zebra", "zebra", "1.0.0", description="Z project"),
        _make_manifest("Alpha", "alpha", "2.0.0", description="A project"),
    ]
    result = generate_homepage(manifests, "https://docs.example.com")
    # Alpha sorts before Zebra
    alpha_pos = result.index("Alpha")
    zebra_pos = result.index("Zebra")
    assert alpha_pos < zebra_pos
    # Both project names present
    assert "Alpha" in result
    assert "Zebra" in result
    # Correct links
    assert 'href="https://docs.example.com/alpha/"' in result
    assert 'href="https://docs.example.com/zebra/"' in result


def test_homepage_empty_manifests():
    """Empty list: no article elements but section/h1 present."""
    result = generate_homepage([], "https://docs.example.com")
    assert "<section" in result
    assert "<h1>" in result
    assert "<article" not in result


def test_homepage_escapes_html_in_names():
    """Manifest with <script> in name is escaped."""
    manifests = [_make_manifest("<script>alert(1)</script>", "xss", "1.0.0")]
    result = generate_homepage(manifests, "https://docs.example.com")
    assert "<script>" not in result
    assert "&lt;script&gt;" in result


def test_homepage_version_badge():
    """Version badge shows v{version}."""
    manifests = [_make_manifest("MyLib", "mylib", "3.2.1")]
    result = generate_homepage(manifests, "https://docs.example.com")
    assert "v3.2.1" in result
    assert 'class="version-badge"' in result


def test_homepage_link_structure():
    """Href follows {docs_base}/{slug}/ pattern."""
    manifests = [_make_manifest("Foo", "foo-lib", "0.1.0")]
    result = generate_homepage(manifests, "https://my-docs.io")
    assert 'href="https://my-docs.io/foo-lib/"' in result


# -- generate_blog_index ------------------------------------------------------


def test_blog_index_multiple_projects():
    """Two manifests with posts: all posts appear."""
    manifests = [
        _make_manifest("ProjA", "proj-a", "1.0.0", posts=[
            {"title": "Post One", "slug": "post-one", "date": "2024-03-01"},
        ]),
        _make_manifest("ProjB", "proj-b", "1.0.0", posts=[
            {"title": "Post Two", "slug": "post-two", "date": "2024-04-01"},
        ]),
    ]
    result = generate_blog_index(manifests, "https://docs.example.com")
    assert "Post One" in result
    assert "Post Two" in result


def test_blog_index_sorted_by_date_descending():
    """Posts with different dates are newest-first."""
    manifests = [
        _make_manifest("Proj", "proj", "1.0.0", posts=[
            {"title": "Old Post", "slug": "old", "date": "2023-01-01"},
            {"title": "New Post", "slug": "new", "date": "2024-06-15"},
            {"title": "Mid Post", "slug": "mid", "date": "2024-01-01"},
        ]),
    ]
    result = generate_blog_index(manifests, "https://docs.example.com")
    new_pos = result.index("New Post")
    mid_pos = result.index("Mid Post")
    old_pos = result.index("Old Post")
    assert new_pos < mid_pos < old_pos


def test_blog_index_no_posts():
    """Manifests with no posts show the 'No posts yet.' message."""
    manifests = [
        _make_manifest("EmptyProj", "empty", "1.0.0"),
    ]
    result = generate_blog_index(manifests, "https://docs.example.com")
    assert "No posts yet." in result


def test_blog_index_link_structure():
    """Post links follow {docs_base}/{slug}/posts/{post_slug}/ pattern."""
    manifests = [
        _make_manifest("MyProj", "my-proj", "1.0.0", posts=[
            {"title": "Hello", "slug": "hello-world", "date": "2024-01-01"},
        ]),
    ]
    result = generate_blog_index(manifests, "https://docs.example.com")
    assert 'href="https://docs.example.com/my-proj/posts/hello-world/"' in result


def test_blog_index_shows_project_name():
    """Each post shows the project name."""
    manifests = [
        _make_manifest("SpecialProject", "special", "1.0.0", posts=[
            {"title": "A Post", "slug": "a-post", "date": "2024-01-01"},
        ]),
    ]
    result = generate_blog_index(manifests, "https://docs.example.com")
    assert "SpecialProject" in result
    assert 'class="project-name"' in result


# -- generate_nav_json --------------------------------------------------------


def test_nav_json_structure():
    """JSON has 'projects' array and 'blog' key."""
    manifests = [_make_manifest("Foo", "foo", "1.0.0")]
    result = json.loads(generate_nav_json(manifests))
    assert "projects" in result
    assert isinstance(result["projects"], list)
    assert "blog" in result


def test_nav_json_project_fields():
    """Each project has name, slug, version."""
    manifests = [_make_manifest("MyLib", "mylib", "2.3.4")]
    result = json.loads(generate_nav_json(manifests))
    project = result["projects"][0]
    assert project["name"] == "MyLib"
    assert project["slug"] == "mylib"
    assert project["version"] == "2.3.4"


def test_nav_json_sorted_alphabetically():
    """Projects sorted by name (case-insensitive)."""
    manifests = [
        _make_manifest("charlie", "charlie", "1.0.0"),
        _make_manifest("Alpha", "alpha", "1.0.0"),
        _make_manifest("bravo", "bravo", "1.0.0"),
    ]
    result = json.loads(generate_nav_json(manifests))
    names = [p["name"] for p in result["projects"]]
    assert names == ["Alpha", "bravo", "charlie"]


def test_nav_json_empty_manifests():
    """Empty list: valid JSON with empty projects array."""
    result = json.loads(generate_nav_json([]))
    assert result["projects"] == []
    assert "blog" in result


# -- generate_unified_feed ----------------------------------------------------


def test_unified_feed_valid_atom():
    """XML declaration and Atom feed namespace present."""
    manifests = [_make_manifest("Proj", "proj", "1.0.0")]
    result = generate_unified_feed(manifests, "https://docs.example.com")
    assert result.startswith('<?xml version="1.0" encoding="utf-8"?>')
    assert 'xmlns="http://www.w3.org/2005/Atom"' in result
    assert "</feed>" in result


def test_unified_feed_contains_entries():
    """Posts from 2 manifests both appear as entries."""
    manifests = [
        _make_manifest("A", "a", "1.0.0", posts=[
            {"title": "Entry A", "slug": "entry-a", "date": "2024-01-01"},
        ]),
        _make_manifest("B", "b", "1.0.0", posts=[
            {"title": "Entry B", "slug": "entry-b", "date": "2024-02-01"},
        ]),
    ]
    result = generate_unified_feed(manifests, "https://docs.example.com")
    assert "<entry>" in result
    assert "Entry A" in result
    assert "Entry B" in result


def test_unified_feed_default_title():
    """No feed_title: 'Documentation' appears as the title."""
    manifests = [_make_manifest("Proj", "proj", "1.0.0")]
    result = generate_unified_feed(manifests, "https://docs.example.com")
    assert "<title>Documentation</title>" in result


def test_unified_feed_custom_title():
    """Custom feed_title appears in the feed."""
    manifests = [_make_manifest("Proj", "proj", "1.0.0")]
    result = generate_unified_feed(
        manifests, "https://docs.example.com", feed_title="My Custom Feed"
    )
    assert "<title>My Custom Feed</title>" in result
    assert "Documentation" not in result


def test_unified_feed_sorted_by_date():
    """Most recent post appears first in the XML output."""
    manifests = [
        _make_manifest("Proj", "proj", "1.0.0", posts=[
            {"title": "Old Entry", "slug": "old", "date": "2023-01-01"},
            {"title": "New Entry", "slug": "new", "date": "2025-06-01"},
        ]),
    ]
    result = generate_unified_feed(manifests, "https://docs.example.com")
    new_pos = result.index("New Entry")
    old_pos = result.index("Old Entry")
    assert new_pos < old_pos


def test_unified_feed_empty_posts():
    """No posts: valid Atom XML with no entry elements."""
    manifests = [_make_manifest("Empty", "empty", "1.0.0")]
    result = generate_unified_feed(manifests, "https://docs.example.com")
    assert '<?xml version="1.0"' in result
    assert "<feed" in result
    assert "</feed>" in result
    assert "<entry>" not in result


# -- generate_sitemap ---------------------------------------------------------


def test_sitemap_all_pages():
    """Manifests with pages: all page URLs present."""
    manifests = [
        _make_manifest("Proj", "proj", "1.0.0", pages=[
            {"path": "guide.md", "title": "Guide"},
            {"path": "api.md", "title": "API"},
        ]),
    ]
    result = generate_sitemap(manifests, "https://docs.example.com")
    assert "https://docs.example.com/proj/guide/" in result
    assert "https://docs.example.com/proj/api/" in result


def test_sitemap_all_posts():
    """Manifests with posts: post URLs present."""
    manifests = [
        _make_manifest("Proj", "proj", "1.0.0", posts=[
            {"slug": "my-post", "title": "My Post", "date": "2024-01-01"},
        ]),
    ]
    result = generate_sitemap(manifests, "https://docs.example.com")
    assert "https://docs.example.com/proj/posts/my-post/" in result


def test_sitemap_page_path_conversion():
    """guide.md -> guide/, index.md -> just slug root."""
    manifests = [
        _make_manifest("Proj", "proj", "1.0.0", pages=[
            {"path": "guide.md", "title": "Guide"},
            {"path": "index.md", "title": "Index"},
        ]),
    ]
    result = generate_sitemap(manifests, "https://docs.example.com")
    assert "https://docs.example.com/proj/guide/" in result
    # index.md maps to the slug root (empty segment -> just proj/)
    assert "https://docs.example.com/proj/" in result


def test_sitemap_sorted_urls():
    """URLs are alphabetically sorted."""
    manifests = [
        _make_manifest("Proj", "proj", "1.0.0", pages=[
            {"path": "zebra.md", "title": "Zebra"},
            {"path": "alpha.md", "title": "Alpha"},
        ]),
    ]
    result = generate_sitemap(manifests, "https://docs.example.com")
    alpha_pos = result.index("proj/alpha/")
    zebra_pos = result.index("proj/zebra/")
    assert alpha_pos < zebra_pos


def test_sitemap_valid_xml_structure():
    """XML declaration and urlset namespace present."""
    manifests = [_make_manifest("Proj", "proj", "1.0.0")]
    result = generate_sitemap(manifests, "https://docs.example.com")
    assert result.startswith('<?xml version="1.0" encoding="UTF-8"?>')
    assert 'xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"' in result
    assert "</urlset>" in result


# -- validate_cross_project_links ---------------------------------------------


def test_cross_links_all_valid():
    """All targets exist in manifests: empty error list."""
    manifests = [
        _make_manifest("Proj", "proj", "1.0.0", pages=[
            {"path": "guide.md", "title": "Guide"},
        ], posts=[
            {"path": "posts/hello.md", "slug": "hello", "title": "Hello",
             "date": "2024-01-01"},
        ]),
    ]
    link_registry = {
        "index.md": ["guide.md", "proj/posts/hello"],
    }
    errors = validate_cross_project_links(manifests, link_registry)
    assert errors == []


def test_cross_links_broken():
    """Some targets don't exist: error strings returned."""
    manifests = [
        _make_manifest("Proj", "proj", "1.0.0", pages=[
            {"path": "guide.md", "title": "Guide"},
        ]),
    ]
    link_registry = {
        "index.md": ["guide.md", "nonexistent.md"],
    }
    errors = validate_cross_project_links(manifests, link_registry)
    assert len(errors) == 1
    assert "nonexistent.md" in errors[0]
    assert "index.md" in errors[0]


def test_cross_links_empty_registry():
    """Empty registry: no errors."""
    manifests = [_make_manifest("Proj", "proj", "1.0.0")]
    errors = validate_cross_project_links(manifests, {})
    assert errors == []


def test_cross_links_slug_based_paths():
    """{slug}/posts/{post_slug} paths are recognized as valid targets."""
    manifests = [
        _make_manifest("MyProj", "myproj", "1.0.0", posts=[
            {"path": "posts/update.md", "slug": "big-update",
             "title": "Big Update", "date": "2024-06-01"},
        ]),
    ]
    link_registry = {
        "overview.md": ["myproj/posts/big-update"],
    }
    errors = validate_cross_project_links(manifests, link_registry)
    assert errors == []


# -- _page_path_to_url_segment ------------------------------------------------


import pytest


@pytest.mark.parametrize(
    "path, expected",
    [
        ("index.md", ""),
        ("guide.md", "guide/"),
        ("api/index.md", "api/"),
        ("api/reference.md", "api/reference/"),
        ("deep/nested/index.md", "deep/nested/"),
    ],
)
def test_page_path_to_url_segment(path: str, expected: str):
    """Standard page paths are converted to correct URL segments."""
    assert _page_path_to_url_segment(path) == expected


def test_page_path_to_url_segment_no_md_extension():
    """Paths without .md extension still work (no stripping needed)."""
    assert _page_path_to_url_segment("guide") == "guide/"


def test_page_path_to_url_segment_bare_index_no_extension():
    """Bare 'index' without .md extension returns empty string."""
    assert _page_path_to_url_segment("index") == ""


def test_page_path_to_url_segment_nested_index_no_extension():
    """Nested index without .md extension returns parent path."""
    assert _page_path_to_url_segment("api/index") == "api/"


def test_page_path_to_url_segment_index_in_name():
    """Filename containing 'index' but not ending with it is not special-cased."""
    assert _page_path_to_url_segment("reindex.md") == "reindex/"
    assert _page_path_to_url_segment("index-page.md") == "index-page/"
