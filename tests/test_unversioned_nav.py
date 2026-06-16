"""Tests for Phase 2 Task 2.2: unversioned nav group in _build_nav.

Verifies that:
- _build_nav works unchanged when no unversioned_pages are provided
- Unversioned pages appear as a "General" group at the end of the nav
- Unversioned items carry an "unversioned": True marker
- Unversioned nav uses frontmatter titles
- Unversioned items are sorted by nav_order
- The "General" group is always the last nav entry
- Empty or None unversioned_pages produce no General group
"""

from selfdoc.html import _build_nav


class TestNavWithoutUnversioned:
    """Backward-compatible: _build_nav with no unversioned pages."""

    def test_nav_without_unversioned(self):
        """No 'General' group appears when unversioned_pages is omitted."""
        markdown_files = {
            "index.md": "# Home\nWelcome.",
            "guide.md": "# Guide\nSome guide.",
        }
        frontmatter = {
            "index.md": {"title": "Home"},
            "guide.md": {"title": "User Guide"},
        }

        nav = _build_nav(markdown_files, frontmatter=frontmatter)

        # Should have two ungrouped items, no groups at all
        assert len(nav) == 2
        for item in nav:
            assert "group" not in item
            assert "unversioned" not in item


class TestNavWithUnversionedPages:
    """_build_nav with unversioned_pages appends a General group."""

    def test_nav_with_unversioned_pages(self):
        """Regular pages appear first; General group with unversioned
        pages appears at the end."""
        markdown_files = {
            "index.md": "# Home\nWelcome.",
            "guide.md": "# Guide\nSome guide.",
        }
        frontmatter = {
            "index.md": {"title": "Home"},
            "guide.md": {"title": "User Guide"},
        }
        unversioned_pages = {
            "about.md": "# About\nAbout us.",
            "terms.md": "# Terms\nTerms of service.",
        }
        unversioned_frontmatter = {
            "about.md": {"title": "About Us"},
            "terms.md": {"title": "Terms of Service"},
        }

        nav = _build_nav(
            markdown_files,
            frontmatter=frontmatter,
            unversioned_pages=unversioned_pages,
            unversioned_frontmatter=unversioned_frontmatter,
        )

        # Two ungrouped items + one General group
        assert len(nav) == 3

        # First two are regular pages
        assert nav[0]["label"] == "Home"
        assert nav[1]["label"] == "User Guide"

        # Last entry is the General group
        general = nav[-1]
        assert general["group"] == "General"
        assert general["slug"] == "general"
        assert general["unversioned"] is True

        # General group contains both unversioned pages
        labels = {item["label"] for item in general["items"]}
        assert labels == {"About Us", "Terms of Service"}

    def test_unversioned_nav_items_have_marker(self):
        """Each item inside the General group has 'unversioned': True."""
        unversioned_pages = {
            "about.md": "# About\nAbout us.",
            "terms.md": "# Terms\nTerms of service.",
        }

        nav = _build_nav(
            {"index.md": "# Home"},
            unversioned_pages=unversioned_pages,
        )

        general = nav[-1]
        assert general["group"] == "General"
        for item in general["items"]:
            assert item.get("unversioned") is True, (
                f"Item {item['md_path']!r} missing unversioned marker"
            )

    def test_unversioned_nav_uses_frontmatter_title(self):
        """Unversioned items use titles from unversioned_frontmatter."""
        unversioned_pages = {
            "about.md": "# About\nAbout us.",
        }
        unversioned_frontmatter = {
            "about.md": {"title": "About Our Project"},
        }

        nav = _build_nav(
            {"index.md": "# Home"},
            unversioned_pages=unversioned_pages,
            unversioned_frontmatter=unversioned_frontmatter,
        )

        general = nav[-1]
        assert general["items"][0]["label"] == "About Our Project"

    def test_unversioned_nav_falls_back_to_filename(self):
        """Without frontmatter, label falls back to filename stem."""
        unversioned_pages = {
            "about.md": "# About\nAbout us.",
        }

        nav = _build_nav(
            {"index.md": "# Home"},
            unversioned_pages=unversioned_pages,
        )

        general = nav[-1]
        assert general["items"][0]["label"] == "about"


class TestUnversionedNavOrder:
    """Unversioned items sort by nav_order, then alphabetically."""

    def test_unversioned_nav_sorted_by_nav_order(self):
        """Items with different nav_order appear in correct order."""
        unversioned_pages = {
            "alpha.md": "# Alpha",
            "beta.md": "# Beta",
            "gamma.md": "# Gamma",
        }
        unversioned_frontmatter = {
            "alpha.md": {"title": "Alpha", "nav_order": 3},
            "beta.md": {"title": "Beta", "nav_order": 1},
            "gamma.md": {"title": "Gamma", "nav_order": 2},
        }

        nav = _build_nav(
            {"index.md": "# Home"},
            unversioned_pages=unversioned_pages,
            unversioned_frontmatter=unversioned_frontmatter,
        )

        general = nav[-1]
        labels = [item["label"] for item in general["items"]]
        assert labels == ["Beta", "Gamma", "Alpha"]

    def test_unversioned_nav_ties_broken_alphabetically(self):
        """Items with the same nav_order are sorted by md_path."""
        unversioned_pages = {
            "zebra.md": "# Zebra",
            "apple.md": "# Apple",
        }
        unversioned_frontmatter = {
            "zebra.md": {"title": "Zebra", "nav_order": 1},
            "apple.md": {"title": "Apple", "nav_order": 1},
        }

        nav = _build_nav(
            {"index.md": "# Home"},
            unversioned_pages=unversioned_pages,
            unversioned_frontmatter=unversioned_frontmatter,
        )

        general = nav[-1]
        labels = [item["label"] for item in general["items"]]
        assert labels == ["Apple", "Zebra"]


class TestUnversionedGroupPosition:
    """The General group is always the last item in the nav list."""

    def test_unversioned_group_always_last(self):
        """With multiple regular groups, General is still last."""
        markdown_files = {
            "index.md": "# Home",
            "guide.md": "# Guide",
            "api/endpoints.md": "# Endpoints",
            "api/auth.md": "# Auth",
            "tutorials/quickstart.md": "# Quickstart",
        }
        frontmatter = {
            "index.md": {"title": "Home"},
            "guide.md": {"title": "Guide"},
            "api/endpoints.md": {"title": "Endpoints"},
            "api/auth.md": {"title": "Auth"},
            "tutorials/quickstart.md": {"title": "Quickstart"},
        }
        unversioned_pages = {
            "about.md": "# About",
        }
        unversioned_frontmatter = {
            "about.md": {"title": "About"},
        }

        nav = _build_nav(
            markdown_files,
            frontmatter=frontmatter,
            unversioned_pages=unversioned_pages,
            unversioned_frontmatter=unversioned_frontmatter,
        )

        # Should have: Home, Guide (ungrouped), Api group, Tutorials group, General group
        # General must be last
        last = nav[-1]
        assert last["group"] == "General"
        assert last["unversioned"] is True

        # Verify the other groups exist before it
        group_names = [item["group"] for item in nav if "group" in item]
        assert "General" in group_names
        # General is the last group
        assert group_names[-1] == "General"


class TestNoGeneralGroupOnEmpty:
    """Empty or None unversioned_pages should not create a General group."""

    def test_empty_unversioned_pages_no_group(self):
        """unversioned_pages={} produces no General group."""
        nav = _build_nav(
            {"index.md": "# Home", "guide.md": "# Guide"},
            unversioned_pages={},
        )

        for item in nav:
            if "group" in item:
                assert item["group"] != "General", (
                    "General group should not appear for empty dict"
                )

    def test_unversioned_none_no_group(self):
        """unversioned_pages=None (default) produces no General group."""
        nav = _build_nav(
            {"index.md": "# Home", "guide.md": "# Guide"},
            unversioned_pages=None,
        )

        for item in nav:
            if "group" in item:
                assert item["group"] != "General", (
                    "General group should not appear for None"
                )
