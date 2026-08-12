"""Tests that the assembly's config keys drive every generated artifact.

`assembly init` used to create a Cloudflare Pages project derived from the
repo basename while the generated deploy workflow hardcoded a different
project name, so a fresh init produced a pipeline that deployed to a
project init never created.  Both sides now read one required config key.
"""

import json
import os
import subprocess

import pytest

from selfblog.assembly import ToolchainPins, assembly_init, generate_workflow_yaml
from selfblog.cli import _cmd_assembly_init

PAGES_PROJECT = "unified-site"
CANONICAL_BASE = "https://docs.example.com"
LEGACY_BLOG_HOST = "blog.example.com"
PINS = ToolchainPins(selfblog="1.2.3", selfdoc="0.36.0", pagefind="1.4.0")


def _setup_project(tmp_path, config_overrides=None):
    config = {
        "source": [{"path": "src/", "language": "python"}],
        "base_url": "https://example.com",
        "version": "1.0.0",
        "versions": [{"version": "1.0.0"}],
        "locales": [{"code": "en", "label": "English", "default": True}],
    }
    if config_overrides:
        config.update(config_overrides)
    (tmp_path / "selfdoc.json").write_text(json.dumps(config))
    (tmp_path / "src").mkdir(exist_ok=True)
    (tmp_path / "src" / "__init__.py").write_text("")
    return tmp_path


# -- generate_workflow_yaml requires its deploy target ------------------------


def test_workflow_requires_pages_project():
    with pytest.raises(ValueError) as excinfo:
        generate_workflow_yaml(
            "", CANONICAL_BASE, LEGACY_BLOG_HOST, PINS,
        )
    assert "pages_project" in str(excinfo.value)


def test_workflow_requires_canonical_base():
    with pytest.raises(ValueError) as excinfo:
        generate_workflow_yaml(
            PAGES_PROJECT, "", LEGACY_BLOG_HOST, PINS,
        )
    assert "docs_base" in str(excinfo.value)


def test_workflow_deploys_to_the_configured_project():
    yaml_str = generate_workflow_yaml(
        PAGES_PROJECT, CANONICAL_BASE, LEGACY_BLOG_HOST, PINS,
    )
    assert f"--project-name '{PAGES_PROJECT}'" in yaml_str
    assert "--project-name smmh" not in yaml_str


def test_workflow_passes_canonical_base_to_generate_shared():
    yaml_str = generate_workflow_yaml(
        PAGES_PROJECT, CANONICAL_BASE, LEGACY_BLOG_HOST, PINS,
    )
    assert f"--canonical-base '{CANONICAL_BASE}'" in yaml_str
    assert f"--legacy-blog-host '{LEGACY_BLOG_HOST}'" in yaml_str


def test_workflow_carries_no_foreign_hostnames():
    """A third-party assembly repo must not inherit our hostnames."""
    yaml_str = generate_workflow_yaml(PAGES_PROJECT, CANONICAL_BASE, "", PINS)
    assert "smmh" not in yaml_str


def test_assembly_init_files_use_the_configured_project():
    files = assembly_init(
        "owner/assembly", PAGES_PROJECT, CANONICAL_BASE, LEGACY_BLOG_HOST,
        PINS,
    )
    workflow = files[".github/workflows/deploy.yml"]
    assert f"--project-name '{PAGES_PROJECT}'" in workflow


# -- init round-trip: create and deploy target the same project ---------------


def test_init_creates_the_project_the_workflow_deploys_to(tmp_path, stub_pypi, monkeypatch):
    _setup_project(tmp_path, {
        "assembly": {"repo": "owner/assembly", "pages_project": PAGES_PROJECT},
        "topology": {
            "slug": "myproject",
            "docs_base": CANONICAL_BASE,
            "legacy_blog_host": LEGACY_BLOG_HOST,
        },
    })
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CF_ACCOUNT_ID", "acct")
    monkeypatch.setenv("CF_PAGES_API_TOKEN", "token")

    pushed = {}
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append([str(c) for c in cmd])
        result = type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()
        if "contents" in " ".join(str(c) for c in cmd):
            payload = json.loads(kwargs["input"])
            import base64
            path = [c for c in cmd if "/contents/" in str(c)][0]
            pushed[str(path).split("/contents/", 1)[1]] = base64.b64decode(
                payload["content"]).decode()
        return result

    monkeypatch.setattr(subprocess, "run", fake_run)
    _cmd_assembly_init(None)

    create_calls = [c for c in calls
                    if "wrangler" in c and "create" in c]
    assert create_calls, "expected a Pages project creation"
    assert PAGES_PROJECT in create_calls[0]

    workflow = pushed[".github/workflows/deploy.yml"]
    assert f"--project-name '{PAGES_PROJECT}'" in workflow
    # The project init creates is the project deploy targets.
    assert create_calls[0][create_calls[0].index("create") + 1] == PAGES_PROJECT


# -- this repo's own config stays coherent ------------------------------------


def test_own_config_declares_a_pages_project():
    from selfdoc_core.config import load_config

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    config = load_config(root)
    assert config["assembly"]["pages_project"]
    assert config["assembly"]["repo"]
    assert "assembly" not in config["topology"]


# -- README command table regenerates from the schema -------------------------


def _repo_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_readme_template_uses_the_live_command_table():
    """The static hand-written table is gone; the directive is back.

    The table was frozen because the retired post/assembly stubs were still
    registered in selfdoc's CLI and polluted the schema.  With the stubs
    deleted the generated table is accurate again.
    """
    template = os.path.join(_repo_root(), "docs", "_README.md")
    with open(template, encoding="utf-8") as f:
        body = f.read()
    assert ":-: table-commands" in body
    assert "| `gen-data` | Generate data files" not in body


def test_command_table_omits_the_deleted_stubs():
    from selfdoc.content import resolve_table_commands

    root = _repo_root()
    table = resolve_table_commands({"schema-dir": "."}, {}, root)
    assert "**baseline**" in table
    assert "`gen-data`" in table
    assert "post" not in table.replace("posts", "")
    assert "**assembly**" not in table


def test_selfdoc_cli_no_longer_registers_selfblog_groups():
    from selfdoc.cli import app

    assert app.test(["post", "list"]).exit_code != 0
    assert app.test(["assembly", "push"]).exit_code != 0
