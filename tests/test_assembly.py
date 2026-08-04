"""Tests for selfblog.assembly -- assembly infrastructure for multi-project docs."""

import json
from unittest.mock import patch

import pytest

from selfblog.assembly import (
    assembly_init,
    assembly_push,
    assembly_rebuild,
    assembly_status,
    generate_workflow_yaml,
    push_files_to_repo,
)


# -- generate_workflow_yaml --------------------------------------------------


def test_workflow_yaml_is_valid_yaml():
    """generate_workflow_yaml returns a non-empty string with expected YAML markers."""
    yaml_str = generate_workflow_yaml("smmh", "https://docs.smmh.dev", "blog.smmh.dev")
    assert isinstance(yaml_str, str)
    assert len(yaml_str) > 0
    # Basic YAML structure markers
    assert "name:" in yaml_str
    assert "on:" in yaml_str
    assert "jobs:" in yaml_str


def test_workflow_yaml_has_dispatch_trigger():
    yaml_str = generate_workflow_yaml("smmh", "https://docs.smmh.dev", "blog.smmh.dev")
    assert "repository_dispatch" in yaml_str
    assert "project-updated" in yaml_str


def test_workflow_yaml_has_concurrency():
    yaml_str = generate_workflow_yaml("smmh", "https://docs.smmh.dev", "blog.smmh.dev")
    assert "assembly-deploy" in yaml_str
    assert "cancel-in-progress: false" in yaml_str
    assert "queue: max" in yaml_str


def test_workflow_yaml_has_queue_max():
    """queue: max enables FIFO queuing of up to 100 pending workflow runs."""
    yaml_str = generate_workflow_yaml("smmh", "https://docs.smmh.dev", "blog.smmh.dev")
    assert "queue: max" in yaml_str


def test_workflow_yaml_has_deploy_job():
    yaml_str = generate_workflow_yaml("smmh", "https://docs.smmh.dev", "blog.smmh.dev")
    assert "deploy:" in yaml_str
    assert "ubuntu-latest" in yaml_str


def test_workflow_yaml_has_checkout_step():
    yaml_str = generate_workflow_yaml("smmh", "https://docs.smmh.dev", "blog.smmh.dev")
    assert "actions/checkout@v4" in yaml_str


def test_workflow_yaml_first_checkout_has_fetch_depth():
    yaml_str = generate_workflow_yaml("smmh", "https://docs.smmh.dev", "blog.smmh.dev")
    # First checkout uses full clone for push retry support
    assert "fetch-depth: 0" in yaml_str


def test_workflow_yaml_has_second_checkout_for_source():
    """Workflow has a second actions/checkout to clone the source project."""
    yaml_str = generate_workflow_yaml("smmh", "https://docs.smmh.dev", "blog.smmh.dev")
    # There should be two occurrences of actions/checkout@v4
    count = yaml_str.count("actions/checkout@v4")
    assert count == 2, f"Expected 2 checkout steps, found {count}"
    # The second checkout should clone into source/
    assert "path: source/" in yaml_str


def test_workflow_yaml_has_python_setup():
    yaml_str = generate_workflow_yaml("smmh", "https://docs.smmh.dev", "blog.smmh.dev")
    assert "actions/setup-python@v5" in yaml_str
    assert "3.12" in yaml_str


def test_workflow_yaml_has_permissions():
    yaml_str = generate_workflow_yaml("smmh", "https://docs.smmh.dev", "blog.smmh.dev")
    assert "permissions:" in yaml_str
    assert "contents: write" in yaml_str


def test_workflow_yaml_has_selfdoc_install():
    yaml_str = generate_workflow_yaml("smmh", "https://docs.smmh.dev", "blog.smmh.dev")
    assert "pip install selfdoc selfblog" in yaml_str


def test_workflow_yaml_has_payload_extraction():
    yaml_str = generate_workflow_yaml("smmh", "https://docs.smmh.dev", "blog.smmh.dev")
    assert "SLUG=" in yaml_str
    assert "VERSION=" in yaml_str
    assert "REF=" in yaml_str
    assert "SOURCE_REPO=" in yaml_str


def test_workflow_yaml_has_clone_step():
    yaml_str = generate_workflow_yaml("smmh", "https://docs.smmh.dev", "blog.smmh.dev")
    assert "Clone source project" in yaml_str
    assert "repository:" in yaml_str


def test_workflow_yaml_has_build_step():
    yaml_str = generate_workflow_yaml("smmh", "https://docs.smmh.dev", "blog.smmh.dev")
    assert "selfdoc build" in yaml_str


def test_workflow_yaml_has_git_config_and_push():
    """Workflow configures git and commits+pushes the built site."""
    yaml_str = generate_workflow_yaml("smmh", "https://docs.smmh.dev", "blog.smmh.dev")
    assert "git config user.name" in yaml_str
    assert "git config user.email" in yaml_str
    assert "git commit" in yaml_str
    assert "git push" in yaml_str


def test_workflow_yaml_has_generate_shared():
    yaml_str = generate_workflow_yaml("smmh", "https://docs.smmh.dev", "blog.smmh.dev")
    assert "selfblog assembly generate-shared" in yaml_str


def test_workflow_yaml_has_pagefind():
    yaml_str = generate_workflow_yaml("smmh", "https://docs.smmh.dev", "blog.smmh.dev")
    assert "pagefind --site site/" in yaml_str


def test_workflow_yaml_has_projects_json_update():
    yaml_str = generate_workflow_yaml("smmh", "https://docs.smmh.dev", "blog.smmh.dev")
    assert "projects.json" in yaml_str
    # The step writes to projects.json via inline Python
    assert "json.dump" in yaml_str


def test_workflow_yaml_has_update_manifest():
    yaml_str = generate_workflow_yaml("smmh", "https://docs.smmh.dev", "blog.smmh.dev")
    # Manifest copy is inside the commit-and-push retry loop
    assert "manifests/" in yaml_str
    assert "manifest.json" in yaml_str


def test_workflow_yaml_has_wrangler_deploy():
    yaml_str = generate_workflow_yaml("smmh", "https://docs.smmh.dev", "blog.smmh.dev")
    assert "wrangler pages deploy site/ --project-name 'smmh'" in yaml_str


def test_workflow_yaml_has_secrets():
    yaml_str = generate_workflow_yaml("smmh", "https://docs.smmh.dev", "blog.smmh.dev")
    assert "CF_ACCOUNT_ID" in yaml_str
    assert "CF_PAGES_API_TOKEN" in yaml_str


# -- assembly_init -----------------------------------------------------------


def test_init_returns_three_files():
    result = assembly_init("smm-h/docs-assembly", "smmh", "https://docs.smmh.dev", "blog.smmh.dev")
    assert len(result) == 3


def test_init_has_workflow_file():
    result = assembly_init("smm-h/docs-assembly", "smmh", "https://docs.smmh.dev", "blog.smmh.dev")
    assert ".github/workflows/deploy.yml" in result


def test_init_has_gitignore():
    result = assembly_init("smm-h/docs-assembly", "smmh", "https://docs.smmh.dev", "blog.smmh.dev")
    assert ".gitignore" in result


def test_init_has_projects_json():
    result = assembly_init("smm-h/docs-assembly", "smmh", "https://docs.smmh.dev", "blog.smmh.dev")
    assert "projects.json" in result


def test_init_projects_json_is_valid_empty_json():
    result = assembly_init("smm-h/docs-assembly", "smmh", "https://docs.smmh.dev", "blog.smmh.dev")
    parsed = json.loads(result["projects.json"])
    assert parsed == {}


def test_init_gitignore_has_node_modules():
    result = assembly_init("smm-h/docs-assembly", "smmh", "https://docs.smmh.dev", "blog.smmh.dev")
    assert "node_modules" in result[".gitignore"]


def test_init_gitignore_has_dist():
    result = assembly_init("smm-h/docs-assembly", "smmh", "https://docs.smmh.dev", "blog.smmh.dev")
    assert "dist/" in result[".gitignore"]


def test_init_workflow_matches_generator():
    result = assembly_init("smm-h/docs-assembly", "smmh", "https://docs.smmh.dev", "blog.smmh.dev")
    assert result[".github/workflows/deploy.yml"] == generate_workflow_yaml("smmh", "https://docs.smmh.dev", "blog.smmh.dev")


# -- assembly_push -----------------------------------------------------------


def test_push_endpoint():
    result = assembly_push("owner/assembly", "owner/proj", "myslug", "1.0.0", "v1.0.0")
    assert result["endpoint"] == "/repos/owner/assembly/dispatches"


def test_push_event_type():
    result = assembly_push("owner/assembly", "owner/proj", "myslug", "1.0.0", "v1.0.0")
    assert result["payload"]["event_type"] == "project-updated"


def test_push_client_payload_fields():
    result = assembly_push("owner/assembly", "owner/proj", "myslug", "1.0.0", "v1.0.0")
    cp = result["payload"]["client_payload"]
    assert set(cp.keys()) == {"slug", "version", "ref", "repo"}


def test_push_uses_assembly_repo_in_endpoint():
    result = assembly_push("org/assembly-repo", "org/source-repo", "s", "1", "v1")
    assert "org/assembly-repo" in result["endpoint"]
    assert "org/source-repo" not in result["endpoint"]


def test_push_uses_source_repo_in_payload():
    result = assembly_push("org/assembly-repo", "org/source-repo", "s", "1", "v1")
    cp = result["payload"]["client_payload"]
    assert cp["repo"] == "org/source-repo"
    assert "org/assembly-repo" not in str(cp)


# -- assembly_status ---------------------------------------------------------


def test_status_returns_list():
    result = assembly_status("owner/docs-assembly")
    assert isinstance(result, list)
    assert len(result) >= 1


def test_status_command_has_gh():
    result = assembly_status("owner/docs-assembly")
    assert result[0][0] == "gh"


def test_status_command_targets_repo():
    result = assembly_status("owner/docs-assembly")
    # The repo should appear somewhere in the command args
    cmd_str = " ".join(result[0])
    assert "owner/docs-assembly" in cmd_str


def test_status_queries_workflow_runs():
    result = assembly_status("owner/docs-assembly")
    cmd_str = " ".join(result[0])
    assert "actions/runs" in cmd_str


# -- assembly_rebuild --------------------------------------------------------


def test_rebuild_empty_projects():
    result = assembly_rebuild("owner/assembly", {})
    assert result == []


def test_rebuild_single_project():
    projects = {"myproj": {"repo": "owner/myproj", "ref": "v1.0.0"}}
    result = assembly_rebuild("owner/assembly", projects)
    assert len(result) == 1


def test_rebuild_multiple_projects():
    projects = {
        "proj-a": {"repo": "owner/proj-a", "ref": "v1.0.0"},
        "proj-b": {"repo": "owner/proj-b", "ref": "v2.0.0"},
        "proj-c": {"repo": "owner/proj-c", "ref": "main"},
    }
    result = assembly_rebuild("owner/assembly", projects)
    assert len(result) == 3


def test_rebuild_dispatch_format():
    projects = {"myproj": {"repo": "owner/myproj", "ref": "v1.0.0"}}
    result = assembly_rebuild("owner/assembly", projects)
    for dispatch in result:
        assert "endpoint" in dispatch
        assert "payload" in dispatch


def test_rebuild_uses_project_info():
    projects = {
        "alpha": {"repo": "org/alpha-repo", "ref": "v3.0.0"},
    }
    result = assembly_rebuild("org/assembly", projects)
    dispatch = result[0]
    cp = dispatch["payload"]["client_payload"]
    assert cp["slug"] == "alpha"
    assert cp["repo"] == "org/alpha-repo"
    assert cp["ref"] == "v3.0.0"


# -- workflow: SCOPE extraction -----------------------------------------------


def test_workflow_yaml_extracts_scope():
    """SCOPE is extracted from client_payload in the payload extraction step."""
    yaml_str = generate_workflow_yaml("smmh", "https://docs.smmh.dev", "blog.smmh.dev")
    assert 'SCOPE=${{ github.event.client_payload.scope }}' in yaml_str


# -- workflow: conditional build step -----------------------------------------


def test_workflow_yaml_posts_build():
    """When SCOPE is posts, workflow runs selfblog build --target posts."""
    yaml_str = generate_workflow_yaml("smmh", "https://docs.smmh.dev", "blog.smmh.dev")
    assert 'selfblog build --target posts --no-auto-commit' in yaml_str


def test_workflow_yaml_full_build_with_version():
    """Full build with LATEST_VERSION uses --version flag."""
    yaml_str = generate_workflow_yaml("smmh", "https://docs.smmh.dev", "blog.smmh.dev")
    assert 'selfdoc build --no-auto-commit --version "$LATEST_VERSION"' in yaml_str


def test_workflow_yaml_conditional_build_structure():
    """Build step uses SCOPE conditional to choose posts vs full build."""
    yaml_str = generate_workflow_yaml("smmh", "https://docs.smmh.dev", "blog.smmh.dev")
    assert '[ "$SCOPE" = "posts" ]' in yaml_str


# -- workflow: conditional subtree replacement --------------------------------


def test_workflow_yaml_posts_subtree_replacement():
    """Posts scope replaces only site/$SLUG/posts/ subtree."""
    yaml_str = generate_workflow_yaml("smmh", "https://docs.smmh.dev", "blog.smmh.dev")
    assert 'rm -rf "site/$SLUG/posts/"' in yaml_str


def test_workflow_yaml_posts_manifest_copy():
    """Posts scope copies post-manifest.json to manifests/$SLUG-posts.json."""
    yaml_str = generate_workflow_yaml("smmh", "https://docs.smmh.dev", "blog.smmh.dev")
    assert 'post-manifest.json' in yaml_str
    assert 'manifests/$SLUG-posts.json' in yaml_str


def test_workflow_yaml_full_subtree_replacement():
    """Full build replaces entire site/$SLUG/ subtree."""
    yaml_str = generate_workflow_yaml("smmh", "https://docs.smmh.dev", "blog.smmh.dev")
    assert 'rm -rf "site/$SLUG/"' in yaml_str


def test_workflow_yaml_full_manifest_copy():
    """Full build copies manifest.json to manifests/$SLUG.json."""
    yaml_str = generate_workflow_yaml("smmh", "https://docs.smmh.dev", "blog.smmh.dev")
    assert 'manifests/$SLUG.json' in yaml_str


# -- workflow: reconciliation -------------------------------------------------


def test_workflow_yaml_reconciles_posts_overlay():
    """Full build deletes manifests/$SLUG-posts.json to reconcile overlay."""
    yaml_str = generate_workflow_yaml("smmh", "https://docs.smmh.dev", "blog.smmh.dev")
    assert 'rm -f "manifests/$SLUG-posts.json"' in yaml_str


# -- workflow: LATEST_VERSION robustness --------------------------------------


def test_workflow_yaml_has_version_count_check():
    """When LATEST is empty, workflow checks VERSION_COUNT for multi-version error."""
    yaml_str = generate_workflow_yaml("smmh", "https://docs.smmh.dev", "blog.smmh.dev")
    assert "VERSION_COUNT" in yaml_str
    assert "Could not detect latest version for multi-version project" in yaml_str


# -- push_files_to_repo -------------------------------------------------------


def _mock_run_factory(responses: list[tuple[int, str, str]]):
    """Return a side_effect callable that yields CompletedProcess objects in order."""
    call_log = []
    idx = [0]

    def side_effect(cmd, *, input=None, capture_output=True, text=True,
                    timeout=30, read=False, resource=None, grant=None,
                    cwd=None, env=None, check=False, skip_if_current=None):
        i = idx[0]
        idx[0] += 1
        returncode, stdout, stderr = responses[i]
        call_log.append({"cmd": cmd, "input": input})
        import subprocess

        return subprocess.CompletedProcess(
            args=cmd, returncode=returncode, stdout=stdout, stderr=stderr
        )

    return side_effect, call_log


def test_push_files_successful_sequence():
    """Successful push with 2 files produces correct API call sequence."""
    responses = [
        (0, "abc123\n", ""),  # get HEAD ref
        (0, "tree456\n", ""),  # get tree SHA
        (0, "blob_a\n", ""),  # create blob for file_a
        (0, "blob_b\n", ""),  # create blob for file_b
        (0, "newtree\n", ""),  # create tree
        (0, "newcommit\n", ""),  # create commit
        (0, "newcommit\n", ""),  # update ref
    ]
    effect, call_log = _mock_run_factory(responses)
    files = {"dir/a.txt": "content a", "dir/b.txt": "content b"}
    with patch("selfblog.assembly.effects.run", side_effect=effect):
        sha = push_files_to_repo("owner/repo", files, "test commit")
    assert sha == "newcommit"
    assert len(call_log) == 7
    # Verify call sequence: HEAD, tree, blob, blob, tree, commit, ref
    assert "/repos/owner/repo/git/ref/heads/main" in " ".join(call_log[0]["cmd"])
    assert "/repos/owner/repo/git/commits/abc123" in " ".join(call_log[1]["cmd"])
    assert "--method" in call_log[2]["cmd"] and "blobs" in " ".join(call_log[2]["cmd"])
    assert "--method" in call_log[3]["cmd"] and "blobs" in " ".join(call_log[3]["cmd"])
    assert "--method" in call_log[4]["cmd"] and "trees" in " ".join(call_log[4]["cmd"])
    assert "--method" in call_log[5]["cmd"] and "commits" in " ".join(call_log[5]["cmd"])
    assert "--method" in call_log[6]["cmd"] and "refs" in " ".join(call_log[6]["cmd"])


def test_push_files_blob_error_raises():
    """Error on blob creation raises RuntimeError."""
    responses = [
        (0, "abc123\n", ""),  # get HEAD ref
        (0, "tree456\n", ""),  # get tree SHA
        (1, "", "Not Found"),  # blob creation fails
    ]
    effect, _ = _mock_run_factory(responses)
    with patch("selfblog.assembly.effects.run", side_effect=effect):
        with pytest.raises(RuntimeError, match="create blob"):
            push_files_to_repo("owner/repo", {"f.txt": "x"}, "msg")


def test_push_files_tree_error_raises():
    """Error on tree creation raises RuntimeError."""
    responses = [
        (0, "abc123\n", ""),  # get HEAD ref
        (0, "tree456\n", ""),  # get tree SHA
        (0, "blob_a\n", ""),  # blob OK
        (1, "", "Server Error"),  # tree creation fails
    ]
    effect, _ = _mock_run_factory(responses)
    with patch("selfblog.assembly.effects.run", side_effect=effect):
        with pytest.raises(RuntimeError, match="create tree"):
            push_files_to_repo("owner/repo", {"f.txt": "x"}, "msg")


def test_push_files_empty_dict_raises():
    """Empty files dict raises ValueError."""
    with pytest.raises(ValueError, match="empty"):
        push_files_to_repo("owner/repo", {}, "msg")


def test_push_files_tree_payload_has_correct_paths_and_shas():
    """The tree creation payload includes correct paths and blob SHAs."""
    responses = [
        (0, "head_sha\n", ""),
        (0, "base_tree\n", ""),
        (0, "sha_for_a\n", ""),
        (0, "sha_for_b\n", ""),
        (0, "new_tree\n", ""),
        (0, "new_commit\n", ""),
        (0, "new_commit\n", ""),
    ]
    effect, call_log = _mock_run_factory(responses)
    files = {"site/index.html": "<html/>", "site/style.css": "body{}"}
    with patch("selfblog.assembly.effects.run", side_effect=effect):
        push_files_to_repo("owner/repo", files, "deploy")
    # call_log[4] is the tree creation call
    tree_input = json.loads(call_log[4]["input"])
    assert tree_input["base_tree"] == "base_tree"
    tree_entries = tree_input["tree"]
    paths = {e["path"] for e in tree_entries}
    shas = {e["sha"] for e in tree_entries}
    assert paths == {"site/index.html", "site/style.css"}
    assert shas == {"sha_for_a", "sha_for_b"}
    for entry in tree_entries:
        assert entry["mode"] == "100644"
        assert entry["type"] == "blob"


# -- workflow: shared-only scope -----------------------------------------------


def test_workflow_yaml_clone_step_has_shared_only_condition():
    """Clone source project step has if: condition skipping shared-only scope."""
    yaml_str = generate_workflow_yaml("smmh", "https://docs.smmh.dev", "blog.smmh.dev")
    # Find the clone step and check it has the if: condition before the uses: line
    lines = yaml_str.splitlines()
    for i, line in enumerate(lines):
        if "Clone source project" in line:
            # The if: condition should be on the next line (after the step name)
            remaining = "\n".join(lines[i : i + 3])
            assert "github.event.client_payload.scope != 'shared-only'" in remaining
            break
    else:
        raise AssertionError("Clone source project step not found")


def test_workflow_yaml_build_step_has_shared_only_condition():
    """Build documentation step has if: condition skipping shared-only scope."""
    yaml_str = generate_workflow_yaml("smmh", "https://docs.smmh.dev", "blog.smmh.dev")
    lines = yaml_str.splitlines()
    for i, line in enumerate(lines):
        if "Build documentation" in line:
            remaining = "\n".join(lines[i : i + 3])
            assert "github.event.client_payload.scope != 'shared-only'" in remaining
            break
    else:
        raise AssertionError("Build documentation step not found")


def test_workflow_yaml_version_detection_has_shared_only_condition():
    """Detect latest version step has if: condition skipping shared-only scope."""
    yaml_str = generate_workflow_yaml("smmh", "https://docs.smmh.dev", "blog.smmh.dev")
    lines = yaml_str.splitlines()
    for i, line in enumerate(lines):
        if "Detect latest version" in line:
            remaining = "\n".join(lines[i : i + 3])
            assert "github.event.client_payload.scope != 'shared-only'" in remaining
            break
    else:
        raise AssertionError("Detect latest version step not found")


def test_workflow_yaml_retry_loop_skips_file_copy_for_shared_only():
    """The retry loop wraps file copy in a shared-only conditional."""
    yaml_str = generate_workflow_yaml("smmh", "https://docs.smmh.dev", "blog.smmh.dev")
    # Find the retry loop section (starts with "Commit and push")
    commit_push_idx = yaml_str.index("Commit and push")
    retry_section = yaml_str[commit_push_idx:]
    assert '"$SCOPE" != "shared-only"' in retry_section
    # Within the retry loop, shared-only guard must come before the posts conditional
    idx_shared = retry_section.index('"$SCOPE" != "shared-only"')
    idx_posts = retry_section.index('"$SCOPE" = "posts"')
    assert idx_shared < idx_posts, "shared-only guard must come before posts conditional"
