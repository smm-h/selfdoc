"""Assembly infrastructure for unified multi-project documentation deployment via GitHub Actions dispatch and Cloudflare Pages."""

from __future__ import annotations

import base64
import json
import subprocess


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
          fetch-depth: 0

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
          echo "SCOPE=${{ github.event.client_payload.scope }}" >> "$GITHUB_ENV"

      - name: Clone source project
        if: github.event.client_payload.scope != 'shared-only'
        uses: actions/checkout@v4
        with:
          repository: ${{ github.event.client_payload.repo }}
          ref: ${{ github.event.client_payload.ref }}
          path: source/${{ github.event.client_payload.slug }}
          fetch-depth: 1

      - name: Detect latest version
        if: github.event.client_payload.scope != 'shared-only'
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
          if [ -z "$LATEST" ]; then
            VERSION_COUNT=$(python3 -c "
          import json, os
          cfg_path = 'source/${{ github.event.client_payload.slug }}/selfdoc.json'
          if os.path.isfile(cfg_path):
              cfg = json.load(open(cfg_path))
              print(len(cfg.get('versions', [])))
          else:
              print('0')
          " || echo "0")
            if [ "$VERSION_COUNT" -gt 1 ]; then
              echo "Error: Could not detect latest version for multi-version project"
              exit 1
            fi
          fi

      - name: Build documentation
        if: github.event.client_payload.scope != 'shared-only'
        run: |
          cd "source/$SLUG"
          if [ "$SCOPE" = "posts" ]; then
            selfdoc build --target posts --no-auto-commit
          else
            if [ -n "$LATEST_VERSION" ]; then
              selfdoc build --no-auto-commit --version "$LATEST_VERSION"
            else
              selfdoc build --no-auto-commit
            fi
          fi

      - name: Configure git
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"

      - name: Commit and push
        run: |
          for attempt in 1 2 3; do
            echo "Attempt $attempt"

            # Sync to latest remote (picks up other runs' pushes)
            git fetch origin main
            git reset --hard origin/main

            # Re-apply project-specific files (not affected by other runs)
            mkdir -p manifests/
            if [ "$SCOPE" != "shared-only" ]; then
              if [ "$SCOPE" = "posts" ]; then
                # Posts-only: replace only the posts subtree
                rm -rf "site/$SLUG/posts/"
                mkdir -p "site/$SLUG/posts/"
                if [ -d "source/$SLUG/docs/_build/posts/" ]; then
                  cp -r "source/$SLUG/docs/_build/posts/." "site/$SLUG/posts/"
                fi
                find "site/$SLUG/posts/" \\( -name '*.gz' -o -name '*.br' -o -name '_headers' -o -name '_redirects' -o -name '_worker.js' \\) -delete
                if [ -f "source/$SLUG/.selfdoc/post-manifest.json" ]; then
                  cp "source/$SLUG/.selfdoc/post-manifest.json" "manifests/$SLUG-posts.json"
                fi
              else
                # Full build: replace entire project subtree
                rm -rf "site/$SLUG/"
                mkdir -p "site/$SLUG/"
                cp -r "source/$SLUG/docs/_build/." "site/$SLUG/"
                find "site/$SLUG/" \\( -name '*.gz' -o -name '*.br' -o -name '_headers' -o -name '_redirects' -o -name '_worker.js' \\) -delete
                if [ -f "source/$SLUG/.selfdoc/manifest.json" ]; then
                  cp "source/$SLUG/.selfdoc/manifest.json" "manifests/$SLUG.json"
                fi
                # Reconcile: remove posts overlay since full build replaces it
                rm -f "manifests/$SLUG-posts.json"
              fi

              # Update projects.json on top of latest
              python3 -c "
          import json
          path = 'projects.json'
          try:
              data = json.load(open(path))
          except (FileNotFoundError, json.JSONDecodeError):
              data = {}
          data['$SLUG'] = {
              'repo': '$SOURCE_REPO',
              'ref': '$REF',
              'version': '$VERSION'
          }
          with open(path, 'w') as f:
              json.dump(data, f, indent=2, sort_keys=True)
              f.write('\\n')
          "
            fi

            # Regenerate shared elements with all current manifests
            # Check if selfdoc supports --portfolio-file (added post-0.24.0)
            if selfdoc assembly generate-shared --help 2>&1 | grep -q portfolio-file; then
              PORTFOLIO_FLAG=""
              if [ -f portfolio/index.html ]; then
                PORTFOLIO_FLAG="--portfolio-file portfolio/index.html"
              fi
              selfdoc assembly generate-shared --site-dir site/ --manifests-dir manifests/ --docs-base '' $PORTFOLIO_FLAG
            else
              # Fallback for selfdoc <= 0.24.0: generate shared, then fix URLs and portfolio
              python3 -c "
          import json, os, glob
          from selfdoc.shared import generate_blog_index, generate_homepage, generate_nav_json, generate_unified_feed, generate_sitemap, wrap_shared_page
          from selfdoc.utils import atomic_write
          manifests = []
          overlays = []
          for f in sorted(glob.glob('manifests/*.json')):
              data = json.load(open(f))
              if f.endswith('-posts.json'):
                  overlays.append(data)
              else:
                  manifests.append(data)
          by_slug = {m['slug']: m for m in manifests}
          for o in overlays:
              s = o.get('slug', '')
              if s in by_slug:
                  by_slug[s]['posts'] = o.get('posts', [])
          docs_base = ''
          hp = generate_homepage(manifests, docs_base)
          bl = generate_blog_index(manifests, docs_base)
          nj = generate_nav_json(manifests)
          fe = generate_unified_feed(manifests, docs_base)
          sm = generate_sitemap(manifests, docs_base)
          hp_html = wrap_shared_page('Projects', hp)
          bl_html = wrap_shared_page('Blog', bl)
          hdr = '/*\\n  X-Frame-Options: DENY\\n  X-Content-Type-Options: nosniff\\n  Referrer-Policy: strict-origin-when-cross-origin\\n'
          if os.path.isfile('portfolio/index.html'):
              with open('portfolio/index.html') as pf:
                  atomic_write('site/index.html', pf.read())
              os.makedirs('site/projects', exist_ok=True)
              atomic_write('site/projects/index.html', hp_html)
          else:
              atomic_write('site/index.html', hp_html)
          os.makedirs('site/blog', exist_ok=True)
          atomic_write('site/blog/index.html', bl_html)
          atomic_write('site/nav.json', nj)
          atomic_write('site/feed.xml', fe)
          atomic_write('site/sitemap.xml', sm)
          atomic_write('site/_headers', hdr)
          print('Generated shared files (fallback mode)')
          "
            fi

            # Build search index
            python3 -m pagefind --site site/

            # Commit and try to push
            git add site/ manifests/ projects.json
            git commit -m "deploy: $SLUG v$VERSION" || echo "No changes to commit"
            if git push; then
              echo "Push succeeded on attempt $attempt"
              exit 0
            fi
            echo "Push failed on attempt $attempt, retrying..."
            sleep 5
          done
          echo "All push attempts failed"
          exit 1

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


def _gh_api(args: list[str], input_data: str | None = None, step: str = "") -> str:
    """Run a gh api command and return stdout. Raise RuntimeError on failure."""
    cmd = ["gh", "api", *args]
    try:
        result = subprocess.run(
            cmd,
            input=input_data,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"{step}: gh api timed out after 30s")
    if result.returncode != 0:
        raise RuntimeError(f"{step}: {result.stderr.strip()}")
    return result.stdout.strip()


def push_files_to_repo(
    repo: str,
    files: dict[str, str],
    message: str,
    branch: str = "main",
) -> str:
    """Push multiple files to a remote repo in a single atomic commit via the Git Data API.

    Uses the GitHub REST API (via gh cli) to create blobs, a tree, a commit,
    and update the branch ref -- all without cloning.

    Args:
        repo: GitHub repo identifier (e.g. "smm-h/selfdoc-cache").
        files: Mapping of file paths to content strings.
        message: Commit message.
        branch: Target branch (default "main").

    Returns:
        The SHA of the new commit.

    Raises:
        ValueError: If files dict is empty.
        RuntimeError: If any API call fails.
    """
    if not files:
        raise ValueError("files dict is empty -- nothing to push")

    # 1. Get current HEAD SHA
    head_sha = _gh_api(
        [f"/repos/{repo}/git/ref/heads/{branch}", "--jq", ".object.sha"],
        step="get HEAD ref",
    )

    # 2. Get the current tree SHA
    tree_sha = _gh_api(
        [f"/repos/{repo}/git/commits/{head_sha}", "--jq", ".tree.sha"],
        step="get tree SHA",
    )

    # 3. Create a blob for each file
    blob_shas: dict[str, str] = {}
    for path, content in files.items():
        encoded = base64.b64encode(content.encode()).decode()
        payload = json.dumps({"content": encoded, "encoding": "base64"})
        blob_sha = _gh_api(
            ["--method", "POST", f"/repos/{repo}/git/blobs", "--jq", ".sha", "--input", "-"],
            input_data=payload,
            step=f"create blob for {path}",
        )
        blob_shas[path] = blob_sha

    # 4. Create a new tree
    tree_entries = [
        {"path": path, "mode": "100644", "type": "blob", "sha": sha}
        for path, sha in blob_shas.items()
    ]
    tree_payload = json.dumps({"base_tree": tree_sha, "tree": tree_entries})
    new_tree_sha = _gh_api(
        ["--method", "POST", f"/repos/{repo}/git/trees", "--jq", ".sha", "--input", "-"],
        input_data=tree_payload,
        step="create tree",
    )

    # 5. Create a commit
    commit_payload = json.dumps({
        "message": message,
        "tree": new_tree_sha,
        "parents": [head_sha],
    })
    new_commit_sha = _gh_api(
        ["--method", "POST", f"/repos/{repo}/git/commits", "--jq", ".sha", "--input", "-"],
        input_data=commit_payload,
        step="create commit",
    )

    # 6. Update the ref
    ref_payload = json.dumps({"sha": new_commit_sha})
    _gh_api(
        ["--method", "PATCH", f"/repos/{repo}/git/refs/heads/{branch}", "--jq", ".object.sha", "--input", "-"],
        input_data=ref_payload,
        step="update ref",
    )

    return new_commit_sha
