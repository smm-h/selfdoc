"""Tests for selfdoc.assembly -- assembly infrastructure for multi-project docs."""

import json

from selfdoc.assembly import (
    assembly_init,
    assembly_push,
    assembly_rebuild,
    assembly_status,
    generate_workflow_yaml,
)


# -- generate_workflow_yaml --------------------------------------------------


def test_workflow_yaml_is_valid_yaml():
    """generate_workflow_yaml returns a non-empty string with expected YAML markers."""
    yaml_str = generate_workflow_yaml()
    assert isinstance(yaml_str, str)
    assert len(yaml_str) > 0
    # Basic YAML structure markers
    assert "name:" in yaml_str
    assert "on:" in yaml_str
    assert "jobs:" in yaml_str


def test_workflow_yaml_has_dispatch_trigger():
    yaml_str = generate_workflow_yaml()
    assert "repository_dispatch" in yaml_str
    assert "project-updated" in yaml_str


def test_workflow_yaml_has_concurrency():
    yaml_str = generate_workflow_yaml()
    assert "assembly-deploy" in yaml_str
    assert "cancel-in-progress: false" in yaml_str


def test_workflow_yaml_has_deploy_job():
    yaml_str = generate_workflow_yaml()
    assert "deploy:" in yaml_str
    assert "ubuntu-latest" in yaml_str


def test_workflow_yaml_has_checkout_step():
    yaml_str = generate_workflow_yaml()
    assert "actions/checkout@v4" in yaml_str


def test_workflow_yaml_has_python_setup():
    yaml_str = generate_workflow_yaml()
    assert "actions/setup-python@v5" in yaml_str
    assert "3.12" in yaml_str


def test_workflow_yaml_has_selfdoc_install():
    yaml_str = generate_workflow_yaml()
    assert "pip install selfdoc" in yaml_str


def test_workflow_yaml_has_payload_extraction():
    yaml_str = generate_workflow_yaml()
    assert "SLUG=" in yaml_str
    assert "VERSION=" in yaml_str
    assert "REF=" in yaml_str
    assert "SOURCE_REPO=" in yaml_str


def test_workflow_yaml_has_clone_step():
    yaml_str = generate_workflow_yaml()
    assert "git clone --depth 1" in yaml_str


def test_workflow_yaml_has_build_step():
    yaml_str = generate_workflow_yaml()
    assert "selfdoc build" in yaml_str


def test_workflow_yaml_has_wrangler_deploy():
    yaml_str = generate_workflow_yaml()
    assert "wrangler pages deploy" in yaml_str


def test_workflow_yaml_has_secrets():
    yaml_str = generate_workflow_yaml()
    assert "CF_ACCOUNT_ID" in yaml_str
    assert "CF_PAGES_API_TOKEN" in yaml_str


# -- assembly_init -----------------------------------------------------------


def test_init_returns_three_files():
    result = assembly_init("smm-h/docs-assembly")
    assert len(result) == 3


def test_init_has_workflow_file():
    result = assembly_init("smm-h/docs-assembly")
    assert ".github/workflows/deploy.yml" in result


def test_init_has_gitignore():
    result = assembly_init("smm-h/docs-assembly")
    assert ".gitignore" in result


def test_init_has_projects_json():
    result = assembly_init("smm-h/docs-assembly")
    assert "projects.json" in result


def test_init_projects_json_is_valid_empty_json():
    result = assembly_init("smm-h/docs-assembly")
    parsed = json.loads(result["projects.json"])
    assert parsed == {}


def test_init_gitignore_has_node_modules():
    result = assembly_init("smm-h/docs-assembly")
    assert "node_modules" in result[".gitignore"]


def test_init_gitignore_has_dist():
    result = assembly_init("smm-h/docs-assembly")
    assert "dist/" in result[".gitignore"]


def test_init_workflow_matches_generator():
    result = assembly_init("smm-h/docs-assembly")
    assert result[".github/workflows/deploy.yml"] == generate_workflow_yaml()


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
