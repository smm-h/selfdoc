"""The preview is the publish, byte for byte.

An authoring app whose preview is a second renderer is an authoring app
that lies: what you approve on screen is not what readers get.  There is
one renderer here, and this module holds the assertion that says so --
save a post, build it through the real posts build, render the same source
through the editor's preview path, compare the bytes.

The comparison is only worth anything if it can fail, so the divergence
tests mutate one input at a time and assert the bytes stop matching.
"""

from __future__ import annotations

import json
import os

import pytest

from selfblog.editor_registry import load_registry
from selfblog.editor_server import EditorState, render_preview
from selfdoc_core.build import build
from conftest import default_config

_HELLO = (
    "hello.md",
    "---\ntitle: Hello World\ndate: 2024-01-15\nslug: hello-world\n"
    "tags: [release]\ndraft: false\ndirectives: false\n---\n"
    "# Hello World\n\nThis is the post content.\n\n"
    "## Setup\n\nFirst.\n\n## Setup\n\nSecond.\n\n"
    "See [the index](../index.md) and [the other post](second.md).\n",
)

_SECOND = (
    "second.md",
    "---\ntitle: Second Post\ndate: 2024-02-01\nslug: second-post\n"
    "tags: []\ndraft: false\ndirectives: false\n---\nSecond post body.\n",
)

_DRAFT = (
    "later.md",
    "---\ntitle: Later\ndate: 2024-05-01\nslug: later\n"
    "tags: []\ndraft: true\ndirectives: false\n---\nNot yet.\n",
)


def _make_project(root, posts):
    os.makedirs(root, exist_ok=True)
    with open(os.path.join(root, "selfdoc.json"), "w", encoding="utf-8") as f:
        json.dump(default_config(docs="docs/", output="docs/_build/"), f)

    src = os.path.join(root, "src")
    os.makedirs(src, exist_ok=True)
    with open(os.path.join(src, "__init__.py"), "w", encoding="utf-8") as f:
        f.write('"""Example package."""\n')

    docs = os.path.join(root, "docs")
    os.makedirs(docs, exist_ok=True)
    with open(os.path.join(docs, "index.md"), "w", encoding="utf-8") as f:
        f.write("# Test Project\n\nWelcome.\n")

    posts_dir = os.path.join(root, ".selfdoc", "posts")
    os.makedirs(posts_dir, exist_ok=True)
    for name, body in posts:
        with open(os.path.join(posts_dir, name), "w", encoding="utf-8") as f:
            f.write(body)
    return root


def _entry(tmp_path, project, name="proj"):
    registry_path = os.path.join(str(tmp_path), "registry.toml")
    with open(registry_path, "w", encoding="utf-8") as f:
        f.write(f'[[repo]]\nname = "{name}"\nkind = "local"\n'
                f'path = "{project}"\n')
    state = EditorState(load_registry(registry_path), "")
    return state.registry.get(name)


def _published_bytes(project, slug):
    path = os.path.join(project, "docs", "_build", "blog", slug, "index.html")
    with open(path, "rb") as f:
        return f.read()


@pytest.fixture()
def published(tmp_path):
    """A project with two posts and a draft, built exactly as publish builds."""
    project = _make_project(
        os.path.join(str(tmp_path), "proj"), [_HELLO, _SECOND, _DRAFT],
    )
    build(project, target="posts")
    return {"project": project, "entry": _entry(tmp_path, project)}


class TestByteIdentity:
    def test_preview_equals_the_published_render(self, published):
        html = render_preview(published["entry"], "hello.md", _HELLO[1])
        assert html.encode("utf-8") == _published_bytes(
            published["project"], "hello-world",
        )

    def test_it_holds_for_every_published_post(self, published):
        for name, source in (_HELLO, _SECOND):
            slug = "hello-world" if name == "hello.md" else "second-post"
            html = render_preview(published["entry"], name, source)
            assert html.encode("utf-8") == _published_bytes(
                published["project"], slug,
            ), name

    def test_site_level_addressing_survives_the_preview(self, published):
        """Posts are site-level citizens; their links resolve site-level.

        The publish build and the preview share one definition of the
        site-level build arguments, and the equality above is what proves
        it -- this narrows the failure message when only addressing drifts.
        """
        html = render_preview(published["entry"], "hello.md", _HELLO[1])
        published_html = _published_bytes(
            published["project"], "hello-world",
        ).decode("utf-8")

        def _hrefs(text):
            return sorted(
                part.split('"')[0] for part in text.split('href="')[1:]
            )

        assert _hrefs(html) == _hrefs(published_html)


class TestTheComparisonCanFail:
    """No vacuous pass: mutate one input and the bytes must stop matching."""

    def test_a_changed_body_diverges(self, published):
        edited = _HELLO[1].replace(
            "This is the post content.", "This is different content.",
        )
        html = render_preview(published["entry"], "hello.md", edited)
        assert html.encode("utf-8") != _published_bytes(
            published["project"], "hello-world",
        )

    def test_a_changed_title_diverges(self, published):
        edited = _HELLO[1].replace("title: Hello World", "title: Hello Moon")
        html = render_preview(published["entry"], "hello.md", edited)
        assert html.encode("utf-8") != _published_bytes(
            published["project"], "hello-world",
        )

    def test_one_added_character_diverges(self, published):
        edited = _HELLO[1].replace("Second.\n", "Second..\n")
        html = render_preview(published["entry"], "hello.md", edited)
        assert html.encode("utf-8") != _published_bytes(
            published["project"], "hello-world",
        )

    def test_comparing_against_another_post_diverges(self, published):
        html = render_preview(published["entry"], "hello.md", _HELLO[1])
        assert html.encode("utf-8") != _published_bytes(
            published["project"], "second-post",
        )


class TestDrafts:
    def test_a_draft_preview_matches_a_drafts_build(self, tmp_path):
        """A draft has no publish; the drafts build is the same renderer."""
        project = _make_project(os.path.join(str(tmp_path), "drafty"), [_DRAFT])
        build(project, target="posts", include_drafts=True)
        entry = _entry(tmp_path, project, name="drafty")

        html = render_preview(entry, "later.md", _DRAFT[1])
        assert html.encode("utf-8") == _published_bytes(project, "later")
