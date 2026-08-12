"""Tests for git-based slug immutability checking.

These tests verify that ``discover_posts`` compares post slugs against
the *committed* manifest (from git HEAD), not the on-disk manifest.
This prevents silent slug changes when ``selfdoc gen`` regenerates the
manifest before the check runs.
"""

from __future__ import annotations

import json
import os
import subprocess

import pytest

from selfdoc.manifest import load_manifest_from_git
from selfblog.posts import discover_posts


def _git(cwd: str, *args: str) -> subprocess.CompletedProcess:
    """Run a git command in the given directory."""
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=10,
        check=True,
    )


def _init_repo(path: str) -> None:
    """Create a git repo with an initial commit."""
    _git(path, "init")
    _git(path, "config", "user.email", "test@test.com")
    _git(path, "config", "user.name", "Test")
    readme = os.path.join(path, "README.md")
    with open(readme, "w") as f:
        f.write("# test\n")
    _git(path, "add", "README.md")
    _git(path, "commit", "-m", "init")


def _write_manifest(dir_path: str, posts: list[dict]) -> str:
    """Write a manifest.json under .selfdoc/ and return its path."""
    selfdoc_dir = os.path.join(dir_path, ".selfdoc")
    os.makedirs(selfdoc_dir, exist_ok=True)
    manifest_path = os.path.join(selfdoc_dir, "manifest.json")
    data = {
        "schema_version": 1,
        "name": "test",
        "slug": "test",
        "version": "0.1.0",
        "description": "",
        "language": "python",
        "base_url": "",
        "author": {"name": "Test Author", "url": "https://author.example"},
        "pages": [],
        "posts": posts,
        "last_gen": "2025-01-01T00:00:00+00:00",
    }
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    return manifest_path


def _write_post(posts_dir: str, filename: str, title: str, date: str,
                slug: str | None = None) -> None:
    """Write a minimal blog post markdown file."""
    os.makedirs(posts_dir, exist_ok=True)
    lines = [
        "---",
        f"title: {title}",
        f"date: {date}",
    ]
    if slug is not None:
        lines.append(f"slug: {slug}")
    lines.append("directives: false")
    lines.extend(["---", "", "Post body."])
    with open(os.path.join(posts_dir, filename), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


# -- load_manifest_from_git unit tests ------------------------------------


class TestLoadManifestFromGit:
    """Unit tests for the new load_manifest_from_git function."""

    def test_not_a_git_repo(self, tmp_path):
        """Not a git repo -> returns None, no error."""
        result = load_manifest_from_git(str(tmp_path))
        assert result is None

    def test_git_repo_no_commits(self, tmp_path):
        """Git repo with no commits -> returns None (HEAD doesn't exist)."""
        subprocess.run(
            ["git", "init"],
            cwd=str(tmp_path),
            capture_output=True,
            timeout=10,
            check=True,
        )
        result = load_manifest_from_git(str(tmp_path))
        assert result is None

    def test_git_repo_manifest_never_committed(self, tmp_path):
        """Git repo with commits but manifest never committed -> None."""
        _init_repo(str(tmp_path))
        # Write manifest to disk but don't commit it
        _write_manifest(str(tmp_path), [])
        result = load_manifest_from_git(str(tmp_path))
        assert result is None

    def test_git_repo_manifest_committed(self, tmp_path):
        """Git repo with committed manifest -> returns the Manifest."""
        _init_repo(str(tmp_path))
        _write_manifest(str(tmp_path), [
            {"path": "hello.md", "title": "Hello", "date": "2025-01-01",
             "slug": "hello", "tags": []},
        ])
        _git(str(tmp_path), "add", ".selfdoc/manifest.json")
        _git(str(tmp_path), "commit", "-m", "add manifest")

        result = load_manifest_from_git(str(tmp_path))
        assert result is not None
        assert result.name == "test"
        assert len(result.posts) == 1
        assert result.posts[0]["slug"] == "hello"

    def test_reads_committed_not_disk(self, tmp_path):
        """After committing then modifying on disk, reads the committed version."""
        _init_repo(str(tmp_path))
        # Commit manifest with slug "hello-old"
        _write_manifest(str(tmp_path), [
            {"path": "hello.md", "title": "Hello", "date": "2025-01-01",
             "slug": "hello-old", "tags": []},
        ])
        _git(str(tmp_path), "add", ".selfdoc/manifest.json")
        _git(str(tmp_path), "commit", "-m", "add manifest")

        # Overwrite on disk with slug "hello-new" (simulating selfdoc gen)
        _write_manifest(str(tmp_path), [
            {"path": "hello.md", "title": "Hello", "date": "2025-01-01",
             "slug": "hello-new", "tags": []},
        ])

        result = load_manifest_from_git(str(tmp_path))
        assert result is not None
        # Must read the COMMITTED version, not the on-disk one
        assert result.posts[0]["slug"] == "hello-old"

    def test_git_error_propagates(self, tmp_path):
        """Unexpected git errors (not 1 or 128) propagate as RuntimeError."""
        _init_repo(str(tmp_path))
        # Corrupt the git directory to trigger an unexpected error
        git_dir = os.path.join(str(tmp_path), ".git")
        # Remove HEAD to cause an unexpected failure
        head_path = os.path.join(git_dir, "HEAD")
        with open(head_path, "w") as f:
            f.write("ref: refs/heads/nonexistent\n")
        # This should still gracefully handle "no commits" (exit 128)
        # because the ref doesn't resolve -- that's the same as no commits
        result = load_manifest_from_git(str(tmp_path))
        assert result is None


# -- discover_posts git-based immutability tests ---------------------------


class TestSlugImmutabilityGit:
    """Integration tests: discover_posts uses git manifest for slug checks."""

    def test_slug_unchanged_passes(self, tmp_path):
        """Post slug matches committed manifest slug -> no error."""
        _init_repo(str(tmp_path))
        posts_dir = os.path.join(str(tmp_path), ".selfdoc", "posts")
        _write_post(posts_dir, "hello.md", "Hello", "2025-01-01",
                     slug="hello")

        # Commit manifest with same slug
        _write_manifest(str(tmp_path), [
            {"path": "hello.md", "title": "Hello", "date": "2025-01-01",
             "slug": "hello", "tags": []},
        ])
        _git(str(tmp_path), "add", ".selfdoc/manifest.json")
        _git(str(tmp_path), "commit", "-m", "add manifest")

        manifest_path = os.path.join(str(tmp_path), ".selfdoc",
                                      "manifest.json")
        result = discover_posts(posts_dir, manifest_path=manifest_path)
        assert len(result) == 1
        assert result[0]["slug"] == "hello"

    def test_slug_changed_raises(self, tmp_path):
        """Post slug differs from committed manifest -> RuntimeError."""
        _init_repo(str(tmp_path))
        posts_dir = os.path.join(str(tmp_path), ".selfdoc", "posts")
        _write_post(posts_dir, "hello.md", "Hello", "2025-01-01",
                     slug="hello-new")

        # Commit manifest with old slug
        _write_manifest(str(tmp_path), [
            {"path": "hello.md", "title": "Hello", "date": "2025-01-01",
             "slug": "hello-old", "tags": []},
        ])
        _git(str(tmp_path), "add", ".selfdoc/manifest.json")
        _git(str(tmp_path), "commit", "-m", "add manifest")

        # Even if on-disk manifest is updated to the new slug...
        _write_manifest(str(tmp_path), [
            {"path": "hello.md", "title": "Hello", "date": "2025-01-01",
             "slug": "hello-new", "tags": []},
        ])

        manifest_path = os.path.join(str(tmp_path), ".selfdoc",
                                      "manifest.json")
        with pytest.raises(RuntimeError, match="Slug immutability violation"):
            discover_posts(posts_dir, manifest_path=manifest_path)

    def test_new_post_not_in_manifest_passes(self, tmp_path):
        """New post not in committed manifest -> passes (no old slug)."""
        _init_repo(str(tmp_path))
        posts_dir = os.path.join(str(tmp_path), ".selfdoc", "posts")
        _write_post(posts_dir, "new-post.md", "New Post", "2025-06-01",
                     slug="new-post")

        # Commit manifest WITHOUT this post
        _write_manifest(str(tmp_path), [])
        _git(str(tmp_path), "add", ".selfdoc/manifest.json")
        _git(str(tmp_path), "commit", "-m", "add manifest")

        manifest_path = os.path.join(str(tmp_path), ".selfdoc",
                                      "manifest.json")
        result = discover_posts(posts_dir, manifest_path=manifest_path)
        assert len(result) == 1
        assert result[0]["slug"] == "new-post"

    def test_not_a_git_repo_skips_check(self, tmp_path):
        """Not a git repo -> slug check skipped entirely, no error."""
        posts_dir = os.path.join(str(tmp_path), ".selfdoc", "posts")
        _write_post(posts_dir, "hello.md", "Hello", "2025-01-01",
                     slug="hello-new")

        # Write manifest with DIFFERENT slug on disk
        _write_manifest(str(tmp_path), [
            {"path": "hello.md", "title": "Hello", "date": "2025-01-01",
             "slug": "hello-old", "tags": []},
        ])

        manifest_path = os.path.join(str(tmp_path), ".selfdoc",
                                      "manifest.json")
        # Should NOT raise -- git check is skipped, falls through
        result = discover_posts(posts_dir, manifest_path=manifest_path)
        assert len(result) == 1

    def test_manifest_never_committed_skips_check(self, tmp_path):
        """Git repo but manifest not committed -> check skipped."""
        _init_repo(str(tmp_path))
        posts_dir = os.path.join(str(tmp_path), ".selfdoc", "posts")
        _write_post(posts_dir, "hello.md", "Hello", "2025-01-01",
                     slug="hello-new")

        # Manifest exists on disk with different slug but is NOT committed
        _write_manifest(str(tmp_path), [
            {"path": "hello.md", "title": "Hello", "date": "2025-01-01",
             "slug": "hello-old", "tags": []},
        ])

        manifest_path = os.path.join(str(tmp_path), ".selfdoc",
                                      "manifest.json")
        # Should NOT raise -- no committed manifest to check against
        result = discover_posts(posts_dir, manifest_path=manifest_path)
        assert len(result) == 1

    def test_disk_manifest_slug_changed_but_committed_same(self, tmp_path):
        """On-disk manifest has new slug, committed has old -> catches it.

        This is the KEY scenario: selfdoc gen has already regenerated
        manifest.json on disk with the new slug. The old code would read
        from disk and see no difference. The new code reads from git and
        catches the change.
        """
        _init_repo(str(tmp_path))
        posts_dir = os.path.join(str(tmp_path), ".selfdoc", "posts")

        # Commit manifest with old slug
        _write_manifest(str(tmp_path), [
            {"path": "hello.md", "title": "Hello", "date": "2025-01-01",
             "slug": "hello-old", "tags": []},
        ])
        _git(str(tmp_path), "add", ".selfdoc/manifest.json")
        _git(str(tmp_path), "commit", "-m", "add manifest")

        # Write post with NEW slug
        _write_post(posts_dir, "hello.md", "Hello", "2025-01-01",
                     slug="hello-new")

        # Overwrite disk manifest with new slug (simulating gen)
        _write_manifest(str(tmp_path), [
            {"path": "hello.md", "title": "Hello", "date": "2025-01-01",
             "slug": "hello-new", "tags": []},
        ])

        manifest_path = os.path.join(str(tmp_path), ".selfdoc",
                                      "manifest.json")
        # OLD code: reads disk manifest (hello-new == hello-new) -> PASSES (wrong!)
        # NEW code: reads git manifest (hello-old != hello-new) -> RAISES (correct!)
        with pytest.raises(RuntimeError, match="Slug immutability violation"):
            discover_posts(posts_dir, manifest_path=manifest_path)
