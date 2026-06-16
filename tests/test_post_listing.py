"""Tests for post listing: nav grouping, listing renderer, and full build integration."""

from __future__ import annotations

import json
import os

import pytest

from selfdoc.build import build, _render_post_listing, _inject_posts_into_docs
from selfdoc.html import _build_nav
from conftest import default_config


# -- Nav tests: _build_nav with posts -----------------------------------------


class TestNavPostsGroupSeparation:
    """Posts (type: post) get their own nav group, non-posts stay in General."""

    def test_nav_posts_group_separate_from_general(self):
        """Posts appear in a 'Posts' group and non-posts in 'General'."""
        markdown_files = {
            "index.md": "# Home",
            "guide.md": "# Guide",
        }
        frontmatter = {
            "index.md": {"title": "Home"},
            "guide.md": {"title": "Guide"},
        }
        unversioned_pages = {
            "posts/hello.md": "content",
            "about.md": "content",
        }
        unversioned_frontmatter = {
            "posts/hello.md": {
                "title": "Hello Post",
                "type": "post",
                "date": "2024-06-15",
            },
            "about.md": {"title": "About"},
        }

        nav = _build_nav(
            markdown_files,
            frontmatter=frontmatter,
            unversioned_pages=unversioned_pages,
            unversioned_frontmatter=unversioned_frontmatter,
        )

        group_names = [item["group"] for item in nav if "group" in item]
        assert "Posts" in group_names
        assert "General" in group_names

        posts_group = next(g for g in nav if g.get("group") == "Posts")
        general_group = next(g for g in nav if g.get("group") == "General")

        post_labels = {item["label"] for item in posts_group["items"]}
        general_labels = {item["label"] for item in general_group["items"]}

        assert "Hello Post" in post_labels
        assert "About" in general_labels
        assert "Hello Post" not in general_labels
        assert "About" not in post_labels


class TestNavPostsSortedByDate:
    """Posts in nav are sorted by date descending (newest first)."""

    def test_nav_posts_sorted_by_date_descending(self):
        """Multiple posts appear newest-first based on their date."""
        unversioned_pages = {
            "posts/old.md": "content",
            "posts/mid.md": "content",
            "posts/new.md": "content",
        }
        unversioned_frontmatter = {
            "posts/old.md": {
                "title": "Old Post",
                "type": "post",
                "date": "2023-01-01",
            },
            "posts/mid.md": {
                "title": "Mid Post",
                "type": "post",
                "date": "2024-06-15",
            },
            "posts/new.md": {
                "title": "New Post",
                "type": "post",
                "date": "2025-12-31",
            },
        }

        nav = _build_nav(
            {"index.md": "# Home"},
            unversioned_pages=unversioned_pages,
            unversioned_frontmatter=unversioned_frontmatter,
        )

        posts_group = next(g for g in nav if g.get("group") == "Posts")
        labels = [item["label"] for item in posts_group["items"]]
        assert labels == ["New Post", "Mid Post", "Old Post"]


class TestNavPostsGroupMarker:
    """Posts group carries unversioned: True marker."""

    def test_nav_posts_group_has_unversioned_marker(self):
        """The Posts group itself has unversioned: True."""
        unversioned_pages = {
            "posts/hello.md": "content",
        }
        unversioned_frontmatter = {
            "posts/hello.md": {
                "title": "Hello Post",
                "type": "post",
                "date": "2024-06-15",
            },
        }

        nav = _build_nav(
            {"index.md": "# Home"},
            unversioned_pages=unversioned_pages,
            unversioned_frontmatter=unversioned_frontmatter,
        )

        posts_group = next(g for g in nav if g.get("group") == "Posts")
        assert posts_group["unversioned"] is True


class TestNavPostsBeforeGeneral:
    """Posts group appears before the General group in the nav."""

    def test_nav_posts_before_general(self):
        """When both Posts and General groups exist, Posts comes first."""
        unversioned_pages = {
            "posts/hello.md": "content",
            "about.md": "content",
        }
        unversioned_frontmatter = {
            "posts/hello.md": {
                "title": "Hello Post",
                "type": "post",
                "date": "2024-06-15",
            },
            "about.md": {"title": "About"},
        }

        nav = _build_nav(
            {"index.md": "# Home"},
            unversioned_pages=unversioned_pages,
            unversioned_frontmatter=unversioned_frontmatter,
        )

        groups = [item for item in nav if "group" in item]
        group_names = [g["group"] for g in groups]
        posts_idx = group_names.index("Posts")
        general_idx = group_names.index("General")
        assert posts_idx < general_idx


class TestNavOnlyPosts:
    """When all unversioned pages are posts, no General group appears."""

    def test_nav_only_posts_no_general(self):
        """Only posts in unversioned_pages produces Posts group but not General."""
        unversioned_pages = {
            "posts/hello.md": "content",
            "posts/world.md": "content",
        }
        unversioned_frontmatter = {
            "posts/hello.md": {
                "title": "Hello Post",
                "type": "post",
                "date": "2024-06-15",
            },
            "posts/world.md": {
                "title": "World Post",
                "type": "post",
                "date": "2024-06-16",
            },
        }

        nav = _build_nav(
            {"index.md": "# Home"},
            unversioned_pages=unversioned_pages,
            unversioned_frontmatter=unversioned_frontmatter,
        )

        group_names = [item["group"] for item in nav if "group" in item]
        assert "Posts" in group_names
        assert "General" not in group_names


class TestNavOnlyGeneral:
    """When no posts exist, only General group appears (existing behavior)."""

    def test_nav_only_general_no_posts(self):
        """Non-post unversioned pages produce General group only."""
        unversioned_pages = {
            "about.md": "content",
            "terms.md": "content",
        }
        unversioned_frontmatter = {
            "about.md": {"title": "About"},
            "terms.md": {"title": "Terms"},
        }

        nav = _build_nav(
            {"index.md": "# Home"},
            unversioned_pages=unversioned_pages,
            unversioned_frontmatter=unversioned_frontmatter,
        )

        group_names = [item["group"] for item in nav if "group" in item]
        assert "General" in group_names
        assert "Posts" not in group_names


# -- Listing renderer tests: _render_post_listing -----------------------------


class TestRenderPostListingBasic:
    """_render_post_listing renders a listing with date, title, and link."""

    def test_render_post_listing_basic(self):
        """Single post renders with date, title, and link to slug."""
        posts = [
            {"date": "2024-06-15", "title": "Hello World", "slug": "hello-world"},
        ]

        result = _render_post_listing(posts)

        assert "**2024-06-15**" in result
        assert "[Hello World]" in result
        assert "posts/hello-world.html" in result


class TestRenderPostListingMultiple:
    """_render_post_listing lists multiple posts in provided order."""

    def test_render_post_listing_multiple_posts(self):
        """Multiple posts are listed in the order given."""
        posts = [
            {"date": "2024-06-16", "title": "Second Post", "slug": "second-post"},
            {"date": "2024-06-15", "title": "First Post", "slug": "first-post"},
        ]

        result = _render_post_listing(posts)

        lines = result.strip().splitlines()
        # Find the list item lines
        list_lines = [line for line in lines if line.startswith("- ")]
        assert len(list_lines) == 2
        assert "Second Post" in list_lines[0]
        assert "First Post" in list_lines[1]


class TestRenderPostListingEmpty:
    """_render_post_listing with no posts shows placeholder text."""

    def test_render_post_listing_empty(self):
        """Empty post list renders 'No posts yet.' message."""
        result = _render_post_listing([])

        assert "No posts yet." in result


class TestRenderPostListingFrontmatter:
    """_render_post_listing output has versioned: false and type: post-listing."""

    def test_render_post_listing_frontmatter(self):
        """Listing page frontmatter has versioned: false and type: post-listing."""
        posts = [
            {"date": "2024-06-15", "title": "Hello", "slug": "hello"},
        ]

        result = _render_post_listing(posts)

        # The frontmatter is between --- fences at the top
        assert result.startswith("---\n")
        # Extract frontmatter block
        parts = result.split("---", 2)
        fm_text = parts[1]
        assert "versioned: false" in fm_text
        assert "type: post-listing" in fm_text


# -- Integration tests: full build with listing --------------------------------


_POST_ALPHA = (
    "alpha.md",
    "---\ntitle: Alpha Post\ndate: 2024-06-10\nslug: alpha-post\n"
    "tags: []\ndraft: false\n---\n# Alpha Post\n\nAlpha content.\n",
)

_POST_BETA = (
    "beta.md",
    "---\ntitle: Beta Post\ndate: 2024-06-12\nslug: beta-post\n"
    "tags: []\ndraft: false\n---\n# Beta Post\n\nBeta content.\n",
)


def _setup_project_with_posts(tmp_path, posts=None, config_overrides=None):
    """Create a minimal selfdoc project with optional posts.

    Posts are written to ``.selfdoc/posts/`` (the default posts directory).
    Each entry in *posts* is ``(filename, content)`` where *content* is the
    full markdown including frontmatter fences.
    """
    config = default_config(docs="docs/", output="docs/_build/")
    if config_overrides:
        config.update(config_overrides)

    with open(os.path.join(tmp_path, "selfdoc.json"), "w") as f:
        json.dump(config, f)

    src_dir = os.path.join(tmp_path, "src")
    os.makedirs(src_dir, exist_ok=True)
    with open(os.path.join(src_dir, "__init__.py"), "w") as f:
        f.write('"""Example package."""\n')

    docs_dir = os.path.join(tmp_path, "docs")
    os.makedirs(docs_dir, exist_ok=True)
    with open(os.path.join(docs_dir, "index.md"), "w") as f:
        f.write("# Test Project\n\nWelcome.\n")

    if posts:
        posts_dir = os.path.join(tmp_path, ".selfdoc", "posts")
        os.makedirs(posts_dir, exist_ok=True)
        for filename, content in posts:
            path = os.path.join(posts_dir, filename)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w") as f:
                f.write(content)

    return tmp_path


class TestBuildGeneratesListingPage:
    """Full build produces a listing page at en/posts/index.html."""

    def test_build_generates_listing_page(self, tmp_path):
        """Listing page exists in build output under en/posts/."""
        project = _setup_project_with_posts(tmp_path, posts=[_POST_ALPHA])

        written = build(str(project))

        output_dir = os.path.join(project, "docs", "_build")
        # posts/index.md maps to posts/index/index.html via _md_to_html_path
        listing_html = os.path.join(
            output_dir, "en", "posts", "index", "index.html",
        )
        assert listing_html in written
        assert os.path.isfile(listing_html)


class TestListingPageContainsPostLinks:
    """Listing page HTML contains links to individual posts."""

    def test_listing_page_contains_post_links(self, tmp_path):
        """Listing HTML contains links to both posts."""
        project = _setup_project_with_posts(
            tmp_path, posts=[_POST_ALPHA, _POST_BETA],
        )

        build(str(project))

        output_dir = os.path.join(project, "docs", "_build")
        # posts/index.md maps to posts/index/index.html via _md_to_html_path
        listing_html_path = os.path.join(
            output_dir, "en", "posts", "index", "index.html",
        )
        assert os.path.isfile(listing_html_path)

        content = open(listing_html_path).read()
        assert "Alpha Post" in content
        assert "Beta Post" in content
        assert "alpha-post" in content
        assert "beta-post" in content
