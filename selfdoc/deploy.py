"""Deploy providers for selfdoc documentation sites.

Supports:
- Cloudflare Pages (via wrangler CLI)
- GitHub Pages (via git force-push to gh-pages branch)
"""

import os
import shutil
import subprocess
import sys
import tempfile


class DeployError(RuntimeError):
    """Raised when a deploy operation fails."""

    pass


def _resolve_cloudflare_env():
    """Resolve Cloudflare environment variable name variations.

    Checks for deprecated CF_ACCOUNT_ID, CF_API_TOKEN, and CF_PAGES_API_TOKEN
    and remaps them to CLOUDFLARE_ACCOUNT_ID / CLOUDFLARE_API_TOKEN so wrangler
    picks them up. Prints deprecation warnings to stderr.
    """
    if not os.environ.get("CLOUDFLARE_ACCOUNT_ID"):
        fallback = os.environ.get("CF_ACCOUNT_ID")
        if fallback:
            print(
                "Warning: CF_ACCOUNT_ID is deprecated. Set CLOUDFLARE_ACCOUNT_ID instead.",
                file=sys.stderr,
            )
            os.environ["CLOUDFLARE_ACCOUNT_ID"] = fallback

    if not os.environ.get("CLOUDFLARE_API_TOKEN"):
        fallback = os.environ.get("CF_API_TOKEN")
        if fallback:
            print(
                "Warning: CF_API_TOKEN is deprecated. Set CLOUDFLARE_API_TOKEN instead.",
                file=sys.stderr,
            )
            os.environ["CLOUDFLARE_API_TOKEN"] = fallback
        else:
            fallback = os.environ.get("CF_PAGES_API_TOKEN")
            if fallback:
                print(
                    "Warning: CF_PAGES_API_TOKEN is deprecated. Set CLOUDFLARE_API_TOKEN instead.",
                    file=sys.stderr,
                )
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


def deploy_github_pages(output_dir, version):
    """Deploy to GitHub Pages by force-pushing output to gh-pages branch.

    Uses a temporary directory to build a fresh commit without touching
    the current working tree. Creates a .nojekyll file to prevent
    Jekyll processing on GitHub.

    Args:
        output_dir: Path to the built HTML output directory.
        version: Version string for the commit message.

    Raises:
        DeployError: If git operations fail or remote is unreachable.
    """
    # Get remote URL from the current repo
    try:
        remote = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except subprocess.CalledProcessError:
        raise DeployError(
            "Could not determine git remote URL. "
            "Ensure 'origin' remote is configured."
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
        with open(nojekyll_path, "w") as f:
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
