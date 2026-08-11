"""The in-memory render path: same bytes as a build, no writes at all.

``render_post`` exists so an editor can preview an unsaved buffer.  Two
properties are what make it useful, and both are asserted here: the HTML
is byte-identical to what a real build writes for the same content saved
to disk, and the call leaves the working tree exactly as it found it.
"""

from __future__ import annotations

import hashlib
import json
import os

import pytest

from selfdoc.build import build
from selfdoc_core.build import build_single
from selfdoc_core.render import render_post
from conftest import default_config


_POST_HELLO = (
    "hello.md",
    "---\ntitle: Hello World\ndate: 2024-01-15\nslug: hello-world\n"
    "tags: [release]\ndraft: false\n---\n"
    "# Hello World\n\nThis is the post content.\n\n"
    "## Setup\n\nFirst.\n\n## Setup\n\nSecond.\n",
)

_POST_SECOND = (
    "second.md",
    "---\ntitle: Second Post\ndate: 2024-02-01\nslug: second-post\n"
    "tags: []\ndraft: false\n---\nSecond post body.\n",
)

_POST_DRAFT = (
    "draft.md",
    "---\ntitle: Draft Post\ndate: 2024-03-01\nslug: draft-post\n"
    "tags: []\ndraft: true\n---\nUnfinished.\n",
)


def _make_project(tmp_path, posts):
    """A minimal project with *posts* written to .selfdoc/posts/."""
    project = str(tmp_path)
    with open(os.path.join(project, "selfdoc.json"), "w") as f:
        json.dump(default_config(docs="docs/", output="docs/_build/"), f)

    src_dir = os.path.join(project, "src")
    os.makedirs(src_dir, exist_ok=True)
    with open(os.path.join(src_dir, "__init__.py"), "w") as f:
        f.write('"""Example package."""\n')

    docs_dir = os.path.join(project, "docs")
    os.makedirs(docs_dir, exist_ok=True)
    with open(os.path.join(docs_dir, "index.md"), "w") as f:
        f.write("# Test Project\n\nWelcome.\n")

    posts_dir = os.path.join(project, ".selfdoc", "posts")
    os.makedirs(posts_dir, exist_ok=True)
    for filename, content in posts:
        with open(os.path.join(posts_dir, filename), "w") as f:
            f.write(content)

    return project


def _tree_fingerprint(root):
    """Path, size, mtime and content digest of every file under *root*.

    mtime is included on purpose: an atomic rewrite with identical bytes
    is still a write, and this notices it.
    """
    digest = hashlib.sha256()
    entries = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        for name in sorted(filenames):
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, root)
            stat = os.stat(full)
            with open(full, "rb") as f:
                body = hashlib.sha256(f.read()).hexdigest()
            entries.append((rel, stat.st_size, stat.st_mtime_ns, body))
    for entry in entries:
        digest.update(repr(entry).encode())
    return digest.hexdigest(), entries


def _built_post_bytes(project, slug):
    path = os.path.join(project, "docs", "_build", "posts", slug, "index.html")
    with open(path, "rb") as f:
        return f.read()


class TestByteIdentity:
    """The rendered buffer equals the built file, byte for byte."""

    def test_matches_built_page(self, tmp_path):
        project = _make_project(tmp_path, [_POST_HELLO, _POST_SECOND])
        build(project, target="posts")

        source = _POST_HELLO[1]
        rendered = render_post(project, "hello.md", source)

        assert rendered.encode("utf-8") == _built_post_bytes(
            project, "hello-world",
        )

    def test_matches_for_every_post(self, tmp_path):
        project = _make_project(tmp_path, [_POST_HELLO, _POST_SECOND])
        build(project, target="posts")

        for filename, source in (_POST_HELLO, _POST_SECOND):
            slug = "hello-world" if filename == "hello.md" else "second-post"
            rendered = render_post(project, filename, source)
            assert rendered.encode("utf-8") == _built_post_bytes(project, slug)

    def test_duplicate_heading_anchors_survive_the_render(self, tmp_path):
        project = _make_project(tmp_path, [_POST_HELLO])
        build(project, target="posts")

        rendered = render_post(project, "hello.md", _POST_HELLO[1])
        assert 'id="setup"' in rendered
        assert 'id="setup-1"' in rendered


class TestWritesNothing:
    """The render leaves the working tree byte-for-byte as it found it."""

    def test_no_mutation_after_build(self, tmp_path):
        project = _make_project(tmp_path, [_POST_HELLO, _POST_SECOND])
        build(project, target="posts")

        before, before_entries = _tree_fingerprint(project)
        render_post(project, "hello.md", _POST_HELLO[1])
        after, after_entries = _tree_fingerprint(project)

        assert after == before, (
            "render_post mutated the working tree: "
            f"{set(after_entries) ^ set(before_entries)}"
        )

    def test_no_mutation_without_a_prior_build(self, tmp_path):
        """Not even the staleness baselines or the docs tree get created."""
        project = _make_project(tmp_path, [_POST_HELLO])

        before, before_entries = _tree_fingerprint(project)
        render_post(project, "hello.md", _POST_HELLO[1])
        after, after_entries = _tree_fingerprint(project)

        assert after == before, (
            "render_post mutated the working tree: "
            f"{set(after_entries) ^ set(before_entries)}"
        )
        assert not os.path.isdir(os.path.join(project, "docs", "posts"))
        assert not os.path.isdir(os.path.join(project, ".selfdoc", "hashes"))

    def test_edited_buffer_is_not_written_back(self, tmp_path):
        project = _make_project(tmp_path, [_POST_HELLO])
        edited = _POST_HELLO[1].replace(
            "This is the post content.", "Edited in the buffer only.",
        )

        before, _ = _tree_fingerprint(project)
        rendered = render_post(project, "hello.md", edited)
        after, _ = _tree_fingerprint(project)

        assert "Edited in the buffer only." in rendered
        assert after == before


class TestBuildSingleWriteContract:
    """build_single writes the staleness baselines, and nothing else.

    Its docstring used to claim it wrote nothing at all, which was never
    true.  Both directions are pinned here so the claim stays honest.
    """

    def test_baselines_are_written_by_default(self, tmp_path):
        project = _make_project(tmp_path, [])
        hashes = os.path.join(project, ".selfdoc", "hashes")
        assert not os.path.isdir(hashes)

        build_single(
            dir_path=project, mount_locale="", mount_version="",
            version_override="",
        )

        assert os.path.isfile(os.path.join(hashes, "hashes.json"))

    def test_write_baselines_false_touches_nothing(self, tmp_path):
        project = _make_project(tmp_path, [])
        before, _ = _tree_fingerprint(project)

        build_single(
            dir_path=project, mount_locale="", mount_version="",
            version_override="", write_baselines=False,
        )

        after, _ = _tree_fingerprint(project)
        assert after == before


class TestUnsavedAndDraftPosts:
    def test_new_post_with_no_file_renders(self, tmp_path):
        project = _make_project(tmp_path, [_POST_HELLO])
        source = (
            "---\ntitle: Brand New\ndate: 2024-04-01\nslug: brand-new\n"
            "tags: []\ndraft: false\n---\nNever saved.\n"
        )

        before, _ = _tree_fingerprint(project)
        rendered = render_post(project, "brand-new.md", source)
        after, _ = _tree_fingerprint(project)

        assert "Never saved." in rendered
        assert after == before

    def test_draft_is_refused_unless_asked_for(self, tmp_path):
        project = _make_project(tmp_path, [_POST_DRAFT])

        with pytest.raises(RuntimeError, match="draft"):
            render_post(project, "draft.md", _POST_DRAFT[1])

    def test_draft_renders_with_include_drafts(self, tmp_path):
        project = _make_project(tmp_path, [_POST_DRAFT])

        rendered = render_post(
            project, "draft.md", _POST_DRAFT[1], include_drafts=True,
        )
        assert "Unfinished." in rendered

    def test_draft_render_matches_drafts_build(self, tmp_path):
        project = _make_project(tmp_path, [_POST_DRAFT])
        build(project, target="posts", include_drafts=True)

        rendered = render_post(
            project, "draft.md", _POST_DRAFT[1], include_drafts=True,
        )
        assert rendered.encode("utf-8") == _built_post_bytes(
            project, "draft-post",
        )
