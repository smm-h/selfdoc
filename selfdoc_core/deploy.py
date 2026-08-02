"""Deploy providers for selfdoc documentation sites.

Supports:
- Cloudflare Pages (via wrangler CLI)
- GitHub Pages (via git force-push to gh-pages branch)
"""

import os
import shutil
import subprocess
import tempfile


class DeployError(RuntimeError):
    """Raised when a deploy operation fails."""

    pass


def _resolve_cloudflare_env():
    """Bridge CF_* env vars to CLOUDFLARE_* for wrangler.

    Our canonical env var names use the CF_ prefix (CF_ACCOUNT_ID,
    CF_PAGES_API_TOKEN). Wrangler expects CLOUDFLARE_ACCOUNT_ID and
    CLOUDFLARE_API_TOKEN. This function bridges the gap.
    """
    if not os.environ.get("CLOUDFLARE_ACCOUNT_ID"):
        fallback = os.environ.get("CF_ACCOUNT_ID")
        if fallback:
            os.environ["CLOUDFLARE_ACCOUNT_ID"] = fallback

    if not os.environ.get("CLOUDFLARE_API_TOKEN"):
        fallback = os.environ.get("CF_PAGES_API_TOKEN")
        if fallback:
            os.environ["CLOUDFLARE_API_TOKEN"] = fallback


def deploy_cloudflare_pages(output_dir, project_name, version):
    """Deploy to Cloudflare Pages using the Wrangler CLI.

    Requires `wrangler` (Cloudflare CLI) to be installed and authenticated
    (via `wrangler login` or CLOUDFLARE_API_TOKEN env var).

    Args:
        output_dir: Path to the built HTML output directory.
        project_name: Cloudflare Pages project name.
        version: Version string for the commit message.

    Raises:
        DeployError: If wrangler is not installed or the deploy fails.
    """
    _resolve_cloudflare_env()

    if not shutil.which("wrangler"):
        raise DeployError(
            "wrangler CLI not found. Install it with: npm install -g wrangler\n"
            "Then authenticate with: wrangler login"
        )

    cmd = [
        "wrangler",
        "pages",
        "deploy",
        output_dir,
        f"--project-name={project_name}",
        f"--commit-message=v{version}",
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except subprocess.TimeoutExpired:
        raise DeployError(
            f"Cloudflare Pages deploy timed out after 120s for project '{project_name}'"
        )

    if result.returncode != 0:
        raise DeployError(
            f"Cloudflare Pages deploy failed (exit {result.returncode}):\n"
            f"{result.stderr.strip()}"
        )

    print(f"Deployed docs v{version} to Cloudflare Pages project '{project_name}'")


def deploy_github_pages(output_dir, version, *, target):
    """Deploy to GitHub Pages by force-pushing output to gh-pages branch.

    Uses a temporary directory to build a fresh commit without touching
    the current working tree. Creates a .nojekyll file to prevent
    Jekyll processing on GitHub.

    Args:
        output_dir: Path to the built HTML output directory.
        version: Version string for the commit message.
        target: REQUIRED push target. Either a git remote URL (used
            verbatim) or the path to a repository whose ``origin`` remote
            is resolved. This is deliberately not derived from the process's
            current working directory: this function FORCE-pushes a
            gh-pages branch, and a cwd-derived target silently aims that
            force-push at whatever repository the process happens to be
            sitting in.

    Raises:
        DeployError: If *target* is empty, git operations fail, or the
            remote is unreachable.
    """
    if not target:
        raise DeployError(
            "deploy_github_pages requires an explicit push target: pass "
            "either a git remote URL or the path to the repository whose "
            "'origin' remote should be used. This deploy force-pushes the "
            "gh-pages branch, so the target is never inferred."
        )

    if _looks_like_remote_url(target):
        remote = target
    else:
        if not os.path.isdir(target):
            raise DeployError(
                f"deploy_github_pages target '{target}' is neither a git "
                f"remote URL nor an existing directory."
            )
        try:
            remote = subprocess.run(
                ["git", "remote", "get-url", "origin"],
                cwd=target,
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
        except subprocess.CalledProcessError:
            raise DeployError(
                f"Could not determine the git remote URL for '{target}'. "
                "Ensure 'origin' remote is configured there."
            )

    with tempfile.TemporaryDirectory() as tmp:
        # Init a fresh repo and create gh-pages branch
        _run_git(["init"], cwd=tmp)
        _run_git(["checkout", "-b", "gh-pages"], cwd=tmp)

        # Copy HTML output into the temp repo
        for item in os.listdir(output_dir):
            src = os.path.join(output_dir, item)
            dst = os.path.join(tmp, item)
            if os.path.isdir(src):
                shutil.copytree(src, dst)
            else:
                shutil.copy2(src, dst)

        # Prevent Jekyll processing on GitHub
        nojekyll_path = os.path.join(tmp, ".nojekyll")
        with open(nojekyll_path, "w"):
            pass

        # Commit all files
        _run_git(["add", "."], cwd=tmp)
        _run_git(["commit", "-m", f"docs: v{version}"], cwd=tmp)

        # Force-push to gh-pages on the remote
        try:
            subprocess.run(
                ["git", "push", "--force", remote, "gh-pages"],
                cwd=tmp,
                capture_output=True,
                text=True,
                check=True,
                timeout=120,
            )
        except subprocess.TimeoutExpired:
            raise DeployError(
                "GitHub Pages deploy timed out after 120s while pushing to gh-pages"
            )
        except subprocess.CalledProcessError as e:
            raise DeployError(
                f"Failed to push to gh-pages branch:\n{e.stderr.strip()}"
            )

    print(f"Deployed docs v{version} to GitHub Pages (gh-pages branch)")


_REMOTE_URL_PREFIXES = ("http://", "https://", "ssh://", "git://", "file://")


def _looks_like_remote_url(target):
    """True when *target* is a git remote URL rather than a local repo path."""
    if target.startswith(_REMOTE_URL_PREFIXES):
        return True
    # scp-style syntax: user@host:path (no such thing as a ':' in a plain
    # local repo path we would accept here).
    head = target.split("/", 1)[0]
    return "@" in head and ":" in head


def _run_git(args, cwd):
    """Run a git command in the given directory, raising DeployError on failure."""
    result = subprocess.run(
        ["git"] + args,
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise DeployError(
            f"git {' '.join(args)} failed (exit {result.returncode}):\n"
            f"{result.stderr.strip()}"
        )
    return result
