"""Tests for selfblog.assembly -- assembly infrastructure for multi-project docs."""

import json
from unittest.mock import patch

import pytest

from selfblog.assembly import (
    ToolchainPins,
    assembly_init,
    assembly_push,
    assembly_rebuild,
    assembly_status,
    generate_workflow_yaml,
    push_files_to_repo,
)

# The generator renders pins; it never resolves them, so these are just
# three strings the workflow has to come back carrying.
PINS = ToolchainPins(selfblog="1.2.3", selfdoc="0.36.0", pagefind="1.4.0")


# -- generate_workflow_yaml --------------------------------------------------


def test_workflow_yaml_is_valid_yaml():
    """generate_workflow_yaml returns a non-empty string with expected YAML markers."""
    yaml_str = generate_workflow_yaml("smmh", "https://docs.smmh.dev", "blog.smmh.dev", PINS)
    assert isinstance(yaml_str, str)
    assert len(yaml_str) > 0
    # Basic YAML structure markers
    assert "name:" in yaml_str
    assert "on:" in yaml_str
    assert "jobs:" in yaml_str


def test_workflow_yaml_has_dispatch_trigger():
    yaml_str = generate_workflow_yaml("smmh", "https://docs.smmh.dev", "blog.smmh.dev", PINS)
    assert "repository_dispatch" in yaml_str
    assert "project-updated" in yaml_str


def test_workflow_yaml_has_concurrency():
    yaml_str = generate_workflow_yaml("smmh", "https://docs.smmh.dev", "blog.smmh.dev", PINS)
    assert "assembly-deploy" in yaml_str
    assert "cancel-in-progress: false" in yaml_str
    assert "queue: max" in yaml_str


def test_workflow_yaml_has_queue_max():
    """queue: max enables FIFO queuing of up to 100 pending workflow runs."""
    yaml_str = generate_workflow_yaml("smmh", "https://docs.smmh.dev", "blog.smmh.dev", PINS)
    assert "queue: max" in yaml_str


def test_workflow_yaml_has_deploy_job():
    yaml_str = generate_workflow_yaml("smmh", "https://docs.smmh.dev", "blog.smmh.dev", PINS)
    assert "deploy:" in yaml_str
    assert "ubuntu-latest" in yaml_str


def test_workflow_yaml_has_checkout_step():
    yaml_str = generate_workflow_yaml("smmh", "https://docs.smmh.dev", "blog.smmh.dev", PINS)
    assert "actions/checkout@v4" in yaml_str


def test_workflow_yaml_first_checkout_has_fetch_depth():
    yaml_str = generate_workflow_yaml("smmh", "https://docs.smmh.dev", "blog.smmh.dev", PINS)
    # First checkout uses full clone for push retry support
    assert "fetch-depth: 0" in yaml_str


def test_workflow_yaml_has_second_checkout_for_source():
    """Workflow has a second actions/checkout to clone the source project."""
    yaml_str = generate_workflow_yaml("smmh", "https://docs.smmh.dev", "blog.smmh.dev", PINS)
    # There should be two occurrences of actions/checkout@v4
    count = yaml_str.count("actions/checkout@v4")
    assert count == 2, f"Expected 2 checkout steps, found {count}"
    # The second checkout should clone into source/
    assert "path: source/" in yaml_str


def test_workflow_yaml_has_python_setup():
    yaml_str = generate_workflow_yaml("smmh", "https://docs.smmh.dev", "blog.smmh.dev", PINS)
    assert "actions/setup-python@v5" in yaml_str
    assert "3.12" in yaml_str


def test_workflow_yaml_has_permissions():
    yaml_str = generate_workflow_yaml("smmh", "https://docs.smmh.dev", "blog.smmh.dev", PINS)
    assert "permissions:" in yaml_str
    assert "contents: write" in yaml_str


def test_workflow_yaml_installs_the_toolchain():
    yaml_str = generate_workflow_yaml("smmh", "https://docs.smmh.dev", "blog.smmh.dev", PINS)
    assert "pip install 'selfdoc==" in yaml_str
    assert "'pagefind[bin]==" in yaml_str


def test_workflow_yaml_pins_the_selfblog_version():
    """The install line names one selfblog version, not 'whatever is newest'."""
    yaml_str = generate_workflow_yaml(
        "smmh", "https://docs.smmh.dev", "blog.smmh.dev",
        ToolchainPins(selfblog="9.9.9", selfdoc="0.36.0", pagefind="1.4.0"),
    )
    assert "'selfblog==9.9.9'" in yaml_str


def test_workflow_yaml_refuses_to_generate_without_pins():
    """The generator renders pins and never invents them."""
    with pytest.raises(ValueError):
        generate_workflow_yaml(
            "smmh", "https://docs.smmh.dev", "", "1.2.3",
        )


def test_workflow_yaml_invokes_the_integrate_command():
    yaml_str = generate_workflow_yaml("smmh", "https://docs.smmh.dev", "blog.smmh.dev", PINS)
    assert "selfblog assembly integrate" in yaml_str


def test_workflow_yaml_hands_every_payload_field_to_integrate():
    yaml_str = generate_workflow_yaml("smmh", "https://docs.smmh.dev", "blog.smmh.dev", PINS)
    for flag, field in (
        ("--slug", "slug"),
        ("--version", "version"),
        ("--ref", "ref"),
        ("--source-repo", "repo"),
        ("--scope", "scope"),
    ):
        assert f"{flag} '${{{{ github.event.client_payload.{field} }}}}'" in yaml_str


def test_workflow_yaml_hands_the_config_values_to_integrate():
    yaml_str = generate_workflow_yaml("smmh", "https://docs.smmh.dev", "blog.smmh.dev", PINS)
    assert "--canonical-base 'https://docs.smmh.dev'" in yaml_str
    assert "--legacy-blog-host 'blog.smmh.dev'" in yaml_str


def test_workflow_yaml_has_no_inline_interpreter():
    """The deploy body lives in a command, not in embedded interpreters."""
    yaml_str = generate_workflow_yaml("smmh", "https://docs.smmh.dev", "blog.smmh.dev", PINS)
    for marker in ("python3 -c", "python -c", "python3 -m", "python -m",
                   "import json", "json.dump", "bash -c", "sh -c"):
        assert marker not in yaml_str, f"workflow still embeds {marker!r}"


def test_workflow_yaml_has_no_recursive_deletion():
    """Nothing in CI shell may recursively delete a tree any more."""
    yaml_str = generate_workflow_yaml("smmh", "https://docs.smmh.dev", "blog.smmh.dev", PINS)
    assert "rm -rf" not in yaml_str
    assert "rm -r " not in yaml_str
    assert "rm -f " not in yaml_str


def test_workflow_yaml_has_no_embedded_retry_loop_or_git_plumbing():
    yaml_str = generate_workflow_yaml("smmh", "https://docs.smmh.dev", "blog.smmh.dev", PINS)
    for marker in ("for attempt", "git fetch", "git reset", "git commit",
                   "git push", "git config", "git add", "cp -r", "find "):
        assert marker not in yaml_str, f"workflow still embeds {marker!r}"


def test_workflow_yaml_step_count_is_thin():
    """checkout, setup-python, install, clone, integrate, deploy -- and no more."""
    yaml_str = generate_workflow_yaml("smmh", "https://docs.smmh.dev", "blog.smmh.dev", PINS)
    steps = [line for line in yaml_str.splitlines()
             if line.strip().startswith("- name:") or line.strip().startswith("- uses:")]
    assert len(steps) == 6, steps


def test_workflow_yaml_has_wrangler_deploy():
    yaml_str = generate_workflow_yaml("smmh", "https://docs.smmh.dev", "blog.smmh.dev", PINS)
    assert "wrangler pages deploy site/ --project-name 'smmh'" in yaml_str


def test_workflow_yaml_has_secrets():
    yaml_str = generate_workflow_yaml("smmh", "https://docs.smmh.dev", "blog.smmh.dev", PINS)
    assert "CF_ACCOUNT_ID" in yaml_str
    assert "CF_PAGES_API_TOKEN" in yaml_str


# -- assembly_init -----------------------------------------------------------


def test_init_returns_four_files():
    result = assembly_init("smm-h/docs-assembly", "smmh", "https://docs.smmh.dev", "blog.smmh.dev", PINS)
    assert sorted(result) == [
        ".github/workflows/deploy.yml", ".gitignore", "projects.json",
        "roster.toml",
    ]


def test_init_has_workflow_file():
    result = assembly_init("smm-h/docs-assembly", "smmh", "https://docs.smmh.dev", "blog.smmh.dev", PINS)
    assert ".github/workflows/deploy.yml" in result


def test_init_has_gitignore():
    result = assembly_init("smm-h/docs-assembly", "smmh", "https://docs.smmh.dev", "blog.smmh.dev", PINS)
    assert ".gitignore" in result


def test_init_has_projects_json():
    result = assembly_init("smm-h/docs-assembly", "smmh", "https://docs.smmh.dev", "blog.smmh.dev", PINS)
    assert "projects.json" in result


def test_init_projects_json_is_valid_empty_json():
    result = assembly_init("smm-h/docs-assembly", "smmh", "https://docs.smmh.dev", "blog.smmh.dev", PINS)
    parsed = json.loads(result["projects.json"])
    assert parsed == {}


def test_init_gitignore_has_node_modules():
    result = assembly_init("smm-h/docs-assembly", "smmh", "https://docs.smmh.dev", "blog.smmh.dev", PINS)
    assert "node_modules" in result[".gitignore"]


def test_init_gitignore_has_dist():
    result = assembly_init("smm-h/docs-assembly", "smmh", "https://docs.smmh.dev", "blog.smmh.dev", PINS)
    assert "dist/" in result[".gitignore"]


def test_init_workflow_matches_generator():
    result = assembly_init("smm-h/docs-assembly", "smmh", "https://docs.smmh.dev", "blog.smmh.dev", PINS)
    assert result[".github/workflows/deploy.yml"] == generate_workflow_yaml("smmh", "https://docs.smmh.dev", "blog.smmh.dev", PINS)


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
    projects = {"myproj": {"repo": "owner/myproj", "ref": "v1.0.0",
                           "version": "1.0.0"}}
    result = assembly_rebuild("owner/assembly", projects)
    assert len(result) == 1


def test_rebuild_multiple_projects():
    projects = {
        "proj-a": {"repo": "owner/proj-a", "ref": "v1.0.0", "version": "1.0.0"},
        "proj-b": {"repo": "owner/proj-b", "ref": "v2.0.0", "version": "2.0.0"},
        "proj-c": {"repo": "owner/proj-c", "ref": "main", "version": "3.0.0"},
    }
    result = assembly_rebuild("owner/assembly", projects)
    assert len(result) == 3


def test_rebuild_dispatch_format():
    projects = {"myproj": {"repo": "owner/myproj", "ref": "v1.0.0",
                           "version": "1.0.0"}}
    result = assembly_rebuild("owner/assembly", projects)
    for dispatch in result:
        assert "endpoint" in dispatch
        assert "payload" in dispatch


def test_rebuild_uses_project_info():
    projects = {
        "alpha": {"repo": "org/alpha-repo", "ref": "v3.0.0", "version": "3.0.0"},
    }
    result = assembly_rebuild("org/assembly", projects)
    dispatch = result[0]
    cp = dispatch["payload"]["client_payload"]
    assert cp["slug"] == "alpha"
    assert cp["repo"] == "org/alpha-repo"
    assert cp["ref"] == "v3.0.0"
    assert cp["version"] == "3.0.0"


def test_rebuild_refuses_a_membership_entry_with_no_version():
    """A missing version used to become the literal string "latest".

    That string travelled into the dispatch payload and back out into
    projects.json, so the assembly's own membership record then claimed a
    version nobody ever released.
    """
    projects = {"alpha": {"repo": "org/alpha-repo", "ref": "v3.0.0"}}
    with pytest.raises(RuntimeError) as excinfo:
        assembly_rebuild("org/assembly", projects)
    message = str(excinfo.value)
    assert "alpha" in message, "the offending project must be named"
    assert "version" in message, "the missing field must be named"


def test_rebuild_never_invents_the_string_latest():
    projects = {"alpha": {"repo": "org/alpha-repo", "ref": "v3.0.0"}}
    with pytest.raises(RuntimeError):
        assembly_rebuild("org/assembly", projects)


def test_rebuild_refuses_a_membership_entry_with_no_repo():
    projects = {"alpha": {"ref": "v3.0.0", "version": "3.0.0"}}
    with pytest.raises(RuntimeError, match="repo"):
        assembly_rebuild("org/assembly", projects)


def test_rebuild_refuses_a_membership_entry_with_no_ref():
    projects = {"alpha": {"repo": "org/alpha-repo", "version": "3.0.0"}}
    with pytest.raises(RuntimeError, match="ref"):
        assembly_rebuild("org/assembly", projects)


def test_rebuild_refuses_an_empty_version_string():
    projects = {"alpha": {"repo": "org/alpha-repo", "ref": "v3.0.0",
                          "version": ""}}
    with pytest.raises(RuntimeError, match="version"):
        assembly_rebuild("org/assembly", projects)


# -- workflow: the scope reaches the command, not a shell branch --------------


def test_workflow_yaml_scope_is_a_command_flag():
    """SCOPE is no longer an env var branched on by shell."""
    yaml_str = generate_workflow_yaml("smmh", "https://docs.smmh.dev", "blog.smmh.dev", PINS)
    assert "--scope '${{ github.event.client_payload.scope }}'" in yaml_str
    assert 'SCOPE=' not in yaml_str
    assert '[ "$SCOPE"' not in yaml_str


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


EMPTY_TREE = json.dumps({"sha": "tree456", "truncated": False, "tree": []})


def test_push_files_successful_sequence():
    """Successful push with 2 files produces correct API call sequence."""
    responses = [
        (0, "abc123\n", ""),  # get HEAD ref
        (0, "tree456\n", ""),  # get tree SHA
        (0, EMPTY_TREE, ""),  # list the remote tree (nothing there yet)
        (0, "blob_a\n", ""),  # create blob for file_a
        (0, "blob_b\n", ""),  # create blob for file_b
        (0, "newtree\n", ""),  # create tree
        (0, "newcommit\n", ""),  # create commit
        (0, "newcommit\n", ""),  # update ref
    ]
    effect, call_log = _mock_run_factory(responses)
    files = {"dir/a.txt": "content a", "dir/b.txt": "content b"}
    with patch("selfblog.assembly.effects.run", side_effect=effect):
        result = push_files_to_repo("owner/repo", files, "test commit")
    assert result.sha == "newcommit"
    assert result.changed is True
    assert len(call_log) == 8
    # Verify call sequence: HEAD, tree, list, blob, blob, tree, commit, ref
    assert "/repos/owner/repo/git/ref/heads/main" in " ".join(call_log[0]["cmd"])
    assert "/repos/owner/repo/git/commits/abc123" in " ".join(call_log[1]["cmd"])
    assert "/repos/owner/repo/git/trees/tree456" in " ".join(call_log[2]["cmd"])
    assert "--method" in call_log[3]["cmd"] and "blobs" in " ".join(call_log[3]["cmd"])
    assert "--method" in call_log[4]["cmd"] and "blobs" in " ".join(call_log[4]["cmd"])
    assert "--method" in call_log[5]["cmd"] and "trees" in " ".join(call_log[5]["cmd"])
    assert "--method" in call_log[6]["cmd"] and "commits" in " ".join(call_log[6]["cmd"])
    assert "--method" in call_log[7]["cmd"] and "refs" in " ".join(call_log[7]["cmd"])


def test_push_files_blob_error_raises():
    """Error on blob creation raises RuntimeError."""
    responses = [
        (0, "abc123\n", ""),  # get HEAD ref
        (0, "tree456\n", ""),  # get tree SHA
        (0, EMPTY_TREE, ""),  # list the remote tree
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
        (0, EMPTY_TREE, ""),  # list the remote tree
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
        (0, json.dumps({"truncated": False, "tree": []}), ""),
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
    # call_log[5] is the tree creation call
    tree_input = json.loads(call_log[5]["input"])
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
    yaml_str = generate_workflow_yaml("smmh", "https://docs.smmh.dev", "blog.smmh.dev", PINS)
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
