"""Tests for selfdoc post generate --from-release."""

from __future__ import annotations

import datetime
import json
import os

import pytest

from selfdoc.cli import _cmd_post_generate


def _setup_project(tmp_path, config_overrides=None):
    """Create a minimal selfdoc project directory."""
    config = {
        "source": [{"path": "src/", "language": "python"}],
        "base_url": "https://example.com",
        "version": "1.0.0",
        "versions": [{"version": "1.0.0", "indexed": True}],
        "locales": [{"code": "en", "label": "English", "default": True}],
    }
    if config_overrides:
        config.update(config_overrides)
    (tmp_path / "selfdoc.json").write_text(json.dumps(config))
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "__init__.py").write_text("")
    return tmp_path


def _setup_manifest(tmp_path, version="1.0.0", posts=None):
    """Create a manifest.json with optional existing posts."""
    selfdoc_dir = tmp_path / ".selfdoc"
    selfdoc_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema_version": 1,
        "name": "test",
        "slug": "test",
        "version": version,
        "description": "",
        "language": "python",
        "base_url": "https://example.com",
        "pages": [],
        "posts": posts or [],
        "last_gen": "",
    }
    (selfdoc_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")


def _read_post(tmp_path, filename):
    """Read a generated post file and return its content."""
    filepath = tmp_path / ".selfdoc" / "posts" / filename
    return filepath.read_text(encoding="utf-8")


def _parse_post(content):
    """Parse a post into frontmatter dict and body string."""
    from selfdoc.utils import parse_frontmatter

    return parse_frontmatter(content)


# ------------------------------------------------------------------
# Happy paths
# ------------------------------------------------------------------


def test_all_flags_provided(tmp_path, monkeypatch):
    """All flags set produces a post with complete frontmatter and body."""
    _setup_project(tmp_path)
    _setup_manifest(tmp_path, version="1.0.0")
    monkeypatch.chdir(tmp_path)

    changelog_path = tmp_path / "changelog.md"
    changelog_path.write_text("- Fixed a bug\n- Added a feature\n")

    body_path = tmp_path / "body.md"
    body_path.write_text("This is a great release!\n")

    _cmd_post_generate(
        from_release=True,
        version="2.0.0",
        prev_version="1.0.0",
        bump_type="major",
        description="Major release",
        context="Big changes",
        changelog_file=str(changelog_path),
        body_file=str(body_path),
        project_name="MyProject",
        release_url="https://github.com/org/repo/releases/tag/v2.0.0",
        registry_url=["https://pypi.org/project/myproject/2.0.0/", "https://npmjs.com/package/myproject"],
        dry_run=False,
    )

    today = datetime.date.today().isoformat()
    filename = f"{today}-release-v2.0.0.md"
    filepath = tmp_path / ".selfdoc" / "posts" / filename
    assert filepath.is_file()

    content = filepath.read_text(encoding="utf-8")
    fm, body = _parse_post(content)

    assert fm["title"] == "MyProject v2.0.0"
    assert fm["date"] == today
    assert fm["slug"] == "release-v2.0.0"
    assert fm["draft"] is False
    assert fm["project"] == "myproject"
    assert fm["version"] == "2.0.0"
    assert fm["prev_version"] == "1.0.0"
    assert fm["bump_type"] == "major"
    assert fm["release_url"] == "https://github.com/org/repo/releases/tag/v2.0.0"
    assert fm["registry_urls"] == [
        "https://pypi.org/project/myproject/2.0.0/",
        "https://npmjs.com/package/myproject",
    ]
    assert fm["tags"] == ["release", "v2.0.0"]

    assert "This is a great release!" in body
    assert "## Changelog" in body
    assert "- Fixed a bug" in body
    assert "- Added a feature" in body


def test_minimal_version_only(tmp_path, monkeypatch):
    """Only from_release and version produces a valid post with defaults."""
    _setup_project(tmp_path)
    monkeypatch.chdir(tmp_path)

    _cmd_post_generate(from_release=True, version="1.2.3")

    today = datetime.date.today().isoformat()
    filename = f"{today}-release-v1.2.3.md"
    filepath = tmp_path / ".selfdoc" / "posts" / filename
    assert filepath.is_file()

    content = filepath.read_text(encoding="utf-8")
    fm, body = _parse_post(content)

    assert fm["title"] == "Release v1.2.3"
    assert fm["tags"] == ["release", "v1.2.3"]
    assert "prev_version" not in fm
    assert "bump_type" not in fm
    assert "release_url" not in fm
    assert "registry_urls" not in fm
    assert body.strip() == "Version 1.2.3 has been released."


def test_body_file_no_changelog(tmp_path, monkeypatch):
    """Body file content is used alone when no changelog is provided."""
    _setup_project(tmp_path)
    monkeypatch.chdir(tmp_path)

    body_path = tmp_path / "body.md"
    body_path.write_text("Custom release notes here.\n")

    _cmd_post_generate(
        from_release=True,
        version="0.5.0",
        body_file=str(body_path),
    )

    today = datetime.date.today().isoformat()
    content = _read_post(tmp_path, f"{today}-release-v0.5.0.md")
    _fm, body = _parse_post(content)

    assert "Custom release notes here." in body
    assert "## Changelog" not in body


def test_changelog_no_body(tmp_path, monkeypatch):
    """Changelog file content appears under a Changelog heading with no user body."""
    _setup_project(tmp_path)
    monkeypatch.chdir(tmp_path)

    changelog_path = tmp_path / "changes.md"
    changelog_path.write_text("- Bug fix #42\n- Performance improvement\n")

    _cmd_post_generate(
        from_release=True,
        version="3.1.0",
        changelog_file=str(changelog_path),
    )

    today = datetime.date.today().isoformat()
    content = _read_post(tmp_path, f"{today}-release-v3.1.0.md")
    _fm, body = _parse_post(content)

    assert body.startswith("## Changelog")
    assert "- Bug fix #42" in body
    assert "- Performance improvement" in body


def test_dry_run(tmp_path, monkeypatch, capsys):
    """Dry run prints the post content without writing files or updating manifest."""
    _setup_project(tmp_path)
    _setup_manifest(tmp_path, version="1.0.0")
    monkeypatch.chdir(tmp_path)

    _cmd_post_generate(
        from_release=True,
        version="1.1.0",
        project_name="DryTest",
        dry_run=True,
    )

    today = datetime.date.today().isoformat()
    filename = f"{today}-release-v1.1.0.md"

    # No file written
    filepath = tmp_path / ".selfdoc" / "posts" / filename
    assert not filepath.exists()

    # Manifest unchanged
    manifest_data = json.loads((tmp_path / ".selfdoc" / "manifest.json").read_text())
    assert manifest_data["version"] == "1.0.0"
    assert manifest_data["posts"] == []

    # Content printed to stdout
    captured = capsys.readouterr()
    assert "DryTest v1.1.0" in captured.out
    assert "release-v1.1.0" in captured.out
    assert "draft: false" in captured.out


def test_manifest_update(tmp_path, monkeypatch):
    """Existing manifest gets the new post appended and version updated."""
    _setup_project(tmp_path)
    existing_post = {
        "path": "2025-01-01-old-post.md",
        "title": "Old Post",
        "date": "2025-01-01",
        "slug": "old-post",
        "tags": ["misc"],
    }
    _setup_manifest(tmp_path, version="1.0.0", posts=[existing_post])
    monkeypatch.chdir(tmp_path)

    _cmd_post_generate(from_release=True, version="1.1.0")

    today = datetime.date.today().isoformat()
    manifest_data = json.loads((tmp_path / ".selfdoc" / "manifest.json").read_text())

    # Version updated
    assert manifest_data["version"] == "1.1.0"

    # Posts list has old + new
    assert len(manifest_data["posts"]) == 2
    assert manifest_data["posts"][0] == existing_post

    new_entry = manifest_data["posts"][1]
    assert new_entry["path"] == f"{today}-release-v1.1.0.md"
    assert new_entry["title"] == "Release v1.1.0"
    assert new_entry["date"] == today
    assert new_entry["slug"] == "release-v1.1.0"
    assert new_entry["tags"] == ["release", "v1.1.0"]


def test_slug_generation(tmp_path, monkeypatch):
    """Slug is always release-v{version} for various version strings."""
    _setup_project(tmp_path)
    monkeypatch.chdir(tmp_path)

    today = datetime.date.today().isoformat()

    for version, expected_slug in [
        ("1.2.3", "release-v1.2.3"),
        ("0.10.0", "release-v0.10.0"),
    ]:
        _cmd_post_generate(from_release=True, version=version)
        filename = f"{today}-{expected_slug}.md"
        filepath = tmp_path / ".selfdoc" / "posts" / filename
        assert filepath.is_file(), f"Expected {filename} for version {version}"

        content = filepath.read_text(encoding="utf-8")
        assert f"slug: {expected_slug}\n" in content


# ------------------------------------------------------------------
# Error paths
# ------------------------------------------------------------------


def test_no_from_release_flag(tmp_path, monkeypatch):
    """SystemExit when from_release is False."""
    _setup_project(tmp_path)
    monkeypatch.chdir(tmp_path)

    with pytest.raises(SystemExit):
        _cmd_post_generate(from_release=False, version="1.0.0")


def test_no_version(tmp_path, monkeypatch):
    """SystemExit when version is empty."""
    _setup_project(tmp_path)
    monkeypatch.chdir(tmp_path)

    with pytest.raises(SystemExit):
        _cmd_post_generate(from_release=True, version="")


def test_no_config(tmp_path, monkeypatch):
    """SystemExit when no selfdoc.json exists."""
    monkeypatch.chdir(tmp_path)

    with pytest.raises(SystemExit):
        _cmd_post_generate(from_release=True, version="1.0.0")


# ------------------------------------------------------------------
# Project resolution
# ------------------------------------------------------------------


def test_project_from_topology(tmp_path, monkeypatch):
    """Project slug comes from topology.slug when present in config."""
    _setup_project(tmp_path, config_overrides={
        "topology": {"slug": "my-cool-project"},
    })
    monkeypatch.chdir(tmp_path)

    _cmd_post_generate(from_release=True, version="1.0.0")

    today = datetime.date.today().isoformat()
    content = _read_post(tmp_path, f"{today}-release-v1.0.0.md")
    assert "project: my-cool-project\n" in content


def test_project_from_flag(tmp_path, monkeypatch):
    """project_name flag is used for title and kebab-cased for project slug."""
    _setup_project(tmp_path)
    monkeypatch.chdir(tmp_path)

    _cmd_post_generate(
        from_release=True,
        version="2.0.0",
        project_name="My Awesome Project",
    )

    today = datetime.date.today().isoformat()
    content = _read_post(tmp_path, f"{today}-release-v2.0.0.md")
    fm, _body = _parse_post(content)

    assert fm["title"] == "My Awesome Project v2.0.0"
    assert fm["project"] == "my-awesome-project"
