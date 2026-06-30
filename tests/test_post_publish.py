"""Tests for selfdoc post publish command."""

import json
import os
import subprocess

import pytest

from selfdoc.cli import _cmd_post_publish


def _setup_project(tmp_path, config_overrides=None):
    """Create a minimal selfdoc project with posts support."""
    config = {
        "source": [{"path": "src/", "language": "python"}],
        "base_url": "https://example.com",
        "version": "1.0.0",
        "versions": [{"version": "1.0.0", "indexed": True}],
        "locales": [{"code": "en", "label": "English", "default": True}],
        "assembly": {"repo": "owner/docs-assembly"},
        "topology": {"slug": "myproject", "assembly": "owner/docs-assembly"},
    }
    if config_overrides:
        config.update(config_overrides)
    (tmp_path / "selfdoc.json").write_text(json.dumps(config))
    (tmp_path / "src").mkdir(exist_ok=True)
    (tmp_path / "src" / "__init__.py").write_text("")
    return config


def _create_post(tmp_path, filename="2026-06-01-hello.md", draft=False):
    """Create a post file in the default posts directory."""
    posts_dir = tmp_path / ".selfdoc" / "posts"
    posts_dir.mkdir(parents=True, exist_ok=True)
    draft_str = "true" if draft else "false"
    content = (
        "---\n"
        "title: Hello World\n"
        "date: 2026-06-01\n"
        "slug: hello\n"
        f"draft: {draft_str}\n"
        "project: myproject\n"
        "tags: []\n"
        "---\n"
        "\n"
        "Hello world content.\n"
    )
    (posts_dir / filename).write_text(content)
    return posts_dir / filename


# -- Validation: uncommitted posts -------------------------------------------


def test_uncommitted_posts_errors(tmp_path, monkeypatch, capsys):
    """Uncommitted changes in .selfdoc/posts/ should error."""
    _setup_project(tmp_path)
    _create_post(tmp_path)
    monkeypatch.chdir(tmp_path)

    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        result = type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()
        cmd_str = " ".join(str(c) for c in cmd)
        if "status" in cmd_str and "porcelain" in cmd_str:
            # Simulate uncommitted changes
            result.stdout = " M .selfdoc/posts/2026-06-01-hello.md\n"
        return result

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(SystemExit):
        _cmd_post_publish()

    captured = capsys.readouterr()
    assert "Uncommitted changes" in captured.err


# -- Validation: unpushed commits -------------------------------------------


def test_unpushed_commits_errors(tmp_path, monkeypatch, capsys):
    """Local commits not pushed to remote should error."""
    _setup_project(tmp_path)
    _create_post(tmp_path)
    monkeypatch.chdir(tmp_path)

    def fake_run(cmd, **kwargs):
        result = type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()
        cmd_str = " ".join(str(c) for c in cmd)
        if "status" in cmd_str and "porcelain" in cmd_str:
            result.stdout = ""  # clean
        elif "rev-parse" in cmd_str and "HEAD" in cmd_str and "@{u}" not in cmd_str:
            result.stdout = "abc1234\n"
        elif "rev-parse" in cmd_str and "@{u}" in cmd_str:
            result.stdout = "def5678\n"  # different from HEAD
        return result

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(SystemExit):
        _cmd_post_publish()

    captured = capsys.readouterr()
    assert "not pushed to remote" in captured.err


# -- Validation: upstream not set errors ------------------------------------


def test_upstream_not_set_errors(tmp_path, monkeypatch, capsys):
    """When upstream tracking is not set, rev-parse @{u} fails."""
    _setup_project(tmp_path)
    _create_post(tmp_path)
    monkeypatch.chdir(tmp_path)

    def fake_run(cmd, **kwargs):
        result = type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()
        cmd_str = " ".join(str(c) for c in cmd)
        if "status" in cmd_str and "porcelain" in cmd_str:
            result.stdout = ""
        elif "rev-parse" in cmd_str and "@{u}" in cmd_str:
            result.returncode = 1  # no upstream
            result.stderr = "fatal: no upstream configured"
        elif "rev-parse" in cmd_str and "HEAD" in cmd_str:
            result.stdout = "abc1234\n"
        return result

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(SystemExit):
        _cmd_post_publish()

    captured = capsys.readouterr()
    assert "not pushed to remote" in captured.err


# -- Validation: committed and pushed passes --------------------------------


def test_committed_and_pushed_dispatches(tmp_path, monkeypatch, capsys):
    """When posts are committed and pushed, dispatch should succeed."""
    _setup_project(tmp_path)
    _create_post(tmp_path)
    monkeypatch.chdir(tmp_path)

    dispatch_calls = []
    sha = "abc1234def5678"

    def fake_run(cmd, **kwargs):
        result = type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()
        cmd_str = " ".join(str(c) for c in cmd)
        if "status" in cmd_str and "porcelain" in cmd_str:
            result.stdout = ""  # clean
        elif "rev-parse" in cmd_str and "@{u}" in cmd_str:
            result.stdout = sha + "\n"
        elif "rev-parse" in cmd_str and "HEAD" in cmd_str:
            result.stdout = sha + "\n"
        elif "repo" in cmd_str and "view" in cmd_str:
            result.stdout = "owner/myproject\n"
        elif "dispatches" in cmd_str or "api" in cmd_str:
            dispatch_calls.append(kwargs.get("input", ""))
        return result

    monkeypatch.setattr(subprocess, "run", fake_run)

    _cmd_post_publish()

    captured = capsys.readouterr()
    assert "Published 1 post(s)" in captured.out
    assert "Assembly will build and deploy" in captured.out
    assert len(dispatch_calls) == 1


# -- No non-draft posts exits 0 with info message --------------------------


def test_no_non_draft_posts_info_message(tmp_path, monkeypatch, capsys):
    """When all posts are drafts, print info message and exit 0."""
    _setup_project(tmp_path)
    _create_post(tmp_path, draft=True)
    monkeypatch.chdir(tmp_path)

    _cmd_post_publish()

    captured = capsys.readouterr()
    assert "No non-draft posts to publish." in captured.out


def test_no_posts_at_all_info_message(tmp_path, monkeypatch, capsys):
    """When there are no posts at all, print info message and exit 0."""
    _setup_project(tmp_path)
    monkeypatch.chdir(tmp_path)

    _cmd_post_publish()

    captured = capsys.readouterr()
    assert "No non-draft posts to publish." in captured.out


# -- Dispatch payload has scope="posts" and ref is commit SHA ---------------


def test_dispatch_payload_has_scope_posts(tmp_path, monkeypatch):
    """The dispatch payload must include scope='posts' in client_payload."""
    _setup_project(tmp_path)
    _create_post(tmp_path)
    monkeypatch.chdir(tmp_path)

    dispatched_payloads = []
    sha = "deadbeef12345678"

    def fake_run(cmd, **kwargs):
        result = type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()
        cmd_str = " ".join(str(c) for c in cmd)
        if "status" in cmd_str and "porcelain" in cmd_str:
            result.stdout = ""
        elif "rev-parse" in cmd_str and "@{u}" in cmd_str:
            result.stdout = sha + "\n"
        elif "rev-parse" in cmd_str and "HEAD" in cmd_str:
            result.stdout = sha + "\n"
        elif "repo" in cmd_str and "view" in cmd_str:
            result.stdout = "owner/myproject\n"
        elif "--method" in cmd_str and "POST" in cmd_str:
            dispatched_payloads.append(kwargs.get("input", ""))
        return result

    monkeypatch.setattr(subprocess, "run", fake_run)

    _cmd_post_publish()

    assert len(dispatched_payloads) == 1
    payload = json.loads(dispatched_payloads[0])
    cp = payload["client_payload"]
    assert cp["scope"] == "posts"
    assert cp["ref"] == sha


def test_dispatch_ref_is_commit_sha_not_tag(tmp_path, monkeypatch):
    """The ref in the dispatch should be the commit SHA, not a tag."""
    _setup_project(tmp_path)
    _create_post(tmp_path)
    monkeypatch.chdir(tmp_path)

    dispatched_payloads = []
    sha = "1a2b3c4d5e6f7890"

    def fake_run(cmd, **kwargs):
        result = type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()
        cmd_str = " ".join(str(c) for c in cmd)
        if "status" in cmd_str and "porcelain" in cmd_str:
            result.stdout = ""
        elif "rev-parse" in cmd_str and "@{u}" in cmd_str:
            result.stdout = sha + "\n"
        elif "rev-parse" in cmd_str and "HEAD" in cmd_str:
            result.stdout = sha + "\n"
        elif "repo" in cmd_str and "view" in cmd_str:
            result.stdout = "owner/myproject\n"
        elif "--method" in cmd_str and "POST" in cmd_str:
            dispatched_payloads.append(kwargs.get("input", ""))
        return result

    monkeypatch.setattr(subprocess, "run", fake_run)

    _cmd_post_publish()

    payload = json.loads(dispatched_payloads[0])
    assert payload["client_payload"]["ref"] == sha


# -- Assembly repo from config ----------------------------------------------


def test_assembly_repo_from_assembly_config(tmp_path, monkeypatch, capsys):
    """assembly.repo takes precedence for the assembly repo."""
    _setup_project(tmp_path, {
        "assembly": {"repo": "org/my-assembly"},
        "topology": {"slug": "myproject", "assembly": "org/other-assembly"},
    })
    _create_post(tmp_path)
    monkeypatch.chdir(tmp_path)

    dispatched_endpoints = []
    sha = "aabbccdd"

    def fake_run(cmd, **kwargs):
        result = type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()
        cmd_str = " ".join(str(c) for c in cmd)
        if "status" in cmd_str and "porcelain" in cmd_str:
            result.stdout = ""
        elif "rev-parse" in cmd_str and "@{u}" in cmd_str:
            result.stdout = sha + "\n"
        elif "rev-parse" in cmd_str and "HEAD" in cmd_str:
            result.stdout = sha + "\n"
        elif "repo" in cmd_str and "view" in cmd_str:
            result.stdout = "org/myproject\n"
        elif "--method" in cmd_str and "POST" in cmd_str:
            dispatched_endpoints.append(cmd)
        return result

    monkeypatch.setattr(subprocess, "run", fake_run)

    _cmd_post_publish()

    # The endpoint should use assembly.repo, not topology.assembly
    endpoint_cmd = " ".join(str(c) for c in dispatched_endpoints[0])
    assert "org/my-assembly" in endpoint_cmd


def test_assembly_repo_falls_back_to_topology(tmp_path, monkeypatch, capsys):
    """When assembly.repo is not set, topology.assembly is used."""
    _setup_project(tmp_path, {
        "assembly": {},
        "topology": {"slug": "myproject", "assembly": "org/topo-assembly"},
    })
    _create_post(tmp_path)
    monkeypatch.chdir(tmp_path)

    dispatched_endpoints = []
    sha = "aabbccdd"

    def fake_run(cmd, **kwargs):
        result = type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()
        cmd_str = " ".join(str(c) for c in cmd)
        if "status" in cmd_str and "porcelain" in cmd_str:
            result.stdout = ""
        elif "rev-parse" in cmd_str and "@{u}" in cmd_str:
            result.stdout = sha + "\n"
        elif "rev-parse" in cmd_str and "HEAD" in cmd_str:
            result.stdout = sha + "\n"
        elif "repo" in cmd_str and "view" in cmd_str:
            result.stdout = "org/myproject\n"
        elif "--method" in cmd_str and "POST" in cmd_str:
            dispatched_endpoints.append(cmd)
        return result

    monkeypatch.setattr(subprocess, "run", fake_run)

    _cmd_post_publish()

    endpoint_cmd = " ".join(str(c) for c in dispatched_endpoints[0])
    assert "org/topo-assembly" in endpoint_cmd


def test_no_assembly_repo_errors(tmp_path, monkeypatch, capsys):
    """When neither assembly.repo nor topology.assembly is set, error."""
    _setup_project(tmp_path, {
        "assembly": {},
        "topology": {"slug": "myproject"},
    })
    monkeypatch.chdir(tmp_path)

    with pytest.raises(SystemExit):
        _cmd_post_publish()

    captured = capsys.readouterr()
    assert "assembly.repo" in captured.err


def test_no_topology_slug_errors(tmp_path, monkeypatch, capsys):
    """When topology.slug is not configured, error."""
    _setup_project(tmp_path, {
        "assembly": {"repo": "owner/assembly"},
        "topology": {},
    })
    monkeypatch.chdir(tmp_path)

    with pytest.raises(SystemExit):
        _cmd_post_publish()

    captured = capsys.readouterr()
    assert "topology.slug" in captured.err
