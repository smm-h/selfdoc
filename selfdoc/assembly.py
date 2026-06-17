"""Assembly infrastructure for unified multi-project documentation deployment."""

from __future__ import annotations

import json


def generate_workflow_yaml() -> str:
    """Return a GitHub Actions workflow YAML for assembly deployment."""
    return """\
name: Assembly Deploy

on:
  repository_dispatch:
    types: [project-updated]

concurrency:
  group: assembly-deploy
  cancel-in-progress: false
  queue: max

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install selfdoc
        run: pip install selfdoc

      - name: Extract dispatch payload
        run: |
          echo "SLUG=${{ github.event.client_payload.slug }}" >> "$GITHUB_ENV"
          echo "VERSION=${{ github.event.client_payload.version }}" >> "$GITHUB_ENV"
          echo "REF=${{ github.event.client_payload.ref }}" >> "$GITHUB_ENV"
          echo "SOURCE_REPO=${{ github.event.client_payload.repo }}" >> "$GITHUB_ENV"

      - name: Clone triggering project
        run: |
          git clone "https://github.com/$SOURCE_REPO.git" "projects/$SLUG"
          cd "projects/$SLUG"
          git checkout "$REF"

      - name: Build documentation
        run: |
          cd "projects/$SLUG"
          selfdoc build

      - name: Deploy to Cloudflare Pages
        run: npx wrangler pages deploy dist --project-name assembly-docs
        env:
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_PAGES_API_TOKEN }}
"""


def assembly_init(repo_name: str) -> dict[str, str]:
    """Return a dict mapping filename to file content for a new assembly repo.

    repo_name: e.g. "smm-h/docs-assembly"
    """
    return {
        ".github/workflows/deploy.yml": generate_workflow_yaml(),
        ".gitignore": _gitignore_content(),
        "projects.json": json.dumps({}, indent=2) + "\n",
    }


def _gitignore_content() -> str:
    """Return a .gitignore suitable for a CI-only assembly repo."""
    return """\
node_modules/
.wrangler/
dist/
projects/
*.log
"""


def assembly_push(
    assembly_repo: str,
    source_repo: str,
    slug: str,
    version: str,
    ref: str,
) -> dict:
    """Return the API endpoint and payload for a repository_dispatch event.

    assembly_repo: the assembly repo (e.g. "smm-h/docs-assembly")
    source_repo: the source project repo (e.g. "smm-h/selfdoc")
    slug: the project slug
    version: the version being deployed
    ref: the git ref (tag or branch) to clone
    """
    return {
        "endpoint": f"/repos/{assembly_repo}/dispatches",
        "payload": {
            "event_type": "project-updated",
            "client_payload": {
                "slug": slug,
                "version": version,
                "ref": ref,
                "repo": source_repo,
            },
        },
    }


def assembly_status(repo: str) -> list[list[str]]:
    """Return a list of gh CLI argument lists to query recent workflow runs.

    repo: the assembly repo identifier (e.g. "smm-h/docs-assembly")
    """
    return [
        [
            "gh",
            "api",
            f"/repos/{repo}/actions/runs",
            "--jq",
            ".workflow_runs[:5] | .[] | {status, conclusion, created_at, html_url}",
        ],
    ]


def assembly_rebuild(
    repo: str,
    projects: dict[str, dict],
) -> list[dict]:
    """Return dispatch payloads for rebuilding all projects.

    repo: the assembly repo identifier
    projects: mapping of slug to project info (must have "repo" and "ref" keys)
    """
    return [
        assembly_push(
            assembly_repo=repo,
            source_repo=info["repo"],
            slug=slug,
            version=info.get("version", "latest"),
            ref=info["ref"],
        )
        for slug, info in projects.items()
    ]


def generate_redirects_file(slug: str, docs_base: str) -> str:
    """Return the content of a Cloudflare Pages _redirects file.

    Redirects all paths from the old per-project CF Pages site to the
    assembly site under the project's slug prefix.

    slug: project's URL path segment (e.g. "selfdoc")
    docs_base: base URL of the assembly site (e.g. "https://docs.smmh.dev")
    """
    docs_base = docs_base.rstrip("/")
    return f"/* {docs_base}/{slug}/:splat 301\n"
