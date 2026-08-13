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
from selfdoc_core import effects


app = strictcli.App(
    name="selfblog",
    version=__version__,
    help="Blog system for selfdoc-based documentation sites",
)

post_group = app.group("post", help="Manage blog posts and chronological content for the documentation site")
docs_group = app.group("docs", help="Publish this project's documentation to the unified assembly without a release")
assembly_group = app.group("assembly", help="Manage the unified multi-project documentation assembly and deployment")
editor_group = app.group("editor", help="Run and inspect the local authoring app for blog posts")


#: What a command can raise that is the *project's* fault rather than
#: selfblog's: an unusable config, a suppression list naming a code that is
#: unknown or not suppressible, a directive nothing answers, and the
#: RuntimeErrors the build and check raise for a defect they name. All print
#: one line and exit 1; a traceback is what selfblog owes for its own bugs.
def _user_errors():
    from selfdoc_core.config import ConfigError
    from selfdoc_core.directives import DirectiveError

    return (ConfigError, DirectiveError, RuntimeError)


def _fail(exc):
    """Print *exc* as a refusal and exit 1."""
    print(f"Error: {exc}", file=sys.stderr)
    sys.exit(1)


def _load_config_or_fail(dir_path="."):
    """Load the project config, or refuse cleanly."""
    from selfdoc_core.config import load_config

    try:
        return load_config(dir_path)
    except _user_errors() as exc:
        _fail(exc)


# -- post commands -----------------------------------------------------------


@post_group.command("new", help="Scaffold a new blog post markdown file with a date-prefixed filename and frontmatter template containing title, date, slug, tags, draft status, and project metadata. Creates the file in the configured posts directory and exits with an error if the file already exists.", effect="mutating")
@strictcli.flag("title", type=str, help="Title for the new blog post, used in frontmatter and filename generation")
@effects.handler
def _cmd_post_new(ctx, title=""):
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

    filepath = os.path.join(posts_dir, filename)

    if os.path.isfile(filepath):
        print(f"Error: Post file already exists: {filepath}", file=sys.stderr)
        sys.exit(1)

    effects.makedirs(posts_dir, exist_ok=True)

    content = (
        f"---\n"
        f"title: {title}\n"
        f"date: {today}\n"
        f"slug: {slug}\n"
        f"tags: []\n"
        f"draft: true\n"
        f"directives: false\n"
        f"---\n"
        f"\n"
    )

    effects.write_text(filepath, content)

    print(f"Created post: {filepath}")
    return 0


@post_group.command("list", help="List all discovered blog posts with date, title, slug, and draft status. Scans the configured posts directory for markdown files with frontmatter, parses their metadata, and prints a formatted summary showing each post's publication date, title, slug identifier, and whether it is marked as a draft.", effect="read_only")
@effects.handler
def _cmd_post_list(ctx):
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


@post_group.command("generate", help="Generate a blog post markdown file from structured release metadata. Takes version, bump type, description, changelog, and registry URLs as inputs, produces a frontmatter-bearing post with title, date, tags, and body content, and updates the project manifest with the new post entry.", effect="mutating")
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
@effects.handler
def _cmd_post_generate(
    ctx,
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
):
    """Generate a blog post from release metadata."""
    from selfdoc_core.config import load_config
    from selfdoc_core.manifest import generate_manifest, load_manifest
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
        # A generated release post is prose plus a changelog; nothing in it
        # is meant to be resolved.  The declaration is required on every
        # post, so the scaffold states it rather than leaving the author a
        # file its own discovery would refuse.
        "directives: false",
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

    # Write the post file.  Under --dry-run the writes below are recorded by
    # the effects chokepoint and rendered in the would-do log, which replaces
    # the command's old local --dry-run (a reserved framework name now).
    effects.makedirs(posts_dir, exist_ok=True)
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


@post_group.command("publish", help="Publish non-draft blog posts to the documentation assembly. Builds posts locally, pushes built HTML and manifest to the assembly repo via the Git Data API, then dispatches a shared-only workflow to regenerate cross-project elements.", effect="mutating",
    # Consequential: this is the moment locally-authored, previously-private
    # post content becomes publicly readable. Unlike `assembly push` and
    # `assembly rebuild`, which re-derive already-public docs from an
    # already-public tag, this one publishes something new, and a post
    # published by mistake cannot be unpublished from the reader's side.
    consequential=True,
    grants=[
        strictcli.Grant(
            "assembly-dispatch",
            "triggers a GitHub Actions workflow on the assembly repository, "
            "which rebuilds and republishes the live documentation site",
            strictcli.PROC_MUTATE,
        ),
    ],
)
@effects.handler
def _cmd_post_publish(ctx):
    """Publish blog posts to the assembly without a software release."""

    from selfblog.assembly import push_files_to_repo, split_build_output
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
        print("Error: assembly.repo not configured in selfdoc.json.", file=sys.stderr)
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

    # Read built HTML files and map to assembly paths. A post is site-level
    # -- `blog/<post-slug>/`, under no project slug -- and the listing page
    # the build renders for the project's own standalone site is dropped:
    # the assembled site's blog index lists every project's posts and is
    # written by the shared-only rebuild dispatched below.
    build_rels = {
        os.path.relpath(abs_path, output_dir).replace(os.sep, "/")
        for abs_path in written
    }
    files = {}
    produced = set()
    for build_rel, site_rel in split_build_output(build_rels, slug).items():
        with open(os.path.join(output_dir, *build_rel.split("/")),
                  "r", encoding="utf-8") as f:
            files[f"site/{site_rel}"] = f.read()
        produced.add(site_rel)

    # Read post-manifest and map to assembly path
    post_manifest_path = os.path.join(".selfdoc", "post-manifest.json")
    if os.path.isfile(post_manifest_path):
        with open(post_manifest_path, "r", encoding="utf-8") as f:
            files[f"manifests/{slug}-posts.json"] = f.read()

    # Include revisions sidecar if it exists
    if os.path.isfile(revisions_path):
        with open(revisions_path, "r", encoding="utf-8") as f:
            files[f"manifests/{slug}-revisions.json"] = f.read()

    # Record the posts this publish owns, in the same commit that carries
    # them: an unrecorded post is unclaimed, so nothing accounts for it,
    # another project's publish may overwrite it, and retirement leaves it
    # behind on the blog. This is the helper `docs publish` records through.
    delete_paths = []
    if produced:
        from selfblog.assembly import (
            load_remote_roster,
            refuse_foreign_post_overwrite,
            remote_post_claims,
            stage_published_record,
        )

        # The site-level blog is one namespace shared by every project, so a
        # post slug another project already claims is refused before anything
        # is written -- the same refusal the integrate graft makes, against
        # the records on the assembly instead of a local clone.
        try:
            roster = load_remote_roster(repo)
            refuse_foreign_post_overwrite(
                slug, produced, remote_post_claims(repo, slug, roster),
            )
        except RuntimeError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            sys.exit(1)

        delete_paths = stage_published_record(
            repo, slug, "posts", produced, files,
        )
    else:
        # The same protection the posts-scope integrate has: a build that
        # emitted no post pages is not an instruction to unpublish the posts
        # already on the site, so the record is left exactly as it is.
        print(
            f"posts publish for {slug!r}: the build produced no post pages, "
            f"so nothing was claimed and nothing was removed. Posts already "
            f"published stay.",
            file=sys.stderr,
        )

    # Push files to assembly repo via Git Data API
    push_files_to_repo(repo, files, f"posts: {slug}",
                       delete_paths=delete_paths)

    # Dispatch shared-only rebuild to regenerate cross-project elements
    dispatch_payload = json.dumps({
        "event_type": "project-updated",
        "client_payload": {"scope": "shared-only"},
    })
    result = effects.run(
        ["gh", "api", "--method", "POST",
         f"/repos/{repo}/dispatches", "--input", "-"],
        input=dispatch_payload, check=False, capture_output=True,
        text=True, timeout=30,
        resource=f"dispatch:{repo}",
        grant="assembly-dispatch",
    )
    if not effects.unsettled(result) and result.returncode != 0:
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


# -- docs commands -----------------------------------------------------------


@docs_group.command("publish", help="Publish this project's documentation to the assembly without a release. Builds the docs locally, pushes the built site, its manifest and its membership record into the assembly repo via the Git Data API -- deleting the pages this project published before and no longer produces -- then dispatches a shared-only workflow to regenerate cross-project elements.", effect="mutating",
    # Consequential for the same reason `post publish` is: locally-authored
    # content becomes publicly readable at the moment this runs, with no tag
    # and no release standing between the working tree and the live site. It
    # also deletes: a page this project published before and no longer builds
    # disappears for readers in the same commit.
    consequential=True,
    grants=[
        strictcli.Grant(
            "assembly-dispatch",
            "triggers a GitHub Actions workflow on the assembly repository, "
            "which rebuilds and republishes the live documentation site",
            strictcli.PROC_MUTATE,
        ),
    ],
)
@effects.handler
def _cmd_docs_publish(ctx):
    """Publish built documentation to the assembly without a software release."""
    from selfblog.assembly import build_source_project, publish_project_docs
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

    topology = config.get("topology") or {}
    slug = topology.get("slug")
    if not slug:
        print("Error: topology.slug not configured in selfdoc.json.", file=sys.stderr)
        sys.exit(1)

    version = config.get("version", "")
    if not version:
        from selfdoc_core.utils import detect_project_version
        version = detect_project_version(".", fallback="0.0.0")

    # The same build the deploy runs on a cloned checkout, run here on the
    # working tree. selfblog never imports selfdoc, so this shells out to it
    # exactly as the assembly's own integrate step does.
    try:
        build_source_project(".", "full")
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    output_dir = os.path.join(".", config["output"].rstrip("/"))
    if not os.path.isdir(output_dir):
        print(
            f"Error: the build produced no output at {output_dir}; there is "
            f"nothing to publish.",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        summary = publish_project_docs(
            repo, slug, output_dir,
            version=version,
            manifest_path=os.path.join(".selfdoc", "manifest.json"),
        )
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    # Dispatch a shared-only rebuild so the listing, feed, sitemap and search
    # index take account of what just changed.
    dispatch_payload = json.dumps({
        "event_type": "project-updated",
        "client_payload": {"scope": "shared-only"},
    })
    result = effects.run(
        ["gh", "api", "--method", "POST",
         f"/repos/{repo}/dispatches", "--input", "-"],
        input=dispatch_payload, check=False, capture_output=True,
        text=True, timeout=30,
        resource=f"dispatch:{repo}",
        grant="assembly-dispatch",
    )
    if not effects.unsettled(result) and result.returncode != 0:
        print(f"Error: Failed to dispatch shared rebuild: {result.stderr.strip()}", file=sys.stderr)
        sys.exit(1)

    deleted = len(summary["deleted"])
    print(
        f"Published {len(summary['published'])} documentation file(s) for "
        f"{slug} to {repo}"
        + (f", removing {deleted} page(s) it no longer builds" if deleted else "")
        + ". Shared elements will regenerate."
    )
    return 0


# -- assembly commands -------------------------------------------------------


@assembly_group.command("init", help="Create and initialize the assembly GitHub repository with workflow and configuration files. Creates a private GitHub repo, pushes initial files via the Contents API, creates a Cloudflare Pages project if credentials are available, and sets GitHub secrets for deployment authentication.", effect="mutating",
    # Consequential: every one of its three effects creates a NAMED external
    # resource that rerunning cannot un-create -- a GitHub repository under the
    # configured owner, a Cloudflare Pages project that claims its *.pages.dev
    # subdomain, and deployment credentials written into that repo's Actions
    # secrets. This is the highest-stakes command in either CLI.
    consequential=True,
    grants=[
        strictcli.Grant(
            "create-repo",
            "creates a new private GitHub repository under the configured "
            "owner; repository creation is not undone by rerunning the command",
            strictcli.PROC_MUTATE,
        ),
        strictcli.Grant(
            "create-pages-project",
            "creates a Cloudflare Pages project on the configured account, "
            "claiming its *.pages.dev subdomain",
            strictcli.PROC_MUTATE,
        ),
        strictcli.Grant(
            "set-secret",
            "writes Cloudflare deployment credentials into the assembly "
            "repository's GitHub Actions secrets",
            strictcli.PROC_MUTATE,
        ),
    ],
)
@effects.handler
def _cmd_assembly_init(ctx):
    """Create the assembly GitHub repo and push initial files."""
    import base64

    from selfblog.assembly import (
        assembly_init,
        check_pins_are_published,
        resolve_toolchain_pins,
    )
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

    pages_project = assembly_config.get("pages_project")
    if not pages_project:
        print(
            "Error: assembly.pages_project not configured in selfdoc.json.",
            file=sys.stderr,
        )
        sys.exit(1)

    topology = config.get("topology") or {}
    canonical_base = topology.get("docs_base")
    if not canonical_base:
        print(
            "Error: topology.docs_base not configured in selfdoc.json.",
            file=sys.stderr,
        )
        sys.exit(1)
    legacy_blog_host = topology.get("legacy_blog_host") or ""

    # The workflow init writes pins its toolchain exactly as the one
    # sync-workflow rewrites later, and refuses an unpublishable pin the
    # same way -- a fresh assembly must not start life with a deploy that
    # cannot install its own tools.
    try:
        pins = resolve_toolchain_pins()
        check_pins_are_published(pins)
    except (RuntimeError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    files = assembly_init(
        repo, pages_project, canonical_base, legacy_blog_host, pins,
    )

    # Create the private GitHub repo
    print(f"Creating repository {repo}...")
    result = effects.run(
        ["gh", "repo", "create", repo, "--private"],
        check=False, capture_output=True, text=True, timeout=30,
        resource=f"gh-repo:{repo}",
        grant="create-repo",
    )
    if not effects.unsettled(result) and result.returncode != 0:
        print(f"Error: Failed to create repository: {result.stderr.strip()}", file=sys.stderr)
        sys.exit(1)

    # Push initial files via GitHub Contents API
    for filepath, content in files.items():
        print(f"  Creating {filepath}...")
        encoded = base64.b64encode(content.encode()).decode()
        payload = json.dumps({"message": f"Initial: {filepath}", "content": encoded})
        result = effects.run(
            ["gh", "api", "--method", "PUT",
             f"/repos/{repo}/contents/{filepath}",
             "--input", "-"],
            input=payload, check=False, capture_output=True, text=True, timeout=30,
            resource=f"gh-contents:{repo}/{filepath}",
        )
        if not effects.unsettled(result) and result.returncode != 0:
            print(f"Error: Failed to create {filepath}: {result.stderr.strip()}", file=sys.stderr)
            sys.exit(1)

    # Create CF Pages project
    cf_account = os.environ.get("CF_ACCOUNT_ID") or os.environ.get("CLOUDFLARE_ACCOUNT_ID")
    cf_token = os.environ.get("CF_PAGES_API_TOKEN") or os.environ.get("CLOUDFLARE_API_TOKEN")
    if cf_account and cf_token:
        env = os.environ.copy()
        env["CLOUDFLARE_ACCOUNT_ID"] = cf_account
        env["CLOUDFLARE_API_TOKEN"] = cf_token
        result = effects.run(
            ["npx", "wrangler", "pages", "project", "create", pages_project, "--production-branch", "main"],
            env=env, check=False, capture_output=True, text=True, timeout=60,
            resource=f"cf-pages-project:{pages_project}",
            grant="create-pages-project",
        )
        if effects.unsettled(result):
            pass
        elif result.returncode == 0:
            print(f"Created CF Pages project: {pages_project}")
        else:
            print(f"Warning: CF Pages project creation failed: {result.stderr.strip()}", file=sys.stderr)
    else:
        print("Warning: CF_ACCOUNT_ID/CF_PAGES_API_TOKEN not set, skipping CF Pages project creation.", file=sys.stderr)

    # Set GitHub secrets for CF credentials
    if cf_account:
        result = effects.run(
            ["gh", "secret", "set", "CF_ACCOUNT_ID", "--repo", repo, "--body", cf_account],
            check=False, capture_output=True, text=True, timeout=30,
            resource=f"gh-secret:{repo}/CF_ACCOUNT_ID",
            grant="set-secret",
        )
        if effects.unsettled(result):
            pass
        elif result.returncode == 0:
            print("Set GitHub secret: CF_ACCOUNT_ID")
        else:
            print(f"Warning: Failed to set CF_ACCOUNT_ID secret: {result.stderr.strip()}", file=sys.stderr)

    if cf_token:
        result = effects.run(
            ["gh", "secret", "set", "CF_PAGES_API_TOKEN", "--repo", repo, "--body", cf_token],
            check=False, capture_output=True, text=True, timeout=30,
            resource=f"gh-secret:{repo}/CF_PAGES_API_TOKEN",
            grant="set-secret",
        )
        if effects.unsettled(result):
            pass
        elif result.returncode == 0:
            print("Set GitHub secret: CF_PAGES_API_TOKEN")
        else:
            print(f"Warning: Failed to set CF_PAGES_API_TOKEN secret: {result.stderr.strip()}", file=sys.stderr)

    print(f"Assembly repository initialized: {repo}")
    return 0


@assembly_group.command("push", help="Dispatch a GitHub Actions workflow to rebuild this project in the documentation assembly. Detects the source repository, resolves the latest git tag as the version reference, and sends a repository dispatch event to the assembly repo with the project slug, version, and commit SHA.", effect="mutating",
    # Deliberately NOT consequential, though its grant escapes the process:
    # the dispatch re-derives already-public documentation from an
    # already-public git tag. Nothing new becomes public, nothing published is
    # destroyed, and rerunning converges on the same site. It is also the
    # routine post-release refresh, so a prompt here would be the reflex the
    # confirm protocol exists to avoid. strictcli's
    # `consequential-grant-agreement` check warns about this pairing by design;
    # the warning is expected and this comment is the answer to it.
    grants=[
        strictcli.Grant(
            "assembly-dispatch",
            "triggers a GitHub Actions workflow on the assembly repository, "
            "which rebuilds and republishes the live documentation site",
            strictcli.PROC_MUTATE,
        ),
    ],
)
@effects.handler
def _cmd_assembly_push(ctx):
    """Dispatch an assembly rebuild for the current project."""

    from selfblog.assembly import (
        assembly_push,
        check_version_is_declared,
        list_repo_tags,
        resolve_project_tag,
    )
    from selfdoc_core.config import load_config

    config = load_config(".")
    if config is None:
        print("Error: No selfdoc.json found. Run 'selfdoc init' first.", file=sys.stderr)
        sys.exit(1)

    # Resolve assembly repo from config
    assembly_config = config.get("assembly") or {}
    repo = assembly_config.get("repo")
    if not repo:
        print("Error: assembly.repo not configured in selfdoc.json.", file=sys.stderr)
        sys.exit(1)

    topology = config.get("topology") or {}
    slug = topology.get("slug")
    if not slug:
        print("Error: topology.slug not configured in selfdoc.json.", file=sys.stderr)
        sys.exit(1)

    # Detect source repo
    result = effects.run(
        ["gh", "repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner"],
        check=False, capture_output=True, text=True, timeout=15,
        read=True,
    )
    if result.returncode != 0:
        print(f"Error: Failed to detect source repository: {result.stderr.strip()}", file=sys.stderr)
        sys.exit(1)
    source_repo = result.stdout.strip()

    # Detect version
    version = config.get("version", "")
    if not version:
        from selfdoc_core.utils import detect_project_version
        version = detect_project_version(".", fallback="0.0.0")

    # The assembly builds selfdoc.json's newest declared version, so a
    # 'versions' array that omits the version being dispatched would
    # publish something else under this version's name.
    try:
        check_version_is_declared(config, version)
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    # Resolve the tag that names THIS project's version. Never the
    # repository's newest tag: in a repo that releases more than one
    # thing, that is a sibling's tag and the assembly builds the wrong
    # source tree under this project's slug.
    try:
        ref = resolve_project_tag(list_repo_tags("."), version)
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    dispatch = assembly_push(repo, source_repo, slug, version, ref)

    # Execute the dispatch
    payload = json.dumps(dispatch["payload"])
    result = effects.run(
        ["gh", "api", "--method", "POST", dispatch["endpoint"], "--input", "-"],
        input=payload, check=False, capture_output=True, text=True, timeout=30,
        resource=f"dispatch:{repo}",
        grant="assembly-dispatch",
    )
    if not effects.unsettled(result) and result.returncode != 0:
        print(f"Error: Failed to dispatch rebuild: {result.stderr.strip()}", file=sys.stderr)
        sys.exit(1)

    print(f"Dispatched assembly rebuild for {slug} v{version} (ref: {ref})")
    return 0


@assembly_group.command("status", help="Show the status of recent assembly build workflow runs on GitHub. Queries the assembly repository for recent workflow runs using the GitHub CLI and displays their status, conclusion, and timing information for monitoring deployment progress.", effect="read_only")
@effects.handler
def _cmd_assembly_status(ctx):
    """Show recent assembly build status."""

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
        result = effects.run(
            cmd, check=False, capture_output=True, text=True, timeout=30,
            read=True,
        )
        if result.returncode == 0 and result.stdout.strip():
            print(result.stdout.strip())
            found_runs = True

    if not found_runs:
        print("No recent assembly builds found.")

    return 0


@assembly_group.command("rebuild", help="Dispatch rebuild workflows for every project registered in the assembly. Fetches the projects.json manifest from the assembly repository, then sends a separate GitHub Actions repository dispatch event for each registered project to trigger a full documentation rebuild.", effect="mutating",
    # Deliberately NOT consequential, for the same reason as `assembly push`
    # and despite the wider blast radius: it re-derives every registered
    # project's already-public docs from their already-public tags. The scale
    # is larger; the character of the change is not. See the note on
    # `assembly push` regarding the `consequential-grant-agreement` warning.
    grants=[
        strictcli.Grant(
            "assembly-dispatch",
            "triggers a GitHub Actions workflow on the assembly repository, "
            "which rebuilds and republishes the live documentation site",
            strictcli.PROC_MUTATE,
        ),
    ],
)
@effects.handler
def _cmd_assembly_rebuild(ctx):
    """Trigger rebuild for all projects in the assembly."""
    from selfblog.assembly import PROJECTS_PATH, assembly_rebuild, fetch_remote_text
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

    # The membership record comes through the same reader every other remote
    # read uses, so an absent record and a failed read are told apart here
    # too: neither is an assembly with no projects, and both stop the rebuild.
    try:
        raw = fetch_remote_text(
            repo, PROJECTS_PATH,
            operation=f"dispatch a rebuild for every project on {repo}",
        )
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    try:
        projects = json.loads(raw)
    except json.JSONDecodeError as exc:
        # The only thing left to go wrong: the record was read successfully
        # and is not a JSON document. Every other failure -- the read itself,
        # the base64 decode -- is already a RemoteReadError above.
        print(f"Error: {repo}:{PROJECTS_PATH} is not valid JSON: {exc}",
              file=sys.stderr)
        sys.exit(1)

    if not projects:
        print("No projects configured in assembly.")
        return 0

    dispatches = assembly_rebuild(repo, projects)

    for dispatch in dispatches:
        slug = dispatch["payload"]["client_payload"]["slug"]
        print(f"Dispatching rebuild for {slug}...")
        payload = json.dumps(dispatch["payload"])
        result = effects.run(
            ["gh", "api", "--method", "POST", dispatch["endpoint"], "--input", "-"],
            input=payload, check=False, capture_output=True, text=True, timeout=30,
            resource=f"dispatch:{repo}/{slug}",
            grant="assembly-dispatch",
        )
        if effects.unsettled(result):
            pass
        elif result.returncode != 0:
            print(f"  Warning: Failed to dispatch for {slug}: {result.stderr.strip()}", file=sys.stderr)
        else:
            print(f"  Dispatched rebuild for {slug}.")

    print(f"Dispatched {len(dispatches)} rebuild(s).")
    return 0


@assembly_group.command("retire", help="Retire a project from the unified assembly: remove its [[project]] block from the roster and, in the same commit, delete its whole site subtree, all of its manifests and its membership record, then dispatch a shared-only rebuild so the listing, feed, sitemap and search index stop naming it.", effect="mutating",
    # Consequential: it deletes a project's published section from the live
    # site. Nothing else in either CLI removes public content, and rerunning
    # cannot restore it -- the pages are gone from the branch the site serves.
    consequential=True,
    grants=[
        strictcli.Grant(
            "assembly-commit",
            "deletes a project's published documentation from the assembly "
            "repository's deploy branch through the GitHub Git Data API",
            strictcli.PROC_MUTATE,
        ),
        strictcli.Grant(
            "assembly-dispatch",
            "triggers a GitHub Actions workflow on the assembly repository, "
            "which rebuilds and republishes the live documentation site",
            strictcli.PROC_MUTATE,
        ),
    ],
)
@strictcli.flag("slug", type=str, default="", help="Slug of the project to retire; it is removed from the roster and every path it owns in the assembly is deleted")
@effects.handler
def _cmd_assembly_retire(ctx, slug=""):
    """Remove a project from the assembly's roster and published tree."""
    from selfblog.assembly import retire_project
    from selfdoc_core.config import load_config

    if not slug:
        print("Error: --slug is required.", file=sys.stderr)
        sys.exit(1)

    config = load_config(".")
    if config is None:
        print("Error: No selfdoc.json found. Run 'selfdoc init' first.", file=sys.stderr)
        sys.exit(1)

    assembly_config = config.get("assembly") or {}
    repo = assembly_config.get("repo")
    if not repo:
        print("Error: assembly.repo not configured in selfdoc.json.", file=sys.stderr)
        sys.exit(1)

    try:
        summary = retire_project(repo, slug)
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    dispatch_payload = json.dumps({
        "event_type": "project-updated",
        "client_payload": {"scope": "shared-only"},
    })
    result = effects.run(
        ["gh", "api", "--method", "POST",
         f"/repos/{repo}/dispatches", "--input", "-"],
        input=dispatch_payload, check=False, capture_output=True,
        text=True, timeout=30,
        resource=f"dispatch:{repo}",
        grant="assembly-dispatch",
    )
    if not effects.unsettled(result) and result.returncode != 0:
        print(f"Error: Failed to dispatch shared rebuild: {result.stderr.strip()}", file=sys.stderr)
        sys.exit(1)

    print(
        f"Retired {slug} from {repo}: {len(summary['deleted'])} path(s) "
        f"deleted. Remaining projects: "
        f"{', '.join(summary['remaining']) or '(none)'}. Shared elements will "
        f"regenerate."
    )
    return 0


@assembly_group.command("redirects", help="Generate a Cloudflare Pages _redirects file for this project that redirects standalone documentation URLs to the corresponding paths on the unified assembly site. Requires a project slug and assembly base URL as inputs, prints the redirect rules to stdout.", effect="read_only")
@strictcli.flag("slug", type=str, help="Project slug used as the URL path segment in the assembly site structure")
@strictcli.flag("docs-base", type=str, help="Base URL of the assembly documentation site used for generating redirect targets")
@effects.handler
def _cmd_assembly_redirects(ctx, slug="", docs_base=""):
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


@assembly_group.command("generate-shared", help="Generate the shared cross-project elements for the assembled documentation site. Reads per-project manifest JSON files, merges post overlays, and produces a homepage, blog index, navigation JSON, RSS feed, XML sitemap, robots.txt, a site-wide llms.txt linking to each project's own, a root 404 page, a security headers file and the redirect worker in the site output directory.", effect="mutating")
@strictcli.flag("site-dir", type=str, help="Path to the combined site output directory where shared HTML files are written")
@strictcli.flag("manifests-dir", type=str, help="Path to the directory containing per-project manifest JSON files for the assembly")
@strictcli.flag("docs-base", type=str, help="Base URL the Atom feed's entries are written against. Only the feed reads it: every entry there is an absolute URL by protocol. Nothing a reader clicks does -- the generated listing, the blog index and the 404 address the site relative to their own page, so they resolve under any mount. The sitemap does not read it either: it is generated from --canonical-base whatever this says.")
@strictcli.flag("canonical-base", type=str, help="Absolute canonical base URL of the assembly site, from topology.docs_base (e.g. 'https://docs.smmh.dev'). Required: it is the one hostname that serves content and every other host 301s onto it, it is the base of every sitemap entry, and it targets the rel=canonical links on the homepage and blog index, so it cannot be root-relative like --docs-base.")
@strictcli.flag("legacy-blog-host", type=str, help="Hostname of a retired blog subdomain (e.g. 'blog.smmh.dev') to 301 onto the canonical blog URL. Empty when no such subdomain exists.")
@strictcli.flag("home-slug", type=str, default="", help="The roster's home project: the one project served at the site root. Its pages are left out of the generated listing and out of nav, and every site-level directive region it emitted is re-rendered from the current manifests. Empty means the tree carries no home project (which the deploy path never does -- the roster requires one).")
@effects.handler
def _cmd_assembly_generate_shared(ctx, site_dir="", manifests_dir="", docs_base="", canonical_base="", legacy_blog_host="", home_slug=""):
    """Generate shared elements (homepage, blog index, nav, feed, sitemap, headers)."""
    from selfblog.assembly import generate_shared_files

    if not site_dir:
        print("Error: --site-dir is required.", file=sys.stderr)
        sys.exit(1)
    if not manifests_dir:
        print("Error: --manifests-dir is required.", file=sys.stderr)
        sys.exit(1)
    if not canonical_base:
        print(
            "Error: --canonical-base is required (set topology.docs_base in "
            "selfdoc.json and regenerate the assembly workflow).",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        written = generate_shared_files(
            site_dir, manifests_dir, canonical_base,
            docs_base=docs_base,
            legacy_blog_host=legacy_blog_host,
            home_slug=home_slug,
        )
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    print(f"Generated {len(written)} shared file(s):")
    for path in written:
        print(f"  {path}")

    return 0


@assembly_group.command("integrate", help="Integrate one dispatched project into the assembly repository checkout and push the result. Builds the cloned source project, replaces its subtree under site/, refreshes its manifest and membership record, regenerates the shared cross-project elements, rebuilds the search index, then commits and pushes with a re-sync retry loop so concurrent deploys converge instead of clobbering each other. This is the whole body of the generated deploy workflow.", effect="mutating",
    # Deliberately NOT consequential: it runs unattended inside the assembly
    # repo's own CI, re-deriving already-public docs from an already-public
    # tag. A prompt here would hang the deploy forever. Same reasoning as
    # `assembly push`; strictcli's `consequential-grant-agreement` check warns
    # about the pairing by design and this comment is the answer to it.
    #
    # It cannot honestly preview itself, and says so at parse time: every
    # step after the first reads what the step before it wrote, so a
    # recorded run has nothing to hand the steps that follow.
    dry_run_supported=False,
    dry_run_unsupported_reason=(
        "'assembly integrate' cannot be previewed: every step after the "
        "first reads what the step before it wrote -- the shared generator "
        "reads the manifests the graft just copied, the search index reads "
        "the pages it just wrote, and the commit reads the tree all of them "
        "produced. A recorded run writes none of that, so the preview would "
        "stop at the first effect and misrepresent everything after it. To "
        "see what an integration would produce, use 'assembly preview'."
    ),
    grants=[
        strictcli.Grant(
            "assembly-commit",
            "pushes a commit to the assembly repository's deploy branch, "
            "which is the content the live documentation site serves",
            strictcli.PROC_MUTATE,
        ),
    ],
)
@strictcli.flag("slug", type=str, default="", help="Project slug being integrated; the site subtree is site/<slug>/. Required unless --scope is 'shared-only'.")
@strictcli.flag("version", type=str, default="", help="Version of the project being integrated, recorded in projects.json and the commit message")
@strictcli.flag("ref", type=str, default="", help="Git ref (tag) the source project was cloned at, recorded in projects.json")
@strictcli.flag("source-repo", type=str, default="", help="Source project repository (owner/name), recorded in projects.json")
@strictcli.flag("scope", type=str, default="", help="What this dispatch replaces: 'full' (the whole project subtree plus this project's posts), 'posts' (only this project's posts, at the site-level site/blog/<post-slug>/), or 'shared-only' (no project files, just the cross-project elements). Empty means 'full'.")
@strictcli.flag("canonical-base", type=str, default="", help="Absolute canonical base URL of the assembly site, from topology.docs_base. Required: it targets the redirect worker and the rel=canonical links.")
@strictcli.flag("legacy-blog-host", type=str, default="", help="Hostname of a retired blog subdomain to 301 onto the canonical blog URL. Empty when no such subdomain exists.")
@strictcli.flag("assembly-dir", type=str, default=".", help="Path to the assembly repository checkout being updated")
@strictcli.flag("source-dir", type=str, default="", help="Path to the cloned source project. Defaults to <assembly-dir>/source/<slug>, where the deploy workflow clones it.")
@strictcli.flag("branch", type=str, default="main", help="Assembly repository branch the deploy commits and pushes to")
@strictcli.flag("attempts", type=int, default=3, help="How many times to re-sync with the remote and retry the push before failing")
@effects.handler
def _cmd_assembly_integrate(ctx, slug="", version="", ref="", source_repo="",
                            scope="", canonical_base="", legacy_blog_host="",
                            assembly_dir=".",
                            source_dir="", branch="main", attempts=3):
    """Integrate a dispatched project into the assembly and push."""
    from selfblog.assembly import integrate_project

    if not canonical_base:
        print(
            "Error: --canonical-base is required (set topology.docs_base in "
            "selfdoc.json and regenerate the assembly workflow with "
            "'selfblog assembly sync-workflow').",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        summary = integrate_project(
            slug=slug,
            version=version,
            ref=ref,
            source_repo=source_repo,
            scope=scope,
            canonical_base=canonical_base,
            assembly_dir=assembly_dir,
            source_dir=source_dir,
            legacy_blog_host=legacy_blog_host,
            branch=branch,
            attempts=attempts,
        )
    except (ValueError, RuntimeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    if summary["committed"]:
        print(
            f"Integrated {summary['scope']} scope for "
            f"{summary['slug'] or 'shared elements'} "
            f"(attempt {summary['attempt']}, "
            f"{len(summary['shared'])} shared file(s))."
        )
    else:
        print(
            f"Nothing to commit for {summary['slug'] or 'shared elements'} "
            f"({summary['scope']} scope); the assembly is already current."
        )
    return 0


@assembly_group.command("verify", help="Assert every property a built assembly tree has to have before it is deployed: that the roster, the site subtrees and the manifests name the same projects, that each manifest's pages and posts were actually emitted, that the shared cross-project artifacts exist and parse, that every internal reference, sitemap entry, feed link and cross-project link resolves, that every page has a title and a canonical, and that no unresolved directive or per-project routing file survived. The deploy runs this itself before it pushes; this command is how you run the same assertions by hand against a checkout.", effect="read_only")
@strictcli.flag("assembly-dir", type=str, default=".", help="Path to the assembly repository checkout to verify")
@strictcli.flag("canonical-base", type=str, default="", help="Absolute canonical base URL of the assembly site, from topology.docs_base. Required: it is what tells this site's absolute URLs from everybody else's, and without it half the assertions would pass by not looking.")
@effects.handler
def _cmd_assembly_verify(ctx, assembly_dir=".", canonical_base=""):
    """Verify a built assembly tree and report every offender."""
    from selfblog.verify import CHECKS, verify_assembly

    if not canonical_base:
        print(
            "Error: --canonical-base is required (set topology.docs_base in "
            "selfdoc.json).",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        report = verify_assembly(assembly_dir, canonical_base=canonical_base)
    except (ValueError, RuntimeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    for check, reason in report.skipped:
        print(f"NOT CHECKED: {check} -- {reason}", file=sys.stderr)

    if not report.ok:
        print(report.error_text(), file=sys.stderr)
        sys.exit(1)

    print(
        f"The assembled tree at {assembly_dir} passed "
        f"{len(report.ran)} of {len(CHECKS)} check(s)."
    )
    return 0


@assembly_group.command("preview", help="Assemble every named local checkout into a preview tree and serve it on loopback. Builds each project with the toolchain running this command, grafts the output exactly as the deploy does -- the home project at the site root, everybody else under their slug -- writes the roster, membership record and manifests the assembly keeps, generates the shared cross-project files and the site chrome, rebuilds the search index, runs the real pre-deploy verification and prints its report, then serves the result with a working 404. Nothing leaves the machine and nothing is published: this is the look-before-you-ship step.", effect="mutating",
    # Not consequential: everything it writes is a local build tree at a
    # path the caller named, and nothing reaches the world.
    #
    # It cannot preview itself, and says so at parse time. The command's
    # whole output is a tree on disk plus a server over it; recording the
    # writes instead of performing them would leave nothing to look at, and
    # every step after the first reads what the step before it wrote.
    dry_run_supported=False,
    dry_run_unsupported_reason=(
        "'assembly preview' exists to produce output you look at: a built "
        "site tree and a server over it. A recorded run would write no tree, "
        "and every step after the build reads what the step before it wrote "
        "-- the graft reads the build, the shared generator reads the grafted "
        "manifests, the index and the verification read the pages. Run it "
        "without --dry-run; it publishes nothing."
    ),
)
@strictcli.flag("repo", type=str, repeatable=True, unique=True, help="Path to a project checkout to include, served under the slug its selfdoc.json declares. Repeat once per project. The home project is named by --home instead and must not be repeated here.")
@strictcli.flag("home", type=str, help="Path to the home project's checkout: the one project served at the site root rather than under a slug. Required -- a site needs a front page, and there is no default.")
@strictcli.flag("out", type=str, help="Directory the preview tree is written to. Required. Refused when it sits inside a git working tree at a path git does not ignore, because a generated site dropped into a checkout is untracked noise in every session sharing it.")
@strictcli.flag("port", type=int, help="Port to bind on 127.0.0.1. Required and has no default: which port a long-running local server occupies is a decision the caller states rather than inherits.")
@strictcli.flag("canonical-base", type=str, help="Absolute canonical base URL of the assembly site, from topology.docs_base (e.g. 'https://smmh.dev'). Required, and it is the DEPLOYED base rather than the loopback one: the preview shows the pages with the canonicals, sitemap entries and cross-project links they would ship with, and verifies those.")
@strictcli.flag("legacy-blog-host", type=str, default="", help="Hostname of a retired blog subdomain the generated worker 301s onto the canonical blog URL, passed through to the shared generator exactly as the deploy passes it. Empty when no such subdomain exists.")
@strictcli.flag("build", type=bool, help="Whether to build each checkout before grafting it. Required with no default: --build is the honest preview of what would ship, --no-build re-assembles whatever each checkout already has in docs/_build, which is what a second look after one edit wants and the only way to iterate without rebuilding every project. Choosing is the point -- a preview of a stale build tree is a preview of nothing in particular.")
@strictcli.flag("theme", type=str, default="", help="Build every checkout under this theme instead of the one its selfdoc.json declares, for this preview only. Empty -- the default -- leaves every project on its configured theme, which is what a deploy does. This exists to judge a theme on the real pages: the same site, every project flipped at once, without editing a config anywhere. Validated against the theme registry, and refused with --no-build, because a theme is baked into build output and re-grafting an existing tree cannot restyle it.")
@effects.handler
def _cmd_assembly_preview(ctx, repo=(), home="", out="", port=0,
                          canonical_base="", legacy_blog_host="", build=True,
                          theme=""):
    """Build every named checkout into a preview tree and serve it."""
    from selfblog.preview import (
        HOST,
        preview_assembly,
        render_report,
        serve_preview,
    )

    if not home:
        print("Error: --home is required.", file=sys.stderr)
        sys.exit(1)
    if not out:
        print("Error: --out is required.", file=sys.stderr)
        sys.exit(1)
    if not port:
        print("Error: --port is required.", file=sys.stderr)
        sys.exit(1)
    if not canonical_base:
        print(
            "Error: --canonical-base is required (the assembly's "
            "topology.docs_base, e.g. 'https://smmh.dev').",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        summary = preview_assembly(
            home_dir=home,
            project_dirs=list(repo),
            out_dir=out,
            canonical_base=canonical_base,
            legacy_blog_host=legacy_blog_host,
            build=build,
            theme=theme,
        )
    except (ValueError, RuntimeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    # The report first, and loudly. A preview serves a tree that failed
    # verification on purpose -- that is the state worth looking at -- so
    # the only thing standing between a broken tree and a wrong conclusion
    # is that the reader was told.
    print(render_report(summary["report"], out_dir=summary["out_dir"]))
    print(
        f"Preview of {len(summary['slugs'])} project(s) "
        f"(home: {summary['home']}) at {summary['site_dir']}"
    )

    def _ready(bound_port):
        print(f"Preview: http://{HOST}:{bound_port}/  (Ctrl-C to stop)")
        sys.stdout.flush()

    return serve_preview(summary["site_dir"], port, on_ready=_ready)


@assembly_group.command("sync-workflow", help="Regenerate the assembly repository's deploy workflow from this project's configuration and push it. The deployed workflow is a generated artifact like any other: without this it stays frozen at whatever the template said when 'assembly init' ran. Pushes only when the content actually differs.", effect="mutating",
    # Deliberately NOT consequential: it rewrites one tool-owned generated
    # file to match the generator, and rerunning converges. See the note on
    # `assembly push`.
    grants=[
        strictcli.Grant(
            "assembly-commit",
            "commits the regenerated deploy workflow to the assembly "
            "repository through the GitHub Git Data API",
            strictcli.PROC_MUTATE,
        ),
    ],
)
@strictcli.flag("pin-version", type=str, default="", help="selfblog version the regenerated workflow pins its toolchain install to. Defaults to the running selfblog's version, which is what the release path wants: the workflow names the selfblog that generated it.")
@strictcli.flag("pin-selfdoc", type=str, default="", help="selfdoc version the regenerated workflow pins its toolchain install to. Defaults to the selfdoc installed in this environment; selfdoc missing here is a hard error, never an unpinned install.")
@strictcli.flag("pin-pagefind", type=str, default="", help="pagefind version the regenerated workflow pins its toolchain install to. Defaults to PyPI's current release: pagefind is a CI-only tool nothing here installs, so there is no local version to read.")
@effects.handler
def _cmd_assembly_sync_workflow(ctx, pin_version="", pin_selfdoc="", pin_pagefind=""):
    """Regenerate and push the assembly repo's deploy workflow."""
    from selfblog.assembly import (
        WORKFLOW_PATH,
        check_pins_are_published,
        generate_workflow_yaml,
        push_files_to_repo,
        resolve_toolchain_pins,
    )
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

    pages_project = assembly_config.get("pages_project")
    if not pages_project:
        print(
            "Error: assembly.pages_project not configured in selfdoc.json.",
            file=sys.stderr,
        )
        sys.exit(1)

    topology = config.get("topology") or {}
    canonical_base = topology.get("docs_base")
    if not canonical_base:
        print(
            "Error: topology.docs_base not configured in selfdoc.json.",
            file=sys.stderr,
        )
        sys.exit(1)

    # Resolve every pin, then refuse any that the registry cannot serve --
    # before a single byte is written. A pin that resolves nowhere would
    # otherwise fail at the next dispatch, inside the assembly repo's CI.
    try:
        pins = resolve_toolchain_pins(
            selfblog_version=pin_version,
            selfdoc_version=pin_selfdoc,
            pagefind_version=pin_pagefind,
        )
        check_pins_are_published(pins)
    except (RuntimeError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    content = generate_workflow_yaml(
        pages_project,
        canonical_base,
        topology.get("legacy_blog_host") or "",
        pins,
    )

    label = (f"selfblog {pins.selfblog}, selfdoc {pins.selfdoc}, "
             f"pagefind {pins.pagefind}")
    try:
        result = push_files_to_repo(
            repo,
            {WORKFLOW_PATH: content},
            f"assembly: sync deploy workflow ({label})",
        )
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    if result.changed:
        print(f"Synced {WORKFLOW_PATH} on {repo} ({label}, commit {result.sha}).")
    else:
        print(
            f"{WORKFLOW_PATH} on {repo} is already current "
            f"({label}); nothing pushed."
        )
    return 0


# -- editor commands ---------------------------------------------------------


def _load_registry_or_fail(registry):
    """Read the editor registry, or refuse with the file's own message."""
    from selfblog.editor_registry import RegistryError, load_registry

    try:
        return load_registry(registry or None)
    except RegistryError as exc:
        _fail(exc)


@editor_group.command("list-repos", help="List every repository the editor registry declares, with its kind and where it points. Reads the hand-written registry TOML, validates every entry in full, and prints one line per entry -- a local entry's working tree, or a remote entry's repository, ref and whether it declares that rendering runs against a checkout.", effect="read_only")
@strictcli.flag("registry", type=str, default="", help="Path to the editor registry TOML. Defaults to the machine-local registry at ~/Projects/ark/selfblog-registry.toml.")
@effects.handler
def _cmd_editor_list_repos(ctx, registry=""):
    """Enumerate the registry's entries."""
    parsed = _load_registry_or_fail(registry)

    if not parsed.entries:
        print(f"No repositories in {parsed.path}.")
        return 0

    for entry in parsed:
        if entry.kind == "local":
            print(f"{entry.name}  local   {entry.path}")
        else:
            rendered = "render" if entry.render else "no-render"
            print(
                f"{entry.name}  remote  {entry.repo}@{entry.ref} "
                f"[{rendered}, not served yet]"
            )

    print(f"\n{len(parsed)} repository(ies) in {parsed.path}.")
    return 0


@editor_group.command("serve", help="Run the local authoring app: a browser UI over the registry's repositories, with the tinymoon editor component on the left and a live preview on the right. The preview is the publish renderer over the unsaved buffer, so what you approve is byte-for-byte what publishing produces, and rendering a preview writes nothing. Saving writes the buffer into the repository's working tree. Binds 127.0.0.1 only.", effect="mutating",
    # Not consequential: nothing here reaches the world, and the only writes
    # are the ones the author asks for by pressing save. A confirmation prompt
    # at launch would be answering for edits that have not been made yet.
    #
    # It also cannot honestly preview, and says so at parse time. A refusal
    # is the only correct answer rather than a recorded run, because the
    # saves happen on request threads that carry none of the dispatch
    # context -- they would execute for real under a preview that claimed
    # to be recording them.
    dry_run_supported=False,
    dry_run_unsupported_reason=(
        "'editor serve' is an interactive server: its writes are the saves "
        "you make at the keyboard while it runs, so at launch there is "
        "nothing to record. Worse, those saves happen on request threads "
        "that carry no preview context, so they would execute for real. Run "
        "it without --dry-run, and preview a save by not pressing save."
    ),
)
@strictcli.flag("port", type=int, help="Port to bind on 127.0.0.1. Required and has no default: the editor writes working trees and answers without authentication, so which port it occupies is a decision the caller states rather than inherits.")
@strictcli.flag("registry", type=str, default="", help="Path to the editor registry TOML. Defaults to the machine-local registry at ~/Projects/ark/selfblog-registry.toml.")
@strictcli.flag("tinymoon-assets", type=str, default="", help="Path to a tinymoon checkout's 'assets' directory. Empty means the installed tinymoon package. The editor tier (js/editor.js, js/completion.js, css/editor.css) is newer than the released package, so a checkout is currently the only complete source.")
@effects.handler
def _cmd_editor_serve(ctx, port=0, registry="", tinymoon_assets=""):
    """Serve the authoring app on loopback."""
    from selfblog.editor_assets import AssetsError, resolve_tinymoon_assets
    from selfblog.editor_server import HOST, EditorState, serve

    parsed = _load_registry_or_fail(registry)

    try:
        assets_dir, assets_source = resolve_tinymoon_assets(tinymoon_assets)
    except AssetsError as exc:
        _fail(exc)

    state = EditorState(parsed, assets_dir)

    print(f"Registry: {parsed.path} ({len(parsed)} repository(ies))")
    print(f"tinymoon assets: {assets_source}")

    def _ready(bound_port):
        print(f"Editor: http://{HOST}:{bound_port}/  (Ctrl-C to stop)")

    return serve(state, port, on_ready=_ready)


# -- check command -----------------------------------------------------------


@app.command("check", help="Check blog posts and unified multi-project documentation. For unified docs-site projects, runs the full documentation check across every constituent project plus the docs-site's own content; otherwise validates blog posts (POST001-POST005).", effect="mutating")
@strictcli.flag("ignore", type=str, default="", help="Comma-separated lint codes to suppress (e.g., SEO007,SEO008)")
@strictcli.flag("auto-commit", type=bool, default=True, help="Automatically commit updated content hash tracking files to git after checking")
@effects.handler
def _cmd_check(ctx, ignore="", auto_commit=True):
    """Check unified projects and blog posts."""
    from selfdoc_core.lints import (
        DEFAULT_COVERAGE_THRESHOLD,
        LintSuppressionError,
        check_exit_code,
        coverage_below_threshold,
        parse_ignore_codes,
    )

    from selfblog.check import check_posts, check_unified

    # Validated before any work is done: a mistyped code suppresses nothing,
    # and an error-severity code is not suppressible at all.
    try:
        ignore_codes = parse_ignore_codes(ignore)
    except LintSuppressionError as exc:
        _fail(exc)

    config = _load_config_or_fail()
    if config is None:
        print("Error: No selfdoc.json found. Run 'selfdoc init' first.", file=sys.stderr)
        sys.exit(1)

    # The config's own lint_ignore was validated at load.
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
            # No dry_run= is threaded through: under --dry-run the hash
            # write is RECORDED by the effects chokepoint rather than
            # performed, which preserves the old behavior and makes the
            # preview honest about the write a real run would do.
            result = check_unified(".", config=config)
        except RuntimeError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)

        if auto_commit:
            from selfdoc_core.git import auto_commit as _auto_commit
            _auto_commit(
                [".selfdoc/hashes/hashes.json"],
                "selfdoc: update content hashes",
                ".",
            )

        result.lints = filter_lints(result.lints, ignore_codes)

        # The verdict rules live in selfdoc_core.lints -- one implementation
        # for every entry point.  This path used to compare documented
        # against total_public directly, which silently demanded 100%
        # coverage and disagreed with 'selfdoc check' on any project that
        # lowered coverage_threshold.
        exit_code = check_exit_code(
            result.lints,
            directive_results=result.directive_results,
            coverage=result.coverage,
            config=config,
        )
        below_threshold = coverage_below_threshold(result.coverage, config)

        print_results(result)

        if below_threshold:
            cov = result.coverage
            threshold = config.get(
                "coverage_threshold", DEFAULT_COVERAGE_THRESHOLD,
            )
            print(
                f"Coverage: {cov.documented}/{cov.total_public} symbols"
                f" documented. Threshold is {threshold * 100:.0f}%."
            )

        if exit_code != 0:
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
    # Reduced verdict: posts-only runs resolve no directives and measure no
    # coverage, so only the lints reach the shared rules.
    if check_exit_code(lints) != 0:
        sys.exit(1)
    print("Post checks passed.")
    return 0


# -- build command -----------------------------------------------------------


@app.command("build", help="Build blog posts, the unified documentation site, or the home project", effect="mutating")
@strictcli.flag("target", type=str, default="posts", help="Build target: 'posts' for posts-only build, 'unified' for unified multi-project site, 'home' for the assembly's home project (the one served at the site root, whose pages carry site-level directives)")
@strictcli.flag("drafts", type=bool, default=False, help="Include posts marked as draft in the build output")
@strictcli.flag("auto-commit", type=bool, default=True, help="Automatically commit updated content hash tracking files to git after the build")
@strictcli.flag("site-manifests", type=str, default="", help="Path to the assembly's manifests directory. Required by --target home: the home project's front page renders the curated listing with each project's live version and the recent posts across the whole site, and only the assembly's manifests carry those.")
@strictcli.flag("theme", type=str, default="", help="Theme name that overrides the one selfdoc.json declares, for this build only (e.g. 'tinymoon'). Empty means the config decides. Nothing is written back to selfdoc.json")
@effects.handler
def _cmd_build(ctx, target="posts", drafts=False, auto_commit=True,
               site_manifests="", theme=""):
    """Build blog posts, the unified site, or the home project."""
    config = _load_config_or_fail()
    if config is None:
        print("Error: No selfdoc.json found. Run 'selfdoc init' first.", file=sys.stderr)
        sys.exit(1)

    if target == "home":
        from selfblog.sitedirectives import build_home_project

        try:
            written = build_home_project(
                ".", config, site_manifests=site_manifests,
                include_drafts=drafts, theme=theme,
            )
        except _user_errors() as e:
            _fail(e)

        print(f"Built {len(written)} file(s) (home)")
        return 0

    if target == "unified":
        from selfblog.unified import build_unified

        try:
            written = build_unified(
                dir_path=".", include_drafts=drafts, theme=theme,
            )
        except _user_errors() as e:
            _fail(e)

        print(f"Built {len(written)} file(s) (unified)")
        return 0

    if target == "posts":
        from selfdoc_core.build import build

        try:
            written = build(
                ".",
                include_drafts=drafts,
                target="posts",
                theme=theme,
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

    print(
        f"Error: unknown build target '{target}'. "
        f"Valid targets: 'posts', 'unified', 'home'.",
        file=sys.stderr,
    )
    sys.exit(1)


def run():
    """Parse arguments and dispatch to the appropriate subcommand."""
    app.run()
