"""Tests for selfdoc post publish command."""

import json
import os
import subprocess

import pytest

from selfblog.cli import _cmd_post_publish


def _setup_project(tmp_path, config_overrides=None):
    """Create a minimal selfdoc project with posts support."""
    config = {
        "source": [{"path": "src/", "language": "python"}],
        "base_url": "https://example.com",
        "version": "1.0.0",
        "versions": [{"version": "1.0.0", "indexed": True}],
        "locales": [{"code": "en", "label": "English", "default": True}],
        "output": "docs/_build/",
        "docs": "docs/",
        "assembly": {"repo": "owner/docs-assembly"},
        "topology": {"slug": "myproject", "assembly": "owner/docs-assembly"},
    }
    if config_overrides:
        config.update(config_overrides)
    (tmp_path / "selfdoc.json").write_text(json.dumps(config))
    (tmp_path / "src").mkdir(exist_ok=True)
    (tmp_path / "src" / "__init__.py").write_text("")
    (tmp_path / "docs").mkdir(exist_ok=True)
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


# -- Missing config errors --------------------------------------------------


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


# -- Post publish does NOT check git status or push status ------------------


def test_no_git_status_check(tmp_path, monkeypatch, capsys):
    """Post publish does not run git status --porcelain."""
    _setup_project(tmp_path)
    _create_post(tmp_path)
    monkeypatch.chdir(tmp_path)

    subprocess_calls = []

    def tracking_run(cmd, **kwargs):
        subprocess_calls.append(cmd)
        return type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()

    # Mock _build_posts_only and push_files_to_repo to avoid real work
    monkeypatch.setattr(
        "selfdoc_core.build._build_posts_only",
        lambda *a, **kw: {},
    )
    monkeypatch.setattr(
        "selfblog.assembly.push_files_to_repo",
        lambda *a, **kw: "fake_sha",
    )
    monkeypatch.setattr(subprocess, "run", tracking_run)

    _cmd_post_publish()

    # Verify no git status or rev-parse calls were made
    for call in subprocess_calls:
        cmd_str = " ".join(str(c) for c in call)
        assert "git status" not in cmd_str, f"Unexpected git status call: {cmd_str}"
        assert "rev-parse" not in cmd_str, f"Unexpected rev-parse call: {cmd_str}"
        assert "repo view" not in cmd_str, f"Unexpected gh repo view call: {cmd_str}"


def test_no_push_status_check(tmp_path, monkeypatch, capsys):
    """Post publish does not check if commits are pushed to remote."""
    _setup_project(tmp_path)
    _create_post(tmp_path)
    monkeypatch.chdir(tmp_path)

    subprocess_calls = []

    def tracking_run(cmd, **kwargs):
        subprocess_calls.append(cmd)
        result = type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()
        return result

    monkeypatch.setattr(
        "selfdoc_core.build._build_posts_only",
        lambda *a, **kw: {},
    )
    monkeypatch.setattr(
        "selfblog.assembly.push_files_to_repo",
        lambda *a, **kw: "fake_sha",
    )
    monkeypatch.setattr(subprocess, "run", tracking_run)

    _cmd_post_publish()

    for call in subprocess_calls:
        cmd_str = " ".join(str(c) for c in call)
        assert "@{u}" not in cmd_str, f"Unexpected upstream check: {cmd_str}"


# -- Post publish calls _build_posts_only locally ----------------------------


def test_calls_build_posts_only(tmp_path, monkeypatch, capsys):
    """Post publish calls _build_posts_only to build posts locally."""
    _setup_project(tmp_path)
    _create_post(tmp_path)
    monkeypatch.chdir(tmp_path)

    build_calls = []

    def mock_build(dir_path, config, output_dir, docs_dir_name, docs_dir, include_drafts):
        build_calls.append({
            "dir_path": dir_path,
            "output_dir": output_dir,
            "docs_dir_name": docs_dir_name,
            "docs_dir": docs_dir,
            "include_drafts": include_drafts,
        })
        return {}

    monkeypatch.setattr("selfdoc_core.build._build_posts_only", mock_build)
    monkeypatch.setattr(
        "selfblog.assembly.push_files_to_repo",
        lambda *a, **kw: "fake_sha",
    )
    monkeypatch.setattr(
        subprocess, "run",
        lambda cmd, **kw: type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})(),
    )

    _cmd_post_publish()

    assert len(build_calls) == 1
    assert build_calls[0]["dir_path"] == "."
    assert build_calls[0]["include_drafts"] is False


# -- Post publish calls push_files_to_repo with correct file mappings ------


def test_pushes_correct_file_mappings(tmp_path, monkeypatch, capsys):
    """Post publish maps built HTML and manifest to assembly paths."""
    _setup_project(tmp_path)
    _create_post(tmp_path)
    monkeypatch.chdir(tmp_path)

    # Create fake build output
    output_dir = tmp_path / "docs" / "_build"
    posts_out = output_dir / "posts" / "hello"
    posts_out.mkdir(parents=True)
    (posts_out / "index.html").write_text("<html>post</html>")

    # Create fake post-manifest
    selfdoc_dir = tmp_path / ".selfdoc"
    selfdoc_dir.mkdir(exist_ok=True)
    manifest_data = {"slug": "myproject", "posts": [{"slug": "hello"}]}
    (selfdoc_dir / "post-manifest.json").write_text(json.dumps(manifest_data))

    def mock_build(dir_path, config, output_dir_arg, docs_dir_name, docs_dir, include_drafts):
        return {str(posts_out / "index.html"): True}

    push_calls = []

    def mock_push(repo, files, message, branch="main"):
        push_calls.append({"repo": repo, "files": files, "message": message})
        return "commit_sha"

    monkeypatch.setattr("selfdoc_core.build._build_posts_only", mock_build)
    monkeypatch.setattr("selfblog.assembly.push_files_to_repo", mock_push)
    monkeypatch.setattr(
        subprocess, "run",
        lambda cmd, **kw: type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})(),
    )

    _cmd_post_publish()

    assert len(push_calls) == 1
    push = push_calls[0]
    assert push["repo"] == "owner/docs-assembly"
    assert push["message"] == "posts: myproject"

    # Check file mappings
    assert "site/myproject/posts/hello/index.html" in push["files"]
    assert push["files"]["site/myproject/posts/hello/index.html"] == "<html>post</html>"
    assert "manifests/myproject-posts.json" in push["files"]
    assert json.loads(push["files"]["manifests/myproject-posts.json"]) == manifest_data


# -- Post publish dispatches scope="shared-only" after pushing ---------------


def test_dispatches_shared_only(tmp_path, monkeypatch, capsys):
    """Post publish dispatches scope='shared-only' to the assembly repo."""
    _setup_project(tmp_path)
    _create_post(tmp_path)
    monkeypatch.chdir(tmp_path)

    monkeypatch.setattr("selfdoc_core.build._build_posts_only", lambda *a, **kw: {})
    monkeypatch.setattr(
        "selfblog.assembly.push_files_to_repo",
        lambda *a, **kw: "fake_sha",
    )

    dispatched = []

    def fake_run(cmd, **kwargs):
        result = type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()
        cmd_str = " ".join(str(c) for c in cmd)
        if "--method" in cmd_str and "POST" in cmd_str:
            dispatched.append({
                "cmd": cmd,
                "input": kwargs.get("input", ""),
            })
        return result

    monkeypatch.setattr(subprocess, "run", fake_run)

    _cmd_post_publish()

    assert len(dispatched) == 1
    payload = json.loads(dispatched[0]["input"])
    assert payload["event_type"] == "project-updated"
    assert payload["client_payload"]["scope"] == "shared-only"

    # Verify endpoint targets the assembly repo
    cmd_str = " ".join(str(c) for c in dispatched[0]["cmd"])
    assert "/repos/owner/docs-assembly/dispatches" in cmd_str


def test_dispatch_failure_errors(tmp_path, monkeypatch, capsys):
    """When the dispatch call fails, print error and exit."""
    _setup_project(tmp_path)
    _create_post(tmp_path)
    monkeypatch.chdir(tmp_path)

    monkeypatch.setattr("selfdoc_core.build._build_posts_only", lambda *a, **kw: {})
    monkeypatch.setattr(
        "selfblog.assembly.push_files_to_repo",
        lambda *a, **kw: "fake_sha",
    )

    def fake_run(cmd, **kwargs):
        result = type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()
        cmd_str = " ".join(str(c) for c in cmd)
        if "--method" in cmd_str and "POST" in cmd_str:
            result.returncode = 1
            result.stderr = "Dispatch failed"
        return result

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(SystemExit):
        _cmd_post_publish()

    captured = capsys.readouterr()
    assert "Failed to dispatch" in captured.err


# -- Success message -------------------------------------------------------


def test_success_message(tmp_path, monkeypatch, capsys):
    """Successful publish prints count and shared regeneration message."""
    _setup_project(tmp_path)
    _create_post(tmp_path)
    monkeypatch.chdir(tmp_path)

    monkeypatch.setattr("selfdoc_core.build._build_posts_only", lambda *a, **kw: {})
    monkeypatch.setattr(
        "selfblog.assembly.push_files_to_repo",
        lambda *a, **kw: "fake_sha",
    )
    monkeypatch.setattr(
        subprocess, "run",
        lambda cmd, **kw: type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})(),
    )

    _cmd_post_publish()

    captured = capsys.readouterr()
    assert "Published 1 post(s) to assembly" in captured.out
    assert "Shared elements will regenerate" in captured.out


# -- Assembly repo resolution -----------------------------------------------


def test_assembly_repo_from_assembly_config(tmp_path, monkeypatch, capsys):
    """assembly.repo takes precedence for the assembly repo."""
    _setup_project(tmp_path, {
        "assembly": {"repo": "org/my-assembly"},
        "topology": {"slug": "myproject", "assembly": "org/other-assembly"},
    })
    _create_post(tmp_path)
    monkeypatch.chdir(tmp_path)

    push_calls = []

    def mock_push(repo, files, message, branch="main"):
        push_calls.append(repo)
        return "sha"

    monkeypatch.setattr("selfdoc_core.build._build_posts_only", lambda *a, **kw: {})
    monkeypatch.setattr("selfblog.assembly.push_files_to_repo", mock_push)
    monkeypatch.setattr(
        subprocess, "run",
        lambda cmd, **kw: type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})(),
    )

    _cmd_post_publish()

    assert push_calls[0] == "org/my-assembly"


def test_assembly_repo_falls_back_to_topology(tmp_path, monkeypatch, capsys):
    """When assembly.repo is not set, topology.assembly is used."""
    _setup_project(tmp_path, {
        "assembly": {},
        "topology": {"slug": "myproject", "assembly": "org/topo-assembly"},
    })
    _create_post(tmp_path)
    monkeypatch.chdir(tmp_path)

    push_calls = []

    def mock_push(repo, files, message, branch="main"):
        push_calls.append(repo)
        return "sha"

    monkeypatch.setattr("selfdoc_core.build._build_posts_only", lambda *a, **kw: {})
    monkeypatch.setattr("selfblog.assembly.push_files_to_repo", mock_push)
    monkeypatch.setattr(
        subprocess, "run",
        lambda cmd, **kw: type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})(),
    )

    _cmd_post_publish()

    assert push_calls[0] == "org/topo-assembly"


# -- Posts repo archiving -----------------------------------------------------


def test_posts_repo_push_when_configured(tmp_path, monkeypatch, capsys):
    """When posts.repo is configured, push_files_to_repo is called for both
    the assembly repo AND the posts repo."""
    _setup_project(tmp_path, {
        "posts": {"repo": "owner/posts-archive"},
    })
    _create_post(tmp_path)
    monkeypatch.chdir(tmp_path)

    push_calls = []

    def mock_push(repo, files, message, branch="main"):
        push_calls.append({"repo": repo, "files": files, "message": message})
        return "sha"

    monkeypatch.setattr("selfdoc_core.build._build_posts_only", lambda *a, **kw: {})
    monkeypatch.setattr("selfblog.assembly.push_files_to_repo", mock_push)
    monkeypatch.setattr(
        "selfdoc_core.directives.resolve_directives",
        lambda content, resolver: f"resolved:{content}",
    )
    monkeypatch.setattr(
        "selfdoc_core.resolver.make_resolver",
        lambda config, base_dir: "fake_resolver",
    )
    monkeypatch.setattr(
        subprocess, "run",
        lambda cmd, **kw: type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})(),
    )

    _cmd_post_publish()

    # Two push calls: one for assembly, one for posts repo
    assert len(push_calls) == 2
    repos_pushed = [c["repo"] for c in push_calls]
    assert "owner/docs-assembly" in repos_pushed
    assert "owner/posts-archive" in repos_pushed


def test_no_posts_repo_only_assembly_push(tmp_path, monkeypatch, capsys):
    """When posts.repo is NOT configured, only the assembly repo push happens."""
    _setup_project(tmp_path)
    _create_post(tmp_path)
    monkeypatch.chdir(tmp_path)

    push_calls = []

    def mock_push(repo, files, message, branch="main"):
        push_calls.append({"repo": repo, "files": files, "message": message})
        return "sha"

    monkeypatch.setattr("selfdoc_core.build._build_posts_only", lambda *a, **kw: {})
    monkeypatch.setattr("selfblog.assembly.push_files_to_repo", mock_push)
    monkeypatch.setattr(
        subprocess, "run",
        lambda cmd, **kw: type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})(),
    )

    _cmd_post_publish()

    # Only one push call: for the assembly repo
    assert len(push_calls) == 1
    assert push_calls[0]["repo"] == "owner/docs-assembly"


def test_posts_repo_pushes_resolved_markdown(tmp_path, monkeypatch, capsys):
    """The resolved markdown (not raw, not HTML) is pushed to the posts repo."""
    _setup_project(tmp_path, {
        "posts": {"repo": "owner/posts-archive"},
    })
    _create_post(tmp_path)
    monkeypatch.chdir(tmp_path)

    push_calls = []

    def mock_push(repo, files, message, branch="main"):
        push_calls.append({"repo": repo, "files": files, "message": message})
        return "sha"

    def mock_resolve(content, resolver):
        return f"RESOLVED[{content}]"

    monkeypatch.setattr("selfdoc_core.build._build_posts_only", lambda *a, **kw: {})
    monkeypatch.setattr("selfblog.assembly.push_files_to_repo", mock_push)
    monkeypatch.setattr(
        "selfdoc_core.directives.resolve_directives", mock_resolve,
    )
    monkeypatch.setattr(
        "selfdoc_core.resolver.make_resolver",
        lambda config, base_dir: "fake_resolver",
    )
    monkeypatch.setattr(
        subprocess, "run",
        lambda cmd, **kw: type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})(),
    )

    _cmd_post_publish()

    # Find the posts repo push
    posts_push = [c for c in push_calls if c["repo"] == "owner/posts-archive"]
    assert len(posts_push) == 1

    # The pushed content should be the resolved markdown, not raw or HTML
    files = posts_push[0]["files"]
    for path, content in files.items():
        assert content.startswith("RESOLVED["), (
            f"Expected resolved markdown, got: {content[:50]}"
        )
        # Verify it's not HTML
        assert "<html" not in content
        assert "</html>" not in content
