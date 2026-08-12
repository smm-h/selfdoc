"""Every member that runs this suite declares the tools the suite needs.

CI syncs from each member's own directory (``working-directory: <member>``
plus ``uv sync --locked``), so a tool declared only in the workspace root's
dev group is absent from that environment.  A member whose ``testpaths``
points back at this suite therefore has to declare, in its OWN dev group,
every tool the suite shells out to -- otherwise the job installs an
environment the suite cannot run in, and the gap only surfaces on CI.

Pagefind is the case that proved it: the build shells out to the indexer for
every site it writes, the indexer was declared only at the workspace root,
and every build-touching test failed on CI with "No module named pagefind"
while passing locally from a root-rooted run.
"""

import os
import tomllib

import pytest


_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# This suite's own directory name, as a member's testpaths would spell it.
_SHARED_SUITE = "../tests"

# Distributions the shared suite cannot run without.  A member's entry may
# carry extras or a version floor ("pagefind[bin]>=1.4.0"), so matching is on
# the distribution name.  ``selfdoc`` is here because the suite tests that
# `assembly sync-workflow` pins the selfdoc INSTALLED beside it, which reads
# distribution metadata -- importable from the repository is not enough.
_REQUIRED_TOOLS = ("pagefind", "pytest", "selfdoc", "stricttest")


def _members():
    """The workspace members declared by the root pyproject."""
    root = os.path.join(_REPO_ROOT, "pyproject.toml")
    with open(root, "rb") as f:
        data = tomllib.load(f)
    return data["tool"]["uv"]["workspace"]["members"]


def _manifest(member):
    with open(os.path.join(_REPO_ROOT, member, "pyproject.toml"), "rb") as f:
        return tomllib.load(f)


def _distribution_name(requirement):
    """The bare distribution name of a dev-group requirement string."""
    for sep in ("[", ">", "<", "=", "!", "~", ";", " "):
        requirement = requirement.split(sep)[0]
    return requirement.strip().lower()


def _members_running_the_shared_suite():
    out = []
    for member in _members():
        manifest = _manifest(member)
        ini = manifest.get("tool", {}).get("pytest", {}).get("ini_options", {})
        if _SHARED_SUITE in (ini.get("testpaths") or []):
            out.append(member)
    return out


def test_some_member_runs_the_shared_suite():
    """Guard the guard: a typo in testpaths must not empty this file out."""
    assert _members_running_the_shared_suite(), (
        "no workspace member declares testpaths = [\"../tests\"], so the "
        "checks in this file would silently cover nothing"
    )


@pytest.mark.parametrize("member", _members_running_the_shared_suite())
@pytest.mark.parametrize("tool", _REQUIRED_TOOLS)
def test_member_declares_the_tools_the_shared_suite_needs(member, tool):
    manifest = _manifest(member)
    if manifest.get("project", {}).get("name", "").lower() == tool:
        pytest.skip(f"{member} IS {tool}; its own sync installs it")
    dev = manifest.get("dependency-groups", {}).get("dev", [])
    declared = {_distribution_name(req) for req in dev}
    assert tool in declared, (
        f"{member}/pyproject.toml runs this suite (testpaths = "
        f'["{_SHARED_SUITE}"]) but its dev group does not declare {tool!r}. '
        "CI syncs from that directory, so inheriting the tool from the "
        "workspace root's dev group does not reach the job."
    )
