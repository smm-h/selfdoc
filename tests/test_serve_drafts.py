"""Tests for serve --drafts: rebuild behavior and draft inclusion."""

from __future__ import annotations

import json
import os
from unittest.mock import MagicMock, patch

import pytest

# Import build modules before any mocking to prevent mock leakage.
# _cmd_serve does late imports of these modules; if they are first imported
# while selfdoc.config.load_config is mocked, their module-level
# `from selfdoc.config import load_config` binding captures the mock
# and is never restored. Pre-importing ensures the real bindings are set.
import selfdoc.build  # noqa: F401
import selfdoc.unified  # noqa: F401

from conftest import default_config


# -- Helpers ---------------------------------------------------------------


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


_POST_HELLO = (
    "hello.md",
    "---\ntitle: Hello World\ndate: 2024-01-15\nslug: hello-world\n"
    "tags: [release]\ndraft: false\n---\nThis is the post content.\n",
)

_POST_DRAFT = (
    "draft.md",
    "---\ntitle: Draft Post\ndate: 2024-01-16\nslug: draft-post\n"
    "tags: []\ndraft: true\n---\nDraft content here.\n",
)


# -- Unit tests: _cmd_serve rebuild behavior --------------------------------


class TestServeDraftsRebuild:
    """Test that --drafts triggers a rebuild with include_drafts=True."""

    def test_serve_drafts_calls_build(self, tmp_path):
        """When --drafts is True (non-unified config): build() is called
        with include_drafts=True."""
        project = _setup_project_with_posts(tmp_path)
        output_dir = os.path.join(project, "docs", "_build")
        os.makedirs(output_dir, exist_ok=True)

        config = {
            "output": "docs/_build/",
            "source": [{"path": "src/", "language": "python"}],
            "base_url": "https://example.com",
        }

        with (
            patch("selfdoc.config.load_config", return_value=config),
            patch("selfdoc.build.build", return_value={}) as mock_build,
            patch("http.server.HTTPServer") as mock_server,
        ):
            mock_instance = MagicMock()
            mock_server.return_value = mock_instance
            # Make serve_forever raise KeyboardInterrupt to exit
            mock_instance.serve_forever.side_effect = KeyboardInterrupt

            from selfdoc.cli import _cmd_serve

            _cmd_serve(port=8000, drafts=True)

            mock_build.assert_called_once_with(".", include_drafts=True)

    def test_serve_drafts_calls_build_unified(self, tmp_path):
        """When --drafts is True (unified config): build_unified() is called
        with include_drafts=True."""
        project = _setup_project_with_posts(tmp_path)
        output_dir = os.path.join(project, "docs", "_build")
        os.makedirs(output_dir, exist_ok=True)

        config = {
            "output": "docs/_build/",
            "source": [{"path": "src/", "language": "python"}],
            "base_url": "https://example.com",
            "unified": {"projects": [{"path": "../core"}]},
        }

        with (
            patch("selfdoc.config.load_config", return_value=config),
            patch(
                "selfdoc.unified.build_unified", return_value={},
            ) as mock_build_unified,
            patch("http.server.HTTPServer") as mock_server,
        ):
            mock_instance = MagicMock()
            mock_server.return_value = mock_instance
            mock_instance.serve_forever.side_effect = KeyboardInterrupt

            from selfdoc.cli import _cmd_serve

            _cmd_serve(port=8000, drafts=True)

            mock_build_unified.assert_called_once_with(
                ".", config=config, include_drafts=True,
            )

    def test_serve_no_drafts_skips_build(self, tmp_path):
        """When --drafts is False: build is NOT called at all."""
        project = _setup_project_with_posts(tmp_path)
        output_dir = os.path.join(project, "docs", "_build")
        os.makedirs(output_dir, exist_ok=True)

        config = {
            "output": "docs/_build/",
            "source": [{"path": "src/", "language": "python"}],
            "base_url": "https://example.com",
        }

        with (
            patch("selfdoc.config.load_config", return_value=config),
            patch("selfdoc.build.build") as mock_build,
            patch(
                "selfdoc.unified.build_unified",
            ) as mock_build_unified,
            patch("http.server.HTTPServer") as mock_server,
        ):
            mock_instance = MagicMock()
            mock_server.return_value = mock_instance
            mock_instance.serve_forever.side_effect = KeyboardInterrupt

            from selfdoc.cli import _cmd_serve

            _cmd_serve(port=8000, drafts=False)

            mock_build.assert_not_called()
            mock_build_unified.assert_not_called()


# -- Integration test: drafts appear in output ------------------------------


class TestServeDraftsOutput:
    """Integration test: drafts appear in output when --drafts is used."""

    def test_build_with_drafts_includes_draft_post(self, tmp_path):
        """A project with a draft post, calling build() with
        include_drafts=True, actually makes the draft appear in output."""
        project = _setup_project_with_posts(
            tmp_path, posts=[_POST_HELLO, _POST_DRAFT],
        )

        from selfdoc.build import build

        written = build(str(project), include_drafts=True)

        output_dir = os.path.join(project, "docs", "_build")
        draft_html = os.path.join(
            output_dir, "en", "posts", "draft-post", "index.html",
        )
        assert draft_html in written
        assert os.path.isfile(draft_html)

        # Verify draft content is in the HTML
        with open(draft_html) as f:
            content = f.read()
        assert "Draft Post" in content

    def test_build_without_drafts_excludes_draft_post(self, tmp_path):
        """Baseline: build() without include_drafts does not include
        the draft post."""
        project = _setup_project_with_posts(
            tmp_path, posts=[_POST_HELLO, _POST_DRAFT],
        )

        from selfdoc.build import build

        written = build(str(project), include_drafts=False)

        output_dir = os.path.join(project, "docs", "_build")
        draft_html = os.path.join(
            output_dir, "en", "posts", "draft-post", "index.html",
        )
        assert draft_html not in written
        assert not os.path.isfile(draft_html)

        # Non-draft should still be present
        hello_html = os.path.join(
            output_dir, "en", "posts", "hello-world", "index.html",
        )
        assert hello_html in written
