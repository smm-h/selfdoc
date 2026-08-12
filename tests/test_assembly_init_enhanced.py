"""Tests for enhanced assembly init: CF Pages creation and GitHub secrets."""

import json
import subprocess

import pytest

from selfblog.cli import _cmd_assembly_init


def _setup_project(tmp_path, repo="owner/docs-assembly",
                   pages_project="docs-assembly"):
    config = {
        "source": [{"path": "src/", "language": "python"}],
        "base_url": "https://example.com",
        "author": {"name": "Test Author", "url": "https://author.example"},
        "search_engine": "pagefind",
        "version": "1.0.0",
        "versions": [{"version": "1.0.0"}],
        "locales": [{"code": "en", "label": "English", "default": True}],
        "assembly": {"repo": repo, "pages_project": pages_project},
        "topology": {"slug": "myproject", "docs_base": "https://docs.example.com"},
    }
    (tmp_path / "selfdoc.json").write_text(json.dumps(config))
    (tmp_path / "src").mkdir(exist_ok=True)
    (tmp_path / "src" / "__init__.py").write_text("")
    return tmp_path


@pytest.fixture(autouse=True)
def _registry(stub_pypi):
    """Every test here runs `assembly init`, which checks its pins against PyPI.

    The isolation floor denies sockets, so the probe answers from the stub;
    without this the whole module would fail at the network boundary rather
    than at whatever it is actually asserting.
    """
    return stub_pypi


def _make_fake_run(calls):
    """Return a fake subprocess.run that records calls and succeeds on everything."""
    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()
    return fake_run


# -- CF Pages project creation ------------------------------------------------


def test_cf_pages_created_when_env_vars_set(tmp_path, monkeypatch, capsys):
    """CF Pages project creation is attempted when env vars are present."""
    _setup_project(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CF_ACCOUNT_ID", "acct-123")
    monkeypatch.setenv("CF_PAGES_API_TOKEN", "tok-456")

    calls = []
    monkeypatch.setattr(subprocess, "run", _make_fake_run(calls))

    _cmd_assembly_init(None)

    # Find the wrangler call
    wrangler_calls = [c for c in calls if "wrangler" in str(c)]
    assert len(wrangler_calls) == 1
    wrangler_cmd = wrangler_calls[0]
    assert "pages" in wrangler_cmd
    assert "project" in wrangler_cmd
    assert "create" in wrangler_cmd

    captured = capsys.readouterr()
    assert "Created CF Pages project:" in captured.out


def test_cf_pages_uses_alternative_env_vars(tmp_path, monkeypatch, capsys):
    """CF Pages creation works with CLOUDFLARE_ACCOUNT_ID / CLOUDFLARE_API_TOKEN."""
    _setup_project(tmp_path)
    monkeypatch.chdir(tmp_path)
    # Use the alternative env var names
    monkeypatch.setenv("CLOUDFLARE_ACCOUNT_ID", "acct-alt")
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "tok-alt")
    # Make sure the primary names are not set
    monkeypatch.delenv("CF_ACCOUNT_ID", raising=False)
    monkeypatch.delenv("CF_PAGES_API_TOKEN", raising=False)

    calls = []
    monkeypatch.setattr(subprocess, "run", _make_fake_run(calls))

    _cmd_assembly_init(None)

    wrangler_calls = [c for c in calls if "wrangler" in str(c)]
    assert len(wrangler_calls) == 1

    captured = capsys.readouterr()
    assert "Created CF Pages project:" in captured.out


def test_cf_pages_failure_prints_warning(tmp_path, monkeypatch, capsys):
    """When wrangler fails, a warning is printed but init continues."""
    _setup_project(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CF_ACCOUNT_ID", "acct-123")
    monkeypatch.setenv("CF_PAGES_API_TOKEN", "tok-456")

    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        result = type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()
        if "wrangler" in str(cmd):
            result.returncode = 1
            result.stderr = "project already exists"
        return result

    monkeypatch.setattr(subprocess, "run", fake_run)

    _cmd_assembly_init(None)

    captured = capsys.readouterr()
    assert "CF Pages project creation failed" in captured.err
    # Init should still complete successfully
    assert "Assembly repository initialized:" in captured.out


def test_cf_pages_skipped_when_env_vars_missing(tmp_path, monkeypatch, capsys):
    """When CF env vars are missing, a warning is printed and no wrangler call is made."""
    _setup_project(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("CF_ACCOUNT_ID", raising=False)
    monkeypatch.delenv("CF_PAGES_API_TOKEN", raising=False)
    monkeypatch.delenv("CLOUDFLARE_ACCOUNT_ID", raising=False)
    monkeypatch.delenv("CLOUDFLARE_API_TOKEN", raising=False)

    calls = []
    monkeypatch.setattr(subprocess, "run", _make_fake_run(calls))

    _cmd_assembly_init(None)

    wrangler_calls = [c for c in calls if "wrangler" in str(c)]
    assert len(wrangler_calls) == 0

    captured = capsys.readouterr()
    assert "CF_ACCOUNT_ID/CF_PAGES_API_TOKEN not set" in captured.err


# -- Pages project name derivation -------------------------------------------


def test_pages_project_comes_from_config(tmp_path, monkeypatch, capsys):
    """The CF Pages project name is the configured one, not the repo basename."""
    _setup_project(tmp_path, repo="my-org/my-docs-assembly",
                   pages_project="unified-site")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CF_ACCOUNT_ID", "acct-123")
    monkeypatch.setenv("CF_PAGES_API_TOKEN", "tok-456")

    calls = []
    monkeypatch.setattr(subprocess, "run", _make_fake_run(calls))

    _cmd_assembly_init(None)

    wrangler_calls = [c for c in calls if "wrangler" in str(c)]
    assert len(wrangler_calls) == 1
    assert "unified-site" in wrangler_calls[0]
    assert "my-docs-assembly" not in wrangler_calls[0]


# -- GitHub secrets -----------------------------------------------------------


def test_secrets_set_when_env_vars_present(tmp_path, monkeypatch, capsys):
    """GitHub secrets are set when CF env vars are present."""
    _setup_project(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CF_ACCOUNT_ID", "acct-123")
    monkeypatch.setenv("CF_PAGES_API_TOKEN", "tok-456")

    calls = []
    monkeypatch.setattr(subprocess, "run", _make_fake_run(calls))

    _cmd_assembly_init(None)

    secret_calls = [c for c in calls if "secret" in str(c) and "set" in str(c)]
    assert len(secret_calls) == 2

    # Verify CF_ACCOUNT_ID secret
    account_secret_calls = [c for c in secret_calls if "CF_ACCOUNT_ID" in c]
    assert len(account_secret_calls) == 1
    assert "--body" in account_secret_calls[0]
    body_idx = account_secret_calls[0].index("--body")
    assert account_secret_calls[0][body_idx + 1] == "acct-123"

    # Verify CF_PAGES_API_TOKEN secret
    token_secret_calls = [c for c in secret_calls if "CF_PAGES_API_TOKEN" in c]
    assert len(token_secret_calls) == 1
    body_idx = token_secret_calls[0].index("--body")
    assert token_secret_calls[0][body_idx + 1] == "tok-456"

    captured = capsys.readouterr()
    assert "Set GitHub secret: CF_ACCOUNT_ID" in captured.out
    assert "Set GitHub secret: CF_PAGES_API_TOKEN" in captured.out


def test_secrets_not_set_when_env_vars_missing(tmp_path, monkeypatch, capsys):
    """No secret-setting calls when CF env vars are missing."""
    _setup_project(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("CF_ACCOUNT_ID", raising=False)
    monkeypatch.delenv("CF_PAGES_API_TOKEN", raising=False)
    monkeypatch.delenv("CLOUDFLARE_ACCOUNT_ID", raising=False)
    monkeypatch.delenv("CLOUDFLARE_API_TOKEN", raising=False)

    calls = []
    monkeypatch.setattr(subprocess, "run", _make_fake_run(calls))

    _cmd_assembly_init(None)

    secret_calls = [c for c in calls if "secret" in str(c)]
    assert len(secret_calls) == 0


def test_secret_failure_prints_warning(tmp_path, monkeypatch, capsys):
    """When gh secret set fails, a warning is printed but init continues."""
    _setup_project(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CF_ACCOUNT_ID", "acct-123")
    monkeypatch.setenv("CF_PAGES_API_TOKEN", "tok-456")

    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        result = type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()
        if "secret" in str(cmd) and "set" in str(cmd):
            result.returncode = 1
            result.stderr = "permission denied"
        return result

    monkeypatch.setattr(subprocess, "run", fake_run)

    _cmd_assembly_init(None)

    captured = capsys.readouterr()
    assert "Failed to set CF_ACCOUNT_ID secret" in captured.err
    assert "Failed to set CF_PAGES_API_TOKEN secret" in captured.err
    # Init should still complete
    assert "Assembly repository initialized:" in captured.out


def test_only_account_id_set(tmp_path, monkeypatch, capsys):
    """When only CF_ACCOUNT_ID is set (no token), CF Pages is skipped but account secret is set."""
    _setup_project(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CF_ACCOUNT_ID", "acct-123")
    monkeypatch.delenv("CF_PAGES_API_TOKEN", raising=False)
    monkeypatch.delenv("CLOUDFLARE_API_TOKEN", raising=False)

    calls = []
    monkeypatch.setattr(subprocess, "run", _make_fake_run(calls))

    _cmd_assembly_init(None)

    # No wrangler call (both env vars needed for CF Pages)
    wrangler_calls = [c for c in calls if "wrangler" in str(c)]
    assert len(wrangler_calls) == 0

    # But CF_ACCOUNT_ID secret should still be set
    secret_calls = [c for c in calls if "secret" in str(c) and "CF_ACCOUNT_ID" in str(c)]
    assert len(secret_calls) == 1

    captured = capsys.readouterr()
    assert "CF_ACCOUNT_ID/CF_PAGES_API_TOKEN not set" in captured.err


def test_only_token_set(tmp_path, monkeypatch, capsys):
    """When only CF_PAGES_API_TOKEN is set (no account), CF Pages is skipped but token secret is set."""
    _setup_project(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("CF_ACCOUNT_ID", raising=False)
    monkeypatch.delenv("CLOUDFLARE_ACCOUNT_ID", raising=False)
    monkeypatch.setenv("CF_PAGES_API_TOKEN", "tok-456")

    calls = []
    monkeypatch.setattr(subprocess, "run", _make_fake_run(calls))

    _cmd_assembly_init(None)

    # No wrangler call
    wrangler_calls = [c for c in calls if "wrangler" in str(c)]
    assert len(wrangler_calls) == 0

    # But token secret should still be set
    secret_calls = [c for c in calls if "secret" in str(c) and "CF_PAGES_API_TOKEN" in str(c)]
    assert len(secret_calls) == 1
