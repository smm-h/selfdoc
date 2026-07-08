"""CLI interface for selfblog.

Owns the blog post and assembly command groups. Imports from
selfdoc_core (shared engine) and selfblog, never from selfdoc.
"""

import datetime
import json
import os
import sys

import strictcli

from selfblog import __version__


app = strictcli.App(
    name="selfblog",
    version=__version__,
    help="Blog system for selfdoc-based documentation sites",
)

post_group = app.group("post", help="Manage blog posts and chronological content for the documentation site")
assembly_group = app.group("assembly", help="Manage the unified multi-project documentation assembly and deployment")


# -- post commands -----------------------------------------------------------


@post_group.command("new", help="Scaffold a new blog post markdown file with a date-prefixed filename and frontmatter template containing title, date, slug, tags, draft status, and project metadata. Creates the file in the configured posts directory and exits with an error if the file already exists.")
@strictcli.flag("title", type=str, help="Title for the new blog post, used in frontmatter and filename generation")
def _cmd_post_new(title=""):
    """Create a new blog post file in the posts directory."""
    from selfdoc_core.config import load_config
    from selfdoc_core.manifest import _to_kebab

    if not title:
        print("Error: --title is required.", file=sys.stderr)
        sys.exit(1)

    config = load_config(".")
    if config is None:
        print("Error: No selfdoc.json found. Run 'selfdoc init' first.", file=sys.stderr)
        sys.exit(1)

    posts_config = config.get("posts") or {}
    posts_dir = posts_config.get("dir", ".selfdoc/posts/")

    slug = _to_kebab(title)
    today = datetime.date.today().isoformat()
    filename = f"{today}-{slug}.md"

    # Determine project slug for the post frontmatter
    project_slug = (config.get("topology") or {}).get("slug")
    if not project_slug:
        name = config.get("name") or os.path.basename(os.path.abspath("."))
        project_slug = _to_kebab(name)

    filepath = os.path.join(posts_dir, filename)

    if os.path.isfile(filepath):
        print(f"Error: Post file already exists: {filepath}", file=sys.stderr)
        sys.exit(1)

    os.makedirs(posts_dir, exist_ok=True)

    content = (
        f"---\n"
        f"title: {title}\n"
        f"date: {today}\n"
        f"slug: {slug}\n"
        f"tags: []\n"
        f"draft: true\n"
        f"project: {project_slug}\n"
        f"---\n"
        f"\n"
    )

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"Created post: {filepath}")
    return 0


@post_group.command("list", help="List all discovered blog posts with date, title, slug, and draft status. Scans the configured posts directory for markdown files with frontmatter, parses their metadata, and prints a formatted summary showing each post's publication date, title, slug identifier, and whether it is marked as a draft.")
def _cmd_post_list():
    """List all discovered blog posts."""
    from selfdoc_core.config import load_config
    from selfblog.posts import discover_posts

    config = load_config(".")
    if config is None:
        print("Error: No selfdoc.json found. Run 'selfdoc init' first.", file=sys.stderr)
        sys.exit(1)

    posts_config = config.get("posts") or {}
    posts_dir = posts_config.get("dir", ".selfdoc/posts/")

    posts = discover_posts(posts_dir)

    if not posts:
        print("No posts found.")
        return 0

    # Print header and aligned rows
    for post in posts:
        draft_marker = "  [DRAFT]" if post["draft"] else ""
        print(f"{post['date']}  {post['title']}  ({post['slug']}){draft_marker}")

    print(f"\n{len(posts)} post(s) found.")
    return 0


@post_group.command("generate", help="Generate a blog post markdown file from structured release metadata. Takes version, bump type, description, changelog, and registry URLs as inputs, produces a frontmatter-bearing post with title, date, tags, and body content, and updates the project manifest with the new post entry.")
@strictcli.flag("from-release", type=bool, help="Generate the post from structured release metadata rather than freeform content")
@strictcli.flag("version", type=str, help="The released version number to feature in the generated blog post title and metadata")
@strictcli.flag("prev-version", type=str, help="Previous version number, used to show what version this release upgrades from")
@strictcli.flag("bump-type", type=str, help="Semver bump type (patch, minor, or major) included in the post frontmatter")
@strictcli.flag("description", type=str, help="Short release description text included as the post summary paragraph")
@strictcli.flag("context", type=str, help="Additional context explaining the rationale for this release, included in generated blog posts")
@strictcli.flag("changelog-file", type=str, help="Path to a markdown file whose contents are embedded as the changelog section of the post")
@strictcli.flag("body-file", type=str, help="Path to a file containing user-written prose to include as the main post body content")
@strictcli.flag("project-name", type=str, help="Human-readable project name used in the blog post title and frontmatter metadata")
@strictcli.flag("release-url", type=str, help="Full URL to the GitHub release page, linked from the generated blog post")
@strictcli.flag("registry-url", type=str, repeatable=True, unique=False, help="Package registry URL such as PyPI or npm page, can be specified multiple times")
@strictcli.flag("dry-run", type=bool, default=False, help="Print the generated post content to stdout without writing any files to disk")
def _cmd_post_generate(
    from_release=False,
    version="",
    prev_version="",
    bump_type="",
    description="",
    context="",
    changelog_file="",
    body_file="",
    project_name="",
    release_url="",
    registry_url=None,
    dry_run=False,
):
    """Generate a blog post from release metadata."""
    from selfdoc_core.config import load_config
    from selfdoc_core.manifest import _to_kebab, generate_manifest, load_manifest
    from selfdoc_core.utils import atomic_write

    if not from_release:
        print("Error: --from-release is required.", file=sys.stderr)
        sys.exit(1)

    if not version:
        print("Error: --version is required.", file=sys.stderr)
        sys.exit(1)

    config = load_config(".")
    if config is None:
        print("Error: No selfdoc.json found. Run 'selfdoc init' first.", file=sys.stderr)
        sys.exit(1)

    posts_config = config.get("posts") or {}
    posts_dir = posts_config.get("dir", ".selfdoc/posts/")

    # Read file contents if paths provided
    changelog_content = ""
    if changelog_file:
        with open(changelog_file, "r", encoding="utf-8") as f:
            changelog_content = f.read().strip()

    body_content = ""
    if body_file:
        with open(body_file, "r", encoding="utf-8") as f:
            body_content = f.read().strip()

    # Determine project name
    if not project_name:
        project_slug = (config.get("topology") or {}).get("slug")
        if not project_slug:
            name = config.get("name") or os.path.basename(os.path.abspath("."))
            project_slug = _to_kebab(name)
    else:
        project_slug = _to_kebab(project_name)

    # Build slug and filename
    today = datetime.date.today().isoformat()
    slug = f"release-v{version}"
    filename = f"{today}-{slug}.md"

    # Build title
    if project_name:
        title = f"{project_name} v{version}"
    else:
        title = f"Release v{version}"

    # Build frontmatter
    fm_lines = [
        "---",
        f"title: {title}",
        f"date: {today}",
        f"slug: {slug}",
        "draft: false",
        f"project: {project_slug}",
        f"version: {version}",
    ]
    if prev_version:
        fm_lines.append(f"prev_version: {prev_version}")
    if bump_type:
        fm_lines.append(f"bump_type: {bump_type}")
    if release_url:
        fm_lines.append(f"release_url: {release_url}")

    # registry_url is a list from repeatable flag (defaults to [] if none given)
    registry_urls = registry_url if registry_url else []
    if registry_urls:
        urls_str = ", ".join(registry_urls)
        fm_lines.append(f"registry_urls: [{urls_str}]")

    fm_lines.append(f"tags: [release, v{version}]")
    fm_lines.append("---")

    # Build body
    body_parts = []
    if body_content:
        body_parts.append(body_content)
    if changelog_content:
        body_parts.append(f"## Changelog\n\n{changelog_content}")
    if not body_parts:
        body_parts.append(f"Version {version} has been released.")

    post_body = "\n\n".join(body_parts)
    full_content = "\n".join(fm_lines) + "\n\n" + post_body + "\n"

    if dry_run:
        print(full_content)
        return 0

    # Write the post file
    os.makedirs(posts_dir, exist_ok=True)
    filepath = os.path.join(posts_dir, filename)
    atomic_write(filepath, full_content)
    print(f"Created post: {filepath}")

    # Update manifest
    manifest_path = os.path.join(".selfdoc", "manifest.json")
    manifest = load_manifest(manifest_path)

    if manifest is not None:
        # Update posts list in manifest and version
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest_data = json.load(f)

        # Add new post entry
        new_post_entry = {
            "path": filename,
            "title": title,
            "date": today,
            "slug": slug,
            "tags": ["release", f"v{version}"],
        }
        posts_list = manifest_data.get("posts", [])
        posts_list.append(new_post_entry)
        manifest_data["posts"] = posts_list

        # Update version
        manifest_data["version"] = version

        atomic_write(manifest_path, json.dumps(manifest_data, indent=2) + "\n")
        print(f"Updated manifest: {manifest_path}")
    else:
        # No existing manifest - generate one fresh
        from selfdoc_core.docs import resolve_all_docs
        all_docs = resolve_all_docs(config, base_dir=".")
        posts_data = [{
            "path": filename,
            "title": title,
            "date": today,
            "slug": slug,
            "tags": ["release", f"v{version}"],
        }]
        generate_manifest(config, all_docs, posts_data=posts_data, dir_path=".")
        print(f"Created manifest: {manifest_path}")

    return 0


@post_group.command("publish", help="Publish non-draft blog posts to the documentation assembly. Builds posts locally, pushes built HTML and manifest to the assembly repo via the Git Data API, then dispatches a shared-only workflow to regenerate cross-project elements.")
def _cmd_post_publish():
    """Publish blog posts to the assembly without a software release."""
    import subprocess

    from selfblog.assembly import push_files_to_repo
    from selfdoc_core.build import _build_posts_only
    from selfdoc_core.config import load_config
    from selfblog.posts import discover_posts

    config = load_config(".")
    if config is None:
        print("Error: No selfdoc.json found. Run 'selfdoc init' first.", file=sys.stderr)
        sys.exit(1)

    # Resolve assembly repo from config
    assembly_config = config.get("assembly") or {}
    repo = assembly_config.get("repo")
    if not repo:
        topology = config.get("topology") or {}
        repo = topology.get("assembly")
    if not repo:
        print("Error: assembly.repo (or topology.assembly) not configured in selfdoc.json.", file=sys.stderr)
        sys.exit(1)

    topology = config.get("topology") or {}
    slug = topology.get("slug")
    if not slug:
        print("Error: topology.slug not configured in selfdoc.json.", file=sys.stderr)
        sys.exit(1)

    # Discover posts and filter to non-draft only
    posts_config = config.get("posts") or {}
    posts_dir = posts_config.get("dir", ".selfdoc/posts/")
    posts = discover_posts(posts_dir)
    non_draft_posts = [p for p in posts if not p["draft"]]

    if not non_draft_posts:
        print("No non-draft posts to publish.")
        return 0

    # Record revisions for posts whose body content changed
    from selfdoc_core.revisions import record_revision

    revisions_path = os.path.join(".selfdoc", "revisions.json")
    revisions_recorded = 0
    for post in non_draft_posts:
        body = post.get("content", "")
        summary = "Initial publish" if not os.path.isfile(revisions_path) else ""
        changed = record_revision(".", post["slug"], body, summary=summary)
        if changed:
            revisions_recorded += 1

    # Build posts locally
    output_dir = os.path.join(".", config["output"].rstrip("/"))
    docs_dir_name = config["docs"].rstrip("/")
    docs_dir = os.path.join(".", docs_dir_name)
    written = _build_posts_only(
        ".", config, output_dir, docs_dir_name, docs_dir, include_drafts=False,
    )

    # Read built HTML files and map to assembly paths
    files = {}
    for abs_path in written:
        rel_in_output = os.path.relpath(abs_path, output_dir)
        assembly_path = f"site/{slug}/{rel_in_output}"
        with open(abs_path, "r", encoding="utf-8") as f:
            files[assembly_path] = f.read()

    # Read post-manifest and map to assembly path
    post_manifest_path = os.path.join(".selfdoc", "post-manifest.json")
    if os.path.isfile(post_manifest_path):
        with open(post_manifest_path, "r", encoding="utf-8") as f:
            files[f"manifests/{slug}-posts.json"] = f.read()

    # Include revisions sidecar if it exists
    if os.path.isfile(revisions_path):
        with open(revisions_path, "r", encoding="utf-8") as f:
            files[f"manifests/{slug}-revisions.json"] = f.read()

    # Push files to assembly repo via Git Data API
    push_files_to_repo(repo, files, f"posts: {slug}")

    # Dispatch shared-only rebuild to regenerate cross-project elements
    dispatch_payload = json.dumps({
        "event_type": "project-updated",
        "client_payload": {"scope": "shared-only"},
    })
    result = subprocess.run(
        ["gh", "api", "--method", "POST",
         f"/repos/{repo}/dispatches", "--input", "-"],
        input=dispatch_payload, check=False, capture_output=True,
        text=True, timeout=30,
    )
    if result.returncode != 0:
        print(f"Error: Failed to dispatch shared rebuild: {result.stderr.strip()}", file=sys.stderr)
        sys.exit(1)

    # Archive resolved markdown to the posts repo if configured
    posts_repo = (config.get("posts") or {}).get("repo")
    if posts_repo:
        from selfdoc_core.directives import resolve_directives
        from selfdoc_core.resolver import make_resolver

        resolver = make_resolver(config, ".")
        post_files = {}
        for post in non_draft_posts:
            resolved_content = resolve_directives(post["content"], resolver)
            post_files[f"{slug}/{post['path']}"] = resolved_content
        push_files_to_repo(posts_repo, post_files, f"posts: {slug}")
        print(f"Archived {len(non_draft_posts)} post(s) to {posts_repo}")

    print(f"Published {len(non_draft_posts)} post(s) to assembly. Shared elements will regenerate.")
    return 0


# -- assembly commands -------------------------------------------------------


@assembly_group.command("init", help="Create and initialize the assembly GitHub repository with workflow and configuration files. Creates a private GitHub repo, pushes initial files via the Contents API, creates a Cloudflare Pages project if credentials are available, and sets GitHub secrets for deployment authentication.")
def _cmd_assembly_init():
    """Create the assembly GitHub repo and push initial files."""
    import base64
    import subprocess

    from selfblog.assembly import assembly_init
    from selfdoc_core.config import load_config

    config = load_config(".")
    if config is None:
        print("Error: No selfdoc.json found. Run 'selfdoc init' first.", file=sys.stderr)
        sys.exit(1)

    assembly_config = config.get("assembly") or {}
    repo = assembly_config.get("repo")
    if not repo:
        print("Error: assembly.repo not configured in selfdoc.json.", file=sys.stderr)
        sys.exit(1)

    files = assembly_init(repo)

    # Create the private GitHub repo
    print(f"Creating repository {repo}...")
    result = subprocess.run(
        ["gh", "repo", "create", repo, "--private"],
        check=False, capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        print(f"Error: Failed to create repository: {result.stderr.strip()}", file=sys.stderr)
        sys.exit(1)

    # Push initial files via GitHub Contents API
    for filepath, content in files.items():
        print(f"  Creating {filepath}...")
        encoded = base64.b64encode(content.encode()).decode()
        payload = json.dumps({"message": f"Initial: {filepath}", "content": encoded})
        result = subprocess.run(
            ["gh", "api", "--method", "PUT",
             f"/repos/{repo}/contents/{filepath}",
             "--input", "-"],
            input=payload, check=False, capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            print(f"Error: Failed to create {filepath}: {result.stderr.strip()}", file=sys.stderr)
            sys.exit(1)

    # Create CF Pages project
    cf_account = os.environ.get("CF_ACCOUNT_ID") or os.environ.get("CLOUDFLARE_ACCOUNT_ID")
    cf_token = os.environ.get("CF_PAGES_API_TOKEN") or os.environ.get("CLOUDFLARE_API_TOKEN")
    if cf_account and cf_token:
        pages_project = repo.split("/")[-1]  # derive from repo name
        env = os.environ.copy()
        env["CLOUDFLARE_ACCOUNT_ID"] = cf_account
        env["CLOUDFLARE_API_TOKEN"] = cf_token
        result = subprocess.run(
            ["npx", "wrangler", "pages", "project", "create", pages_project, "--production-branch", "main"],
            env=env, check=False, capture_output=True, text=True, timeout=60,
        )
        if result.returncode == 0:
            print(f"Created CF Pages project: {pages_project}")
        else:
            print(f"Warning: CF Pages project creation failed: {result.stderr.strip()}", file=sys.stderr)
    else:
        print("Warning: CF_ACCOUNT_ID/CF_PAGES_API_TOKEN not set, skipping CF Pages project creation.", file=sys.stderr)

    # Set GitHub secrets for CF credentials
    if cf_account:
        result = subprocess.run(
            ["gh", "secret", "set", "CF_ACCOUNT_ID", "--repo", repo, "--body", cf_account],
            check=False, capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            print("Set GitHub secret: CF_ACCOUNT_ID")
        else:
            print(f"Warning: Failed to set CF_ACCOUNT_ID secret: {result.stderr.strip()}", file=sys.stderr)

    if cf_token:
        result = subprocess.run(
            ["gh", "secret", "set", "CF_PAGES_API_TOKEN", "--repo", repo, "--body", cf_token],
            check=False, capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            print("Set GitHub secret: CF_PAGES_API_TOKEN")
        else:
            print(f"Warning: Failed to set CF_PAGES_API_TOKEN secret: {result.stderr.strip()}", file=sys.stderr)

    print(f"Assembly repository initialized: {repo}")
    return 0


@assembly_group.command("push", help="Dispatch a GitHub Actions workflow to rebuild this project in the documentation assembly. Detects the source repository, resolves the latest git tag as the version reference, and sends a repository dispatch event to the assembly repo with the project slug, version, and commit SHA.")
def _cmd_assembly_push():
    """Dispatch an assembly rebuild for the current project."""
    import subprocess

    from selfblog.assembly import assembly_push
    from selfdoc_core.config import load_config

    config = load_config(".")
    if config is None:
        print("Error: No selfdoc.json found. Run 'selfdoc init' first.", file=sys.stderr)
        sys.exit(1)

    # Resolve assembly repo from config
    assembly_config = config.get("assembly") or {}
    repo = assembly_config.get("repo")
    if not repo:
        topology = config.get("topology") or {}
        repo = topology.get("assembly")
    if not repo:
        print("Error: assembly.repo (or topology.assembly) not configured in selfdoc.json.", file=sys.stderr)
        sys.exit(1)

    topology = config.get("topology") or {}
    slug = topology.get("slug")
    if not slug:
        print("Error: topology.slug not configured in selfdoc.json.", file=sys.stderr)
        sys.exit(1)

    # Detect source repo
    result = subprocess.run(
        ["gh", "repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner"],
        check=False, capture_output=True, text=True, timeout=15,
    )
    if result.returncode != 0:
        print(f"Error: Failed to detect source repository: {result.stderr.strip()}", file=sys.stderr)
        sys.exit(1)
    source_repo = result.stdout.strip()

    # Detect ref (prefer exact tag on HEAD, fall back to latest tag)
    result = subprocess.run(
        ["git", "describe", "--tags", "--exact-match", "HEAD"],
        check=False, capture_output=True, text=True, timeout=10,
    )
    if result.returncode == 0:
        ref = result.stdout.strip()
    else:
        result = subprocess.run(
            ["git", "describe", "--tags", "--abbrev=0"],
            check=False, capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            ref = result.stdout.strip()
        else:
            print("Error: No git tags found. Run a release first.", file=sys.stderr)
            sys.exit(1)

    # Detect version
    version = config.get("version", "")
    if not version:
        from selfdoc_core.utils import detect_project_version
        version = detect_project_version(".", fallback="0.0.0")

    dispatch = assembly_push(repo, source_repo, slug, version, ref)

    # Execute the dispatch
    payload = json.dumps(dispatch["payload"])
    result = subprocess.run(
        ["gh", "api", "--method", "POST", dispatch["endpoint"], "--input", "-"],
        input=payload, check=False, capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        print(f"Error: Failed to dispatch rebuild: {result.stderr.strip()}", file=sys.stderr)
        sys.exit(1)

    print(f"Dispatched assembly rebuild for {slug} v{version} (ref: {ref})")
    return 0


@assembly_group.command("status", help="Show the status of recent assembly build workflow runs on GitHub. Queries the assembly repository for recent workflow runs using the GitHub CLI and displays their status, conclusion, and timing information for monitoring deployment progress.")
def _cmd_assembly_status():
    """Show recent assembly build status."""
    import subprocess

    from selfblog.assembly import assembly_status
    from selfdoc_core.config import load_config

    config = load_config(".")
    if config is None:
        print("Error: No selfdoc.json found. Run 'selfdoc init' first.", file=sys.stderr)
        sys.exit(1)

    assembly_config = config.get("assembly") or {}
    repo = assembly_config.get("repo")
    if not repo:
        print("Error: assembly.repo not configured in selfdoc.json.", file=sys.stderr)
        sys.exit(1)

    commands = assembly_status(repo)

    found_runs = False
    for cmd in commands:
        result = subprocess.run(
            cmd, check=False, capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0 and result.stdout.strip():
            print(result.stdout.strip())
            found_runs = True

    if not found_runs:
        print("No recent assembly builds found.")

    return 0


@assembly_group.command("rebuild", help="Dispatch rebuild workflows for every project registered in the assembly. Fetches the projects.json manifest from the assembly repository, then sends a separate GitHub Actions repository dispatch event for each registered project to trigger a full documentation rebuild.")
def _cmd_assembly_rebuild():
    """Trigger rebuild for all projects in the assembly."""
    import base64
    import subprocess

    from selfblog.assembly import assembly_rebuild
    from selfdoc_core.config import load_config

    config = load_config(".")
    if config is None:
        print("Error: No selfdoc.json found. Run 'selfdoc init' first.", file=sys.stderr)
        sys.exit(1)

    assembly_config = config.get("assembly") or {}
    repo = assembly_config.get("repo")
    if not repo:
        print("Error: assembly.repo not configured in selfdoc.json.", file=sys.stderr)
        sys.exit(1)

    # Fetch projects.json from the assembly repo
    result = subprocess.run(
        ["gh", "api", f"/repos/{repo}/contents/projects.json",
         "--jq", ".content"],
        check=False, capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        print(f"Error: Failed to fetch projects.json from {repo}: {result.stderr.strip()}", file=sys.stderr)
        sys.exit(1)

    content_b64 = result.stdout.strip()
    try:
        projects = json.loads(base64.b64decode(content_b64).decode())
    except (json.JSONDecodeError, Exception) as e:
        print(f"Error: Failed to parse projects.json: {e}", file=sys.stderr)
        sys.exit(1)

    if not projects:
        print("No projects configured in assembly.")
        return 0

    dispatches = assembly_rebuild(repo, projects)

    for dispatch in dispatches:
        slug = dispatch["payload"]["client_payload"]["slug"]
        print(f"Dispatching rebuild for {slug}...")
        payload = json.dumps(dispatch["payload"])
        result = subprocess.run(
            ["gh", "api", "--method", "POST", dispatch["endpoint"], "--input", "-"],
            input=payload, check=False, capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            print(f"  Warning: Failed to dispatch for {slug}: {result.stderr.strip()}", file=sys.stderr)
        else:
            print(f"  Dispatched rebuild for {slug}.")

    print(f"Dispatched {len(dispatches)} rebuild(s).")
    return 0


@assembly_group.command("redirects", help="Generate a Cloudflare Pages _redirects file for this project that redirects standalone documentation URLs to the corresponding paths on the unified assembly site. Requires a project slug and assembly base URL as inputs, prints the redirect rules to stdout.")
@strictcli.flag("slug", type=str, help="Project slug used as the URL path segment in the assembly site structure")
@strictcli.flag("docs_base", type=str, help="Base URL of the assembly documentation site used for generating redirect targets")
def _cmd_assembly_redirects(slug="", docs_base=""):
    """Print the _redirects file content for redirecting to the assembly site."""
    from selfblog.assembly import generate_redirects_file

    if not slug:
        print("Error: --slug is required.", file=sys.stderr)
        sys.exit(1)
    if not docs_base:
        print("Error: --docs-base is required.", file=sys.stderr)
        sys.exit(1)

    content = generate_redirects_file(slug, docs_base)
    print(content, end="")
    return 0


@assembly_group.command("generate-shared", help="Generate 6 shared cross-project elements for the assembled documentation site. Reads per-project manifest JSON files, merges post overlays, and produces a homepage, blog index, navigation JSON, RSS feed, XML sitemap, and security headers file in the site output directory.")
@strictcli.flag("site-dir", type=str, help="Path to the combined site output directory where shared HTML files are written")
@strictcli.flag("manifests-dir", type=str, help="Path to the directory containing per-project manifest JSON files for the assembly")
@strictcli.flag("docs-base", type=str, help="Base URL of the assembled documentation site (e.g. 'https://docs.smmh.dev'). Used for generating absolute URLs in feeds, sitemaps, and page links. Defaults to empty string for root-relative URLs.")
@strictcli.flag("portfolio-file", type=str, help="Path to a portfolio HTML file to use as the site root index.html. When provided and the file exists, the project listing moves to /projects/index.html.")
def _cmd_assembly_generate_shared(site_dir="", manifests_dir="", docs_base="", portfolio_file=""):
    """Generate shared elements (homepage, blog index, nav, feed, sitemap, headers)."""
    from selfblog.shared import (
        generate_blog_index,
        generate_homepage,
        generate_nav_json,
        generate_sitemap,
        generate_unified_feed,
        wrap_shared_page,
    )
    from selfdoc_core.manifest import manifest_compat
    from selfdoc_core.utils import atomic_write

    if not site_dir:
        print("Error: --site-dir is required.", file=sys.stderr)
        sys.exit(1)
    if not manifests_dir:
        print("Error: --manifests-dir is required.", file=sys.stderr)
        sys.exit(1)

    # Load all manifest JSON files, separating base manifests from
    # post overlays.  Post overlays are files matching *-posts.json;
    # they carry updated post lists that replace the base manifest's
    # posts for the same project slug.
    #
    # Revisions sidecars (*-revisions.json) are skipped here -- they
    # are not manifests and are not consumed by generate-shared.
    base_manifests = []
    post_overlays = []
    if os.path.isdir(manifests_dir):
        for fname in sorted(os.listdir(manifests_dir)):
            if not fname.endswith(".json"):
                continue
            if fname.endswith("-revisions.json"):
                continue
            fpath = os.path.join(manifests_dir, fname)
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
            # Run through manifest_compat to validate and normalize.
            # Post overlays also have slug/posts structure that
            # manifest_compat can handle (unknown keys are ignored).
            manifest_compat(data, source=fpath)
            if fname.endswith("-posts.json"):
                post_overlays.append(data)
            else:
                base_manifests.append(data)

    # Apply post overlays: replace base manifest posts with overlay posts
    if post_overlays:
        base_by_slug = {m["slug"]: m for m in base_manifests}
        for overlay in post_overlays:
            slug = overlay.get("slug", "")
            if slug in base_by_slug:
                base_by_slug[slug]["posts"] = overlay.get("posts", [])

    manifests = base_manifests

    # Strip trailing slash from docs_base for consistent URL construction
    docs_base = docs_base.rstrip("/")

    # Generate fragments and wrap
    homepage_fragment = generate_homepage(manifests, docs_base)
    blog_fragment = generate_blog_index(manifests, docs_base)
    nav_json = generate_nav_json(manifests)
    feed_xml = generate_unified_feed(manifests, docs_base)
    sitemap_xml = generate_sitemap(manifests, docs_base)

    homepage_html = wrap_shared_page("Projects", homepage_fragment)
    blog_html = wrap_shared_page("Blog", blog_fragment)

    headers_content = (
        "/*\n"
        "  X-Frame-Options: DENY\n"
        "  X-Content-Type-Options: nosniff\n"
        "  Referrer-Policy: strict-origin-when-cross-origin\n"
    )

    # Write outputs
    written = []

    # When a portfolio file is provided, it becomes the root index.html
    # and the project listing moves to /projects/index.html
    if portfolio_file and os.path.isfile(portfolio_file):
        with open(portfolio_file, "r", encoding="utf-8") as f:
            portfolio_html = f.read()
        index_path = os.path.join(site_dir, "index.html")
        os.makedirs(os.path.dirname(index_path) or site_dir, exist_ok=True)
        atomic_write(index_path, portfolio_html)
        written.append(index_path)

        projects_dir = os.path.join(site_dir, "projects")
        os.makedirs(projects_dir, exist_ok=True)
        projects_path = os.path.join(projects_dir, "index.html")
        atomic_write(projects_path, homepage_html)
        written.append(projects_path)
    else:
        index_path = os.path.join(site_dir, "index.html")
        os.makedirs(os.path.dirname(index_path) or site_dir, exist_ok=True)
        atomic_write(index_path, homepage_html)
        written.append(index_path)

    blog_dir = os.path.join(site_dir, "blog")
    os.makedirs(blog_dir, exist_ok=True)
    blog_path = os.path.join(blog_dir, "index.html")
    atomic_write(blog_path, blog_html)
    written.append(blog_path)

    nav_path = os.path.join(site_dir, "nav.json")
    atomic_write(nav_path, nav_json)
    written.append(nav_path)

    feed_path = os.path.join(site_dir, "feed.xml")
    atomic_write(feed_path, feed_xml)
    written.append(feed_path)

    sitemap_path = os.path.join(site_dir, "sitemap.xml")
    atomic_write(sitemap_path, sitemap_xml)
    written.append(sitemap_path)

    headers_path = os.path.join(site_dir, "_headers")
    atomic_write(headers_path, headers_content)
    written.append(headers_path)

    worker_js_content = """\
export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.hostname === "blog.smmh.dev") {
      const target = new URL("/blog" + url.pathname, "https://smmh.dev");
      target.search = url.search;
      return Response.redirect(target.toString(), 301);
    }
    return env.ASSETS.fetch(request);
  }
}
"""
    worker_js_path = os.path.join(site_dir, "_worker.js")
    atomic_write(worker_js_path, worker_js_content)
    written.append(worker_js_path)

    print(f"Generated {len(written)} shared file(s):")
    for path in written:
        print(f"  {path}")

    return 0


# -- check command -----------------------------------------------------------


@app.command("check", help="Check blog posts and unified multi-project documentation. For unified docs-site projects, runs the full documentation check across every constituent project plus the docs-site's own content; otherwise validates blog posts (POST001-POST005).")
@strictcli.flag("ignore", type=str, default="", help="Comma-separated lint codes to suppress (e.g., SEO007,SEO008)")
@strictcli.flag("auto-commit", type=bool, default=True, help="Automatically commit updated content hash tracking files to git after checking")
@strictcli.flag("dry-run", type=bool, default=False, help="Report staleness without writing hash files to disk")
def _cmd_check(ignore="", auto_commit=True, dry_run=False):
    """Check unified projects and blog posts."""
    from selfdoc_core.config import load_config

    from selfblog.check import check_posts, check_unified

    config = load_config(".")
    if config is None:
        print("Error: No selfdoc.json found. Run 'selfdoc init' first.", file=sys.stderr)
        sys.exit(1)

    # Build combined ignore set from CLI --ignore and config lint_ignore
    ignore_codes = set()
    if ignore:
        ignore_codes.update(
            code.strip() for code in ignore.split(",") if code.strip()
        )
    ignore_codes.update(config.get("lint_ignore", []))

    if config.get("unified"):
        # The unified check aggregates selfdoc's per-project docs checks;
        # the result/print helpers live in selfdoc.check.
        try:
            from selfdoc.check import filter_lints, print_results
        except ImportError:
            print(
                "Error: selfblog unified checks require the selfdoc "
                "package. Install it with 'pip install selfdoc'.",
                file=sys.stderr,
            )
            sys.exit(1)

        try:
            result = check_unified(".", config=config, dry_run=dry_run)
        except RuntimeError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)

        if auto_commit and not dry_run:
            from selfdoc_core.git import auto_commit as _auto_commit
            _auto_commit(
                [".selfdoc/hashes/hashes.json"],
                "selfdoc: update content hashes",
                ".",
            )

        result.lints = filter_lints(result.lints, ignore_codes)

        has_failures = any(
            dr.status == "FAILED" for dr in result.directive_results
        )
        has_errors = any(lint.severity == "error" for lint in result.lints)

        # Coverage threshold check (uses documented count, not referenced)
        coverage_below_threshold = False
        if result.coverage is not None and result.coverage.total_public > 0:
            if result.coverage.documented < result.coverage.total_public:
                coverage_below_threshold = True

        print_results(result)

        if coverage_below_threshold:
            cov = result.coverage
            print(
                f"Coverage: {cov.documented}/{cov.total_public} symbols"
                " documented. All public symbols must be documented."
            )

        if has_failures or has_errors or coverage_below_threshold:
            sys.exit(1)
        return 0

    # Non-unified project: run the post checks (POST001-POST005)
    lints = [
        lint for lint in check_posts(config, ".")
        if lint.code not in ignore_codes
    ]
    for lint in lints:
        line_part = f":{lint.line}" if lint.line is not None else ""
        print(
            f"{lint.severity}: [{lint.code}] "
            f"{lint.file}{line_part} - {lint.message}"
        )
    if any(lint.severity == "error" for lint in lints):
        sys.exit(1)
    print("Post checks passed.")
    return 0


# -- build command -----------------------------------------------------------


@app.command("build", help="Build blog posts for the documentation site")
@strictcli.flag("target", type=str, default="posts", help="Build target: 'posts' for posts-only build")
@strictcli.flag("drafts", type=bool, default=False, help="Include posts marked as draft in the build output")
@strictcli.flag("auto-commit", type=bool, default=True, help="Automatically commit updated content hash tracking files to git after the build")
def _cmd_build(target="posts", drafts=False, auto_commit=True):
    """Build blog posts."""
    from selfdoc_core.build import build
    from selfdoc_core.config import load_config

    config = load_config(".")
    if config is None:
        print("Error: No selfdoc.json found. Run 'selfdoc init' first.", file=sys.stderr)
        sys.exit(1)

    if target != "posts":
        print(
            f"Error: selfblog build only supports --target posts. "
            f"For full builds, use 'selfdoc build'.",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        written = build(
            ".",
            include_drafts=drafts,
            target="posts",
        )
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    output_dir = config["output"] if config else "docs/_build/"

    if auto_commit:
        from selfdoc_core.git import auto_commit as _auto_commit
        _auto_commit(
            [".selfdoc/hashes/hashes.json"],
            "selfdoc: update content hashes",
            ".",
        )

    print(f"Built {len(written)} file(s) to {output_dir}")
    return 0


def run():
    """Parse arguments and dispatch to the appropriate subcommand."""
    app.run()
