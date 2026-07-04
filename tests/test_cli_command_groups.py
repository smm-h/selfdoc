import pytest

from selfdoc.cli import app


def test_post_group_registered():
    assert "post" in app._groups


def test_assembly_group_registered():
    assert "assembly" in app._groups


def test_post_group_help_text():
    assert app._groups["post"].help == "Manage blog posts and chronological content for the documentation site"


def test_assembly_group_help_text():
    assert app._groups["assembly"].help == "Manage the unified multi-project documentation assembly and deployment"


def test_post_group_has_new_command():
    assert "new" in app._groups["post"].commands


def test_assembly_group_has_commands():
    cmds = app._groups["assembly"].commands
    assert "init" in cmds
    assert "push" in cmds
    assert "status" in cmds
    assert "rebuild" in cmds


def test_post_help_runs():
    result = app.test(["post", "--help"])
    assert result.exit_code == 0


def test_assembly_help_runs():
    result = app.test(["assembly", "--help"])
    assert result.exit_code == 0
