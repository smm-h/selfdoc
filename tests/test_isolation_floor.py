"""The stricttest isolation floor is actually binding in this suite.

selfdoc's real-write surfaces are authenticated: ``selfdoc deploy`` force-pushes
a ``gh-pages`` branch, ``selfblog assembly init`` creates a GitHub repository
and writes repository secrets, ``selfblog post publish`` commits through the
GitHub Git Data API and dispatches a workflow that republishes the live site,
and the auto-commit chain shells out to the real commit tools. Before the floor,
none of that was structurally prevented -- safety rested on each test
remembering to mock ``subprocess``, and one forgotten mock was one real
authenticated write.

These are the deliberate probes that the floor is doing its job, kept
permanently rather than run once: an isolation guarantee nobody asserts is an
isolation guarantee that quietly lapses.
"""

import os
import shutil
import subprocess

import pytest


def test_home_is_throwaway():
    """HOME points at the session's throwaway directory, not the real one."""
    home = os.environ["HOME"]
    assert "stricttest-env-" in home, (
        f"HOME is {home!r} -- the isolation floor is not active, so every "
        "ambient credential under the real home is live for this suite"
    )
    # The XDG set is repointed into the same throwaway session directory.
    session_dir = os.path.dirname(home)
    for var in (
        "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME", "XDG_STATE_HOME",
    ):
        assert os.environ[var].startswith(session_dir), var


def test_ambient_credentials_are_stripped():
    """No forge, registry or model credential survives into the test env."""
    for var in (
        "GH_TOKEN", "GITHUB_TOKEN", "SSH_AUTH_SOCK",
        "NPM_TOKEN", "PYPI_TOKEN",
        "CF_PAGES_API_TOKEN", "CLOUDFLARE_API_TOKEN",
    ):
        assert os.environ.get(var) is None, f"{var} leaked into the test env"
    # Credential HELPERS are neutralized rather than unset, so that a tool
    # asking for a password gets a hard failure instead of a prompt.
    assert os.environ.get("GIT_ASKPASS") == "/bin/false"
    assert os.environ.get("GIT_TERMINAL_PROMPT") == "0"


@pytest.mark.skipif(shutil.which("gh") is None, reason="gh is not installed")
def test_stored_gh_auth_is_unreachable():
    """``gh`` cannot authenticate from inside the suite.

    The stored credential lives under the real config home; the throwaway one
    has none. This is what turns a forgotten ``subprocess`` mock around
    ``gh repo create`` / ``gh secret set`` / ``gh api --method POST`` from a
    real write into a loud failure.
    """
    result = subprocess.run(
        ["gh", "auth", "status"], capture_output=True, text=True, timeout=30,
    )
    assert result.returncode != 0, (
        "gh is authenticated inside the test environment -- an unmocked "
        "authenticated call would reach the real GitHub API"
    )
