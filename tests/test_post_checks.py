"""Tests for post lint rules (POST001-POST005) in selfblog.check."""

from __future__ import annotations

import json
import os

import pytest

from selfblog.check import check_posts


def _write_post(posts_dir, filename, frontmatter_lines, body=""):
    path = os.path.join(posts_dir, filename)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    content = "---\n" + "\n".join(frontmatter_lines) + "\n---\n" + body
    with open(path, "w") as f:
        f.write(content)


def _write_manifest(path, posts):
    data = {
        "schema_version": 1,
        "name": "test",
        "slug": "test",
        "version": "1.0.0",
        "description": "",
        "language": "python",
        "base_url": "",
        "pages": [],
        "posts": posts,
        "last_gen": "",
    }
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f)


def test_post_check_no_posts_dir(tmp_path):
    """No posts dir configured -> empty results."""
    config = {}
    result = check_posts(config, str(tmp_path))
    assert result == []


def test_post_check_valid_posts(tmp_path):
    """Valid posts -> empty results."""
    posts_dir = tmp_path / "blog"
    _write_post(
        str(posts_dir),
        "hello.md",
        ["title: Hello World", "date: 2025-01-15"],
        body="Some body text.",
    )
    config = {"posts": {"dir": "blog"}}
    result = check_posts(config, str(tmp_path))
    assert result == []


def test_post_check_missing_date(tmp_path):
    """Post missing date -> POST001."""
    posts_dir = tmp_path / "blog"
    _write_post(str(posts_dir), "p.md", ["title: No Date"])
    config = {"posts": {"dir": "blog"}}
    result = check_posts(config, str(tmp_path))
    assert len(result) == 1
    assert result[0].code == "POST001"
    assert result[0].severity == "error"
    assert "'date' is required" in result[0].message


def test_post_check_missing_title(tmp_path):
    """Post missing title -> POST002."""
    posts_dir = tmp_path / "blog"
    _write_post(str(posts_dir), "p.md", ["date: 2025-01-01"])
    config = {"posts": {"dir": "blog"}}
    result = check_posts(config, str(tmp_path))
    assert len(result) == 1
    assert result[0].code == "POST002"
    assert result[0].severity == "error"
    assert "'title' is required" in result[0].message


def test_post_check_invalid_date(tmp_path):
    """Post with bad date format -> POST003."""
    posts_dir = tmp_path / "blog"
    _write_post(
        str(posts_dir),
        "p.md",
        ["title: Bad Date", "date: Jan 15 2025"],
    )
    config = {"posts": {"dir": "blog"}}
    result = check_posts(config, str(tmp_path))
    assert len(result) == 1
    assert result[0].code == "POST003"
    assert result[0].severity == "error"
    assert "must be YYYY-MM-DD" in result[0].message


def test_post_check_duplicate_slug(tmp_path):
    """Two posts with same slug -> POST004."""
    posts_dir = tmp_path / "blog"
    _write_post(str(posts_dir), "a.md", ["title: Same", "date: 2025-01-01"])
    _write_post(str(posts_dir), "b.md", ["title: Same", "date: 2025-02-01"])
    config = {"posts": {"dir": "blog"}}
    result = check_posts(config, str(tmp_path))
    assert len(result) == 1
    assert result[0].code == "POST004"
    assert result[0].severity == "error"
    assert "Duplicate slug" in result[0].message


def test_post_check_slug_immutability(tmp_path):
    """Slug changed from committed manifest -> POST005."""
    import subprocess
    # Set up git repo with initial commit
    subprocess.run(["git", "init"], cwd=str(tmp_path), capture_output=True,
                   timeout=10, check=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"],
                   cwd=str(tmp_path), capture_output=True, timeout=10, check=True)
    subprocess.run(["git", "config", "user.name", "Test"],
                   cwd=str(tmp_path), capture_output=True, timeout=10, check=True)
    readme = tmp_path / "README.md"
    readme.write_text("# test\n")
    subprocess.run(["git", "add", "README.md"], cwd=str(tmp_path),
                   capture_output=True, timeout=10, check=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=str(tmp_path),
                   capture_output=True, timeout=10, check=True)

    posts_dir = tmp_path / "blog"
    _write_post(
        str(posts_dir),
        "hello.md",
        ["title: Hello", "date: 2025-01-01", "slug: hello-new"],
    )
    # Commit manifest with the OLD slug
    manifest_dir = tmp_path / ".selfdoc"
    _write_manifest(
        str(manifest_dir / "manifest.json"),
        [{"path": "hello.md", "slug": "hello-old"}],
    )
    subprocess.run(["git", "add", ".selfdoc/manifest.json"], cwd=str(tmp_path),
                   capture_output=True, timeout=10, check=True)
    subprocess.run(["git", "commit", "-m", "add manifest"], cwd=str(tmp_path),
                   capture_output=True, timeout=10, check=True)

    config = {"posts": {"dir": "blog"}}
    result = check_posts(config, str(tmp_path))
    assert len(result) == 1
    assert result[0].code == "POST005"
    assert result[0].severity == "error"
    assert "Slug immutability violation" in result[0].message


# -- Post-check hook wiring (selfdoc check <-> selfblog) --------------------


def test_check_docs_runs_post_checks_via_hook(tmp_path):
    """check_docs surfaces POST lints through the registered hook."""
    from selfdoc.check import check_docs

    _write_post(
        str(tmp_path / "blog"),
        "bad.md",
        ["title: No Date"],
    )
    config = {
        "source": [{"path": "src/", "language": "python"}],
        "base_url": "https://example.com",
        "version": "1.0.0",
        "versions": [{"version": "1.0.0"}],
        "locales": [{"code": "en", "label": "English", "default": True}],
        "docs": "docs/",
        "output": "docs/_build/",
        "posts": {"dir": "blog"},
    }
    with open(tmp_path / "selfdoc.json", "w") as f:
        json.dump(config, f)
    os.makedirs(tmp_path / "src", exist_ok=True)
    (tmp_path / "src" / "__init__.py").write_text('"""Pkg."""\n')
    os.makedirs(tmp_path / "docs", exist_ok=True)
    (tmp_path / "docs" / "index.md").write_text("# Home\n\nHi.\n")

    result = check_docs(str(tmp_path), dry_run=True)
    assert any(lint.code == "POST001" for lint in result.lints)


def test_check_docs_posts_present_without_hook_hard_errors(
    tmp_path, monkeypatch,
):
    """Posts present but no registered post-check hook -> hard error
    naming selfblog."""
    import selfdoc_core
    from selfdoc.check import check_docs

    _write_post(
        str(tmp_path / "blog"),
        "ok.md",
        ["title: Fine", "date: 2025-01-15"],
    )
    config = {
        "source": [{"path": "src/", "language": "python"}],
        "base_url": "https://example.com",
        "version": "1.0.0",
        "versions": [{"version": "1.0.0"}],
        "locales": [{"code": "en", "label": "English", "default": True}],
        "docs": "docs/",
        "output": "docs/_build/",
        "posts": {"dir": "blog"},
    }
    with open(tmp_path / "selfdoc.json", "w") as f:
        json.dump(config, f)
    os.makedirs(tmp_path / "src", exist_ok=True)
    (tmp_path / "src" / "__init__.py").write_text('"""Pkg."""\n')
    os.makedirs(tmp_path / "docs", exist_ok=True)
    (tmp_path / "docs" / "index.md").write_text("# Home\n\nHi.\n")

    monkeypatch.setattr(selfdoc_core, "_post_check_hook", None)
    with pytest.raises(RuntimeError, match="selfblog"):
        check_docs(str(tmp_path), dry_run=True)


def test_selfblog_check_command_reports_post_errors(
    tmp_path, monkeypatch, capsys,
):
    """'selfblog check' fails on invalid posts and prints the lint."""
    from selfblog.cli import _cmd_check

    _write_post(
        str(tmp_path / "blog"),
        "bad.md",
        ["title: No Date"],
    )
    config = {
        "source": [{"path": "src/", "language": "python"}],
        "base_url": "https://example.com",
        "version": "1.0.0",
        "versions": [{"version": "1.0.0"}],
        "locales": [{"code": "en", "label": "English", "default": True}],
        "posts": {"dir": "blog"},
    }
    with open(tmp_path / "selfdoc.json", "w") as f:
        json.dump(config, f)
    monkeypatch.chdir(tmp_path)

    with pytest.raises(SystemExit):
        _cmd_check(None)
    captured = capsys.readouterr()
    assert "POST001" in captured.out


def test_selfblog_check_command_passes_on_valid_posts(
    tmp_path, monkeypatch, capsys,
):
    """'selfblog check' succeeds on valid posts."""
    from selfblog.cli import _cmd_check

    _write_post(
        str(tmp_path / "blog"),
        "ok.md",
        ["title: Fine", "date: 2025-01-15"],
    )
    config = {
        "source": [{"path": "src/", "language": "python"}],
        "base_url": "https://example.com",
        "version": "1.0.0",
        "versions": [{"version": "1.0.0"}],
        "locales": [{"code": "en", "label": "English", "default": True}],
        "posts": {"dir": "blog"},
    }
    with open(tmp_path / "selfdoc.json", "w") as f:
        json.dump(config, f)
    monkeypatch.chdir(tmp_path)

    assert _cmd_check(None) == 0
    captured = capsys.readouterr()
    assert "Post checks passed." in captured.out
