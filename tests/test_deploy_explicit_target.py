"""Tests for the required explicit target on ``deploy_github_pages``.

``deploy_github_pages`` used to derive its push target from
``git remote get-url origin`` in the process's current working directory,
and then FORCE-push a gh-pages branch there. That is a landmine whenever
the cwd is not the repository the caller meant. The target is now a
required keyword argument: either a git remote URL (used verbatim) or the
path of the repository whose ``origin`` should be used.
"""

import inspect
import json

import pytest

from selfdoc_core.deploy import DeployError, deploy_github_pages


class TestDeployGithubPagesTarget:
    def test_target_parameter_is_required(self):
        sig = inspect.signature(deploy_github_pages)
        assert "target" in sig.parameters
        assert sig.parameters["target"].default is inspect.Parameter.empty

    def test_calling_without_target_is_a_hard_error(self):
        with pytest.raises(TypeError):
            deploy_github_pages("out", "1.0.0")

    def test_empty_target_is_a_hard_error(self, tmp_path):
        with pytest.raises(DeployError) as exc:
            deploy_github_pages(str(tmp_path), "1.0.0", target="")
        assert "target" in str(exc.value).lower()

    def test_nonexistent_path_target_is_a_hard_error(self, tmp_path):
        with pytest.raises(DeployError) as exc:
            deploy_github_pages(
                str(tmp_path), "1.0.0", target=str(tmp_path / "nope"),
            )
        assert "neither a git remote URL nor an existing directory" in str(exc.value)

    def test_repo_root_target_resolves_its_own_remote(self, tmp_path, monkeypatch):
        """A repo-root target must be resolved against THAT repo, not the cwd."""
        calls = []

        def fake_run(cmd, **kwargs):
            calls.append((cmd, kwargs.get("cwd")))
            raise AssertionError("stop before doing any work")

        repo = tmp_path / "repo"
        repo.mkdir()
        monkeypatch.setattr("selfdoc_core.deploy.subprocess.run", fake_run)
        monkeypatch.chdir(tmp_path)

        with pytest.raises(AssertionError):
            deploy_github_pages(str(tmp_path), "1.0.0", target=str(repo))

        cmd, cwd = calls[0]
        assert cmd[:3] == ["git", "remote", "get-url"]
        assert cwd == str(repo)

    def test_remote_url_target_is_used_verbatim(self, tmp_path, monkeypatch):
        """An explicit remote URL must not be resolved through git at all."""
        def fail_run(cmd, **kwargs):
            if cmd[:3] == ["git", "remote", "get-url"]:
                raise AssertionError("must not resolve a remote for a URL target")
            raise AssertionError("stop before doing any work")

        monkeypatch.setattr("selfdoc_core.deploy.subprocess.run", fail_run)
        with pytest.raises(AssertionError) as exc:
            deploy_github_pages(
                str(tmp_path), "1.0.0", target="git@github.com:owner/repo.git",
            )
        assert "must not resolve a remote" not in str(exc.value)


def test_cli_deploy_passes_an_explicit_target(tmp_path, monkeypatch):
    """The single caller must supply the target rather than relying on cwd."""
    from selfdoc import cli

    proj = tmp_path / "proj"
    (proj / "docs" / "_build").mkdir(parents=True)
    (proj / "src").mkdir(parents=True)
    (proj / "src" / "__init__.py").write_text('"""x."""\n', encoding="utf-8")
    (proj / "selfdoc.json").write_text(json.dumps({
        "source": [{"path": "src/", "language": "python"}],
        "docs": "docs/",
        "output": "docs/_build/",
        "base_url": "https://example.com",
        "author": {"name": "Test Author", "url": "https://author.example"},
        "search_engine": "pagefind",
        "version": "1.0.0",
        "versions": [{"version": "1.0.0"}],
        "locales": [{"code": "en", "label": "English", "default": True}],
        "deploy": {"provider": "github-pages"},
    }), encoding="utf-8")

    seen = {}

    def fake_deploy(output_dir, version, *, target):
        seen["target"] = target

    monkeypatch.setattr(
        "selfdoc.deploy.deploy_github_pages", fake_deploy, raising=False,
    )
    monkeypatch.setattr(
        "selfdoc_core.deploy.deploy_github_pages", fake_deploy, raising=False,
    )
    monkeypatch.chdir(proj)
    cli._cmd_deploy(None)

    assert seen["target"] == "."
