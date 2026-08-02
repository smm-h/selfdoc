"""The post/assembly command groups belong to selfblog, not selfdoc."""

from selfblog.cli import app as selfblog_app
from selfdoc.cli import app as selfdoc_app


def test_post_group_registered():
    assert "post" in selfblog_app._groups


def test_assembly_group_registered():
    assert "assembly" in selfblog_app._groups


def test_post_group_help_text():
    assert selfblog_app._groups["post"].help == "Manage blog posts and chronological content for the documentation site"


def test_assembly_group_help_text():
    assert selfblog_app._groups["assembly"].help == "Manage the unified multi-project documentation assembly and deployment"


def test_post_group_has_new_command():
    assert "new" in selfblog_app._groups["post"].commands


def test_assembly_group_has_commands():
    cmds = selfblog_app._groups["assembly"].commands
    assert "init" in cmds
    assert "push" in cmds
    assert "status" in cmds
    assert "rebuild" in cmds


def test_post_help_runs():
    result = selfblog_app.test(["post", "--help"])
    assert result.exit_code == 0


def test_assembly_help_runs():
    result = selfblog_app.test(["assembly", "--help"])
    assert result.exit_code == 0


# -- selfdoc no longer shadows them ------------------------------------------


def test_selfdoc_has_no_post_group():
    assert "post" not in selfdoc_app._groups


def test_selfdoc_has_no_assembly_group():
    assert "assembly" not in selfdoc_app._groups


def test_selfdoc_keeps_its_own_groups():
    assert "baseline" in selfdoc_app._groups
