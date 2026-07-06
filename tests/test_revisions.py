"""Tests for selfdoc_core.revisions -- post revision tracking."""

import json
import os

from selfdoc_core.revisions import (
    compute_post_content_hash,
    get_last_updated,
    get_post_revisions,
    load_revisions,
    record_revision,
    save_revisions,
)


# -- Content hash determinism -------------------------------------------------


class TestContentHash:
    """Tests for compute_post_content_hash()."""

    def test_same_body_same_hash(self):
        """Identical body text produces the same hash."""
        body = "Hello world\n\nThis is a post."
        h1 = compute_post_content_hash(body)
        h2 = compute_post_content_hash(body)
        assert h1 == h2

    def test_different_body_different_hash(self):
        """Different body text produces different hashes."""
        h1 = compute_post_content_hash("Version 1 content")
        h2 = compute_post_content_hash("Version 2 content")
        assert h1 != h2

    def test_whitespace_normalization(self):
        """Trailing whitespace and extra blank lines do not affect hash."""
        body1 = "Hello world\n\nParagraph two.\n"
        body2 = "Hello world  \n\n\n\nParagraph two.  \n\n"
        assert compute_post_content_hash(body1) == compute_post_content_hash(body2)

    def test_leading_trailing_whitespace_ignored(self):
        """Leading and trailing whitespace on the whole body is stripped."""
        body1 = "Content here"
        body2 = "\n\n  Content here  \n\n"
        assert compute_post_content_hash(body1) == compute_post_content_hash(body2)

    def test_hash_is_sha256_hex(self):
        """Hash is a 64-character hex string (SHA-256)."""
        h = compute_post_content_hash("test")
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_context_independent(self):
        """Same body with different surrounding context gives same hash.

        The hash only depends on the body text, not base URLs or themes.
        """
        body = "## Section\n\nSome content here."
        h1 = compute_post_content_hash(body)
        # Same body, different "context" (but we only pass body, not context)
        h2 = compute_post_content_hash(body)
        assert h1 == h2


# -- Load and save revisions --------------------------------------------------


class TestLoadSaveRevisions:
    """Tests for load_revisions() and save_revisions()."""

    def test_load_nonexistent(self, tmp_path):
        """Loading from a directory without revisions.json returns empty."""
        data = load_revisions(str(tmp_path))
        assert data == {"posts": {}}

    def test_save_and_load_roundtrip(self, tmp_path):
        """Data saved with save_revisions can be loaded back."""
        data = {
            "posts": {
                "my-slug": {
                    "revisions": [
                        {
                            "content_hash": "abc123",
                            "timestamp": "2026-07-05T12:00:00Z",
                            "summary": "Initial",
                        }
                    ]
                }
            }
        }
        save_revisions(data, str(tmp_path))
        loaded = load_revisions(str(tmp_path))
        assert loaded == data

    def test_save_creates_selfdoc_dir(self, tmp_path):
        """save_revisions creates .selfdoc/ if it does not exist."""
        save_revisions({"posts": {}}, str(tmp_path))
        assert (tmp_path / ".selfdoc" / "revisions.json").exists()


# -- Record revision ---------------------------------------------------------


class TestRecordRevision:
    """Tests for record_revision()."""

    def test_first_revision_recorded(self, tmp_path):
        """First call to record_revision creates a revision entry."""
        changed = record_revision(
            str(tmp_path), "my-post", "Hello world", summary="Initial publish",
        )
        assert changed is True
        revisions = get_post_revisions(str(tmp_path), "my-post")
        assert len(revisions) == 1
        assert revisions[0]["summary"] == "Initial publish"
        assert "content_hash" in revisions[0]
        assert "timestamp" in revisions[0]

    def test_same_body_no_new_revision(self, tmp_path):
        """Publishing with unchanged body does NOT add a revision."""
        record_revision(str(tmp_path), "my-post", "Hello world")
        changed = record_revision(str(tmp_path), "my-post", "Hello world")
        assert changed is False
        revisions = get_post_revisions(str(tmp_path), "my-post")
        assert len(revisions) == 1

    def test_changed_body_adds_revision(self, tmp_path):
        """Publishing with changed body adds a new revision."""
        record_revision(str(tmp_path), "my-post", "Version 1")
        changed = record_revision(
            str(tmp_path), "my-post", "Version 2",
            summary="Updated examples",
        )
        assert changed is True
        revisions = get_post_revisions(str(tmp_path), "my-post")
        assert len(revisions) == 2
        assert revisions[1]["summary"] == "Updated examples"

    def test_multiple_posts_independent(self, tmp_path):
        """Revisions for different slugs are tracked independently."""
        record_revision(str(tmp_path), "post-a", "Content A")
        record_revision(str(tmp_path), "post-b", "Content B")

        assert len(get_post_revisions(str(tmp_path), "post-a")) == 1
        assert len(get_post_revisions(str(tmp_path), "post-b")) == 1

    def test_whitespace_only_change_no_revision(self, tmp_path):
        """Whitespace-only changes do not create a new revision."""
        record_revision(str(tmp_path), "slug", "Content here")
        changed = record_revision(str(tmp_path), "slug", "  Content here  \n\n")
        assert changed is False
        assert len(get_post_revisions(str(tmp_path), "slug")) == 1

    def test_summary_optional(self, tmp_path):
        """When summary is empty, it is not included in the entry."""
        record_revision(str(tmp_path), "slug", "Body text")
        revisions = get_post_revisions(str(tmp_path), "slug")
        assert "summary" not in revisions[0]


# -- Get helpers ---------------------------------------------------------------


class TestGetHelpers:
    """Tests for get_post_revisions() and get_last_updated()."""

    def test_get_revisions_nonexistent_slug(self, tmp_path):
        """Returns empty list for a slug with no revisions."""
        assert get_post_revisions(str(tmp_path), "no-such-slug") == []

    def test_get_last_updated_with_revisions(self, tmp_path):
        """Returns the timestamp of the most recent revision."""
        record_revision(str(tmp_path), "slug", "V1")
        record_revision(str(tmp_path), "slug", "V2")
        ts = get_last_updated(str(tmp_path), "slug")
        assert ts is not None
        # The second revision's timestamp should be later
        revisions = get_post_revisions(str(tmp_path), "slug")
        assert ts == revisions[-1]["timestamp"]

    def test_get_last_updated_no_revisions(self, tmp_path):
        """Returns None when no revisions exist for the slug."""
        assert get_last_updated(str(tmp_path), "no-slug") is None
