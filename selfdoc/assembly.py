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

permissions:
  contents: write

concurrency:
  group: assembly-deploy
  cancel-in-progress: false
  queue: max

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 1

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install tools
        run: pip install selfdoc 'pagefind[bin]'

      - name: Extract payload
        run: |
          echo "SLUG=${{ github.event.client_payload.slug }}" >> "$GITHUB_ENV"
          echo "VERSION=${{ github.event.client_payload.version }}" >> "$GITHUB_ENV"
          echo "REF=${{ github.event.client_payload.ref }}" >> "$GITHUB_ENV"
          echo "SOURCE_REPO=${{ github.event.client_payload.repo }}" >> "$GITHUB_ENV"

      - name: Clone source project
        uses: actions/checkout@v4
        with:
          repository: ${{ github.event.client_payload.repo }}
          ref: ${{ github.event.client_payload.ref }}
          path: source/${{ github.event.client_payload.slug }}
          fetch-depth: 1

      - name: Detect latest version
        run: |
          LATEST=$(python3 -c "
          import json, os
          cfg_path = 'source/${{ github.event.client_payload.slug }}/selfdoc.json'
          if os.path.isfile(cfg_path):
              cfg = json.load(open(cfg_path))
              versions = cfg.get('versions', [])
              if versions:
                  print(versions[-1]['version'])
          " || true)
          echo "LATEST_VERSION=$LATEST" >> "$GITHUB_ENV"

      - name: Build documentation
        run: |
          cd "source/$SLUG"
          if [ -n "$LATEST_VERSION" ]; then
            selfdoc build --no-commit --version "$LATEST_VERSION"
          else
            selfdoc build --no-commit
          fi

      - name: Update project in site
        run: |
          rm -rf "site/$SLUG/"
          mkdir -p "site/$SLUG/"
          cp -r "source/$SLUG/docs/_build/." "site/$SLUG/"
          find "site/$SLUG/" \\( -name '*.gz' -o -name '*.br' -o -name '_headers' -o -name '_redirects' \\) -delete

      - name: Update manifest
        run: |
          mkdir -p manifests/
          if [ -f "source/$SLUG/.selfdoc/manifest.json" ]; then
            cp "source/$SLUG/.selfdoc/manifest.json" "manifests/$SLUG.json"
          fi

      - name: Update projects.json
        run: |
          python3 -c "
          import json
          path = 'projects.json'
          try:
              data = json.load(open(path))
          except (FileNotFoundError, json.JSONDecodeError):
              data = {}
          data['${{ github.event.client_payload.slug }}'] = {
              'repo': '${{ github.event.client_payload.repo }}',
              'ref': '${{ github.event.client_payload.ref }}',
              'version': '${{ github.event.client_payload.version }}'
          }
          with open(path, 'w') as f:
              json.dump(data, f, indent=2, sort_keys=True)
              f.write('\\n')
          "

      - name: Generate shared elements
        run: selfdoc assembly generate-shared --site-dir site/ --manifests-dir manifests/

      - name: Build search index
        run: python3 -m pagefind --site site/

      - name: Configure git
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"

      - name: Commit and push
        run: |
          git add site/ manifests/ projects.json
          git commit -m "deploy: $SLUG v$VERSION" || echo "No changes to commit"
          git pull --rebase
          git push

      - name: Deploy to Cloudflare Pages
        run: npx wrangler pages deploy site/ --project-name smmh
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
source/
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
