"""CLI interface for selfdoc."""

import datetime
import http.server
import json
import os
import sys
import threading

import strictcli

from selfdoc._version import __version__


app = strictcli.App(
    name="selfdoc",
    version=__version__,
    help="Code-aware static site generator with directive-based content extraction",
)

post_group = app.group("post", help="Manage blog posts and chronological content for the documentation site")
assembly_group = app.group("assembly", help="Manage the unified multi-project documentation assembly and deployment")


@post_group.command("new", help="Scaffold a new blog post markdown file with a date-prefixed filename and frontmatter template containing title, date, slug, tags, draft status, and project metadata. Creates the file in the configured posts directory and exits with an error if the file already exists.")
@strictcli.flag("title", type=str, help="Title for the new blog post, used in frontmatter and filename generation")
def _cmd_post_new(title=""):
    """Create a new blog post file in the posts directory."""
    from selfdoc.config import load_config
    from selfdoc.manifest import _to_kebab

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
    from selfdoc.config import load_config
    from selfdoc.posts import discover_posts

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
    from selfdoc.config import load_config
    from selfdoc.manifest import _to_kebab, generate_manifest, load_manifest
    from selfdoc.utils import atomic_write

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
        from selfdoc.docs import resolve_all_docs
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

    from selfdoc.assembly import push_files_to_repo
    from selfdoc.build import _build_posts_only
    from selfdoc.config import load_config
    from selfdoc.posts import discover_posts

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

    print(f"Published {len(non_draft_posts)} post(s) to assembly. Shared elements will regenerate.")
    return 0


def _detect_source_entries(language):
    """Detect source entries for a given language.

    Returns a list of {"path": ..., "language": ...} dicts suitable
    for the ``source`` field in selfdoc.json.
    """
    if language == "python":
        paths = []
        for candidate in ("src", "lib"):
            if os.path.isdir(candidate):
                paths.append(f"{candidate}/")
                break
        if not paths:
            for entry in sorted(os.listdir(".")):
                init_path = os.path.join(entry, "__init__.py")
                if os.path.isdir(entry) and os.path.isfile(init_path):
                    paths.append(f"{entry}/")
                    break
        paths = paths or ["."]
    elif language == "go":
        paths = []
        for candidate in ("pkg", "internal", "cmd"):
            if os.path.isdir(candidate):
                paths.append(f"{candidate}/")
        paths = paths or ["."]
    elif language == "typescript":
        paths = []
        for candidate in ("src", "lib"):
            if os.path.isdir(candidate):
                paths.append(f"{candidate}/")
                break
        paths = paths or ["."]
    else:
        paths = ["."]

    return [{"path": p, "language": language} for p in paths]


def _detect_main_module():
    """Detect the main module name for the starter template."""
    # For Python: look for a top-level package
    for entry in sorted(os.listdir(".")):
        init_path = os.path.join(entry, "__init__.py")
        if os.path.isdir(entry) and os.path.isfile(init_path):
            if not entry.startswith(".") and entry != "tests":
                return entry
    # For other languages, use the project directory name
    return os.path.basename(os.path.abspath("."))


@app.command("init", help="Initialize selfdoc configuration and starter docs template")
@strictcli.flag("auto-commit", type=bool, default=True, help="Automatically commit the generated selfdoc.json and docs/index.md template files to git")
def _cmd_init(auto_commit=True):
    """Initialize selfdoc in the current project."""
    from selfdoc.extractors import detect_languages

    if os.path.isfile("selfdoc.json"):
        print("selfdoc.json already exists. Aborting.")
        sys.exit(1)

    detected = detect_languages(".")
    if not detected:
        print(
            "Could not detect project language. "
            "Supported: pyproject.toml (Python), go.mod (Go), "
            "tsconfig.json/package.json (TypeScript/JavaScript)"
        )
        sys.exit(1)

    source_entries = []
    for entry in detected:
        source_entries.extend(_detect_source_entries(entry["language"]))

    # Use the first detected language for the starter template
    primary_language = detected[0]["language"]
    detected_languages = [e["language"] for e in detected]

    project_name = os.path.basename(os.path.abspath("."))
    main_module = _detect_main_module()

    config = {
        "source": source_entries,
        "docs": "docs/",
        "output": "docs/_build/",
    }

    # Write selfdoc.json atomically
    config_json = json.dumps(config, indent=2) + "\n"
    tmp_path = "selfdoc.json.tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        f.write(config_json)
    os.replace(tmp_path, "selfdoc.json")

    # Create docs/ directory
    os.makedirs("docs", exist_ok=True)

    # Create starter index.md
    index_path = os.path.join("docs", "index.md")
    if not os.path.isfile(index_path):
        today = datetime.date.today().isoformat()
        starter = (
            f"---\n"
            f"title: {project_name}\n"
            f"description: Documentation for {project_name}\n"
            f"date: {today}\n"
            f"---\n"
            f"\n"
            f"# {project_name}\n"
            f"\n"
            f"Welcome to the {project_name} documentation.\n"
            f"\n"
            f"## API Reference\n"
            f"\n"
            f':-: ref path="{main_module}" lang="{primary_language}"\n'
        )
        with open(index_path, "w", encoding="utf-8") as f:
            f.write(starter)

    source_path_strs = [e["path"] for e in source_entries]
    langs_str = ", ".join(detected_languages)
    print(f"Initialized selfdoc for {langs_str} project '{project_name}'")
    print("  Created: selfdoc.json")
    print("  Created: docs/index.md")
    print(f"  Source:  {', '.join(source_path_strs)}")
    print("\nRun 'selfdoc build' to generate documentation.")

    if auto_commit:
        from selfdoc.git import auto_commit as _auto_commit
        _auto_commit(
            ["selfdoc.json", "docs/index.md"], "selfdoc init", os.getcwd(),
        )

    return 0


@app.command("build", help="Build the documentation site from templates and source code")
@strictcli.flag("auto-commit", type=bool, default=True, help="Automatically commit updated content hash tracking files to git after the build")
@strictcli.flag("locale", type=str, default="", help="Build only the specified locale instead of all (e.g., 'en')")
@strictcli.flag("version", type=str, default="", help="Build only the specified version instead of all (e.g., '1.0.0')")
@strictcli.flag("drafts", type=bool, default=False, help="Include posts marked as draft in the build output alongside published posts")
@strictcli.flag("target", type=str, default="", help="Build target: 'posts' for posts-only build, empty for full build")
def _cmd_build(auto_commit=True, locale="", version="", drafts=False, target=""):
    """Build the documentation site."""
    from selfdoc.config import load_config

    config = load_config(".")

    # Detect unified config and dispatch accordingly
    if config and config.get("unified"):
        from selfdoc.unified import build_unified

        try:
            written = build_unified(".", config=config, include_drafts=drafts)
        except RuntimeError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        from selfdoc.build import build

        try:
            written = build(
                ".",
                version_filter=version or None,
                locale_filter=locale or None,
                include_drafts=drafts,
                target=target,
            )
        except RuntimeError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)

    from selfdoc.check import check_docs, filter_lints

    output_dir = config["output"] if config else "docs/_build/"

    if auto_commit:
        from selfdoc.git import auto_commit as _auto_commit
        _auto_commit(
            [".selfdoc/hashes/hashes.json"],
            "selfdoc: update content hashes",
            ".",
        )

    print(f"Built {len(written)} file(s) to {output_dir}")

    # Build ignore set from config
    ignore_codes = set()
    if config:
        ignore_codes.update(config.get("lint_ignore", []))

    # Run lint checks after build completes
    check_result = check_docs(".")
    lints = filter_lints(check_result.lints, ignore_codes)
    warn_count = 0
    error_count = 0
    for lint in lints:
        line_part = f":{lint.line}" if lint.line is not None else ""
        print(
            f"{lint.severity}: [{lint.code}] "
            f"{lint.file}{line_part} - {lint.message}"
        )
        if lint.severity == "warning":
            warn_count += 1
        elif lint.severity == "error":
            error_count += 1

    if warn_count > 0:
        print(f"{warn_count} SEO warning(s) found.")
    if error_count > 0:
        print(f"{error_count} error(s) found.")
        sys.exit(1)
    return 0


@app.command("serve", help="Serve the documentation site locally with live reload")
@strictcli.flag("port", short="p", type=int, default=8000, help="HTTP port number to serve on (default: 8000, e.g., 3000)")
@strictcli.flag("drafts", type=bool, default=False, help="Rebuild the site with draft posts included before starting the local server")
def _cmd_serve(port=8000, drafts=False):
    """Serve the documentation site locally with SSE-based live reload."""
    from selfdoc.config import load_config

    config = load_config(".")
    if config is None:
        print("Error: No selfdoc.json found. Run 'selfdoc init' first.", file=sys.stderr)
        sys.exit(1)

    if drafts:
        if config.get("unified"):
            from selfdoc.unified import build_unified
            try:
                build_unified(".", config=config, include_drafts=True)
            except RuntimeError as e:
                print(f"Error: {e}", file=sys.stderr)
                sys.exit(1)
        else:
            from selfdoc.build import build
            try:
                build(".", include_drafts=True)
            except RuntimeError as e:
                print(f"Error: {e}", file=sys.stderr)
                sys.exit(1)

    output_dir = config["output"].rstrip("/")
    if not os.path.isdir(output_dir):
        print(
            f"Error: Output directory '{output_dir}' not found. "
            "Run 'selfdoc build' first.",
            file=sys.stderr,
        )
        sys.exit(1)

    # JS snippet injected into HTML responses to enable live reload
    _RELOAD_SCRIPT = (
        b"\n<script>"
        b"const es = new EventSource('/__reload');"
        b"es.onmessage = () => location.reload();"
        b"</script>\n"
    )

    # Shared state for SSE
    sse_clients = []  # list of wfile objects (socket files)
    sse_lock = threading.Lock()

    class LiveReloadHandler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=output_dir, **kw)

        def log_message(self, format, *log_args):
            # Quieter logging
            pass

        def do_GET(self):
            if self.path == "/__reload":
                self._handle_sse()
            else:
                super().do_GET()

        def _handle_sse(self):
            """Hold the connection open as an SSE stream."""
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.end_headers()

            with sse_lock:
                sse_clients.append(self.wfile)
            try:
                # Block until the server shuts down or connection breaks.
                # The watcher thread sends data by writing to wfile directly.
                while not _shutdown_flag.is_set():
                    _shutdown_flag.wait(timeout=1.0)
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass
            finally:
                with sse_lock:
                    if self.wfile in sse_clients:
                        sse_clients.remove(self.wfile)

        def end_headers(self):
            """Inject live-reload script into HTML responses."""
            super().end_headers()

        def copyfile(self, source, outputfile):
            """Override copyfile to inject reload script into HTML."""
            # Check if this is an HTML response by inspecting headers
            for header, value in self._headers_buffer[0:20] if hasattr(self, '_headers_buffer') else []:
                pass  # can't easily inspect after send
            # Instead, read content and check if it looks like HTML
            # We use a simpler approach: check the path
            if self.path.endswith((".html", ".htm", "/")) or self.path == "/":
                data = source.read()
                # Inject before </body> if present, else append
                lower = data.lower()
                pos = lower.rfind(b"</body>")
                if pos != -1:
                    data = data[:pos] + _RELOAD_SCRIPT + data[pos:]
                else:
                    data += _RELOAD_SCRIPT
                outputfile.write(data)
            else:
                super().copyfile(source, outputfile)

    _shutdown_flag = threading.Event()

    def _snapshot_mtimes(directory):
        """Return a dict of {filepath: mtime} for all files under directory."""
        mtimes = {}
        for root, _dirs, files in os.walk(directory):
            for fname in files:
                fpath = os.path.join(root, fname)
                try:
                    mtimes[fpath] = os.stat(fpath).st_mtime
                except OSError:
                    pass
        return mtimes

    def _watcher():
        """Background thread: poll file mtimes and notify SSE clients."""
        prev = _snapshot_mtimes(output_dir)
        while not _shutdown_flag.is_set():
            _shutdown_flag.wait(timeout=0.5)
            if _shutdown_flag.is_set():
                break
            current = _snapshot_mtimes(output_dir)
            if current != prev:
                prev = current
                # Send SSE event to all connected clients
                msg = b"data: reload\n\n"
                with sse_lock:
                    dead = []
                    for wfile in sse_clients:
                        try:
                            wfile.write(msg)
                            wfile.flush()
                        except (BrokenPipeError, ConnectionResetError, OSError):
                            dead.append(wfile)
                    for d in dead:
                        sse_clients.remove(d)

    watcher_thread = threading.Thread(target=_watcher, daemon=True)
    watcher_thread.start()

    server = http.server.HTTPServer(("", port), LiveReloadHandler)
    print(f"Serving docs at http://localhost:{port}/")
    print("Live reload enabled")
    print("Press Ctrl+C to stop.")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
        _shutdown_flag.set()
        server.shutdown()
    return 0


@app.command("deploy", help="Deploy the built documentation site to the configured provider")
def _cmd_deploy():
    """Deploy the documentation site."""
    from selfdoc.config import load_config
    from selfdoc.deploy import (
        DeployError,
        deploy_cloudflare_pages,
        deploy_github_pages,
    )

    config = load_config(".")
    if config is None:
        print("Error: No selfdoc.json found. Run 'selfdoc init' first.", file=sys.stderr)
        sys.exit(1)

    output_dir = config["output"].rstrip("/")
    if not os.path.isdir(output_dir):
        print(
            f"Error: Output directory '{output_dir}' not found. "
            "Run 'selfdoc build' first.",
            file=sys.stderr,
        )
        sys.exit(1)

    deploy_config = config.get("deploy")
    if not deploy_config:
        print(
            "Error: No 'deploy' section in selfdoc.json. "
            "Add a deploy provider configuration.",
            file=sys.stderr,
        )
        sys.exit(1)

    # Prefer version from selfdoc.json, fall back to project manifest
    from selfdoc.utils import detect_project_version
    version = config.get("version") or detect_project_version(".", fallback="0.0.0")

    provider = deploy_config["provider"]

    try:
        if provider == "cloudflare-pages":
            project_name = deploy_config["project"]
            deploy_cloudflare_pages(output_dir, project_name, version)
        elif provider == "github-pages":
            deploy_github_pages(output_dir, version)
        else:
            print(f"Error: Unknown deploy provider '{provider}'", file=sys.stderr)
            sys.exit(1)
    except DeployError as e:
        print(f"Deploy error: {e}", file=sys.stderr)
        sys.exit(1)
    return 0




@app.command("check", help="Check documentation coverage, directive resolution, and lint rules")
@strictcli.flag("ignore", type=str, default="", help="Comma-separated SEO codes to suppress (e.g., SEO007,SEO008)")
@strictcli.flag("format", type=str, default="text", choices=["text", "json"], help="Output format for check results: text (human) or json (machine)")
@strictcli.flag("auto-commit", type=bool, default=True, help="Automatically commit updated content hash tracking files to git after checking")
@strictcli.flag("dry-run", type=bool, default=False, help="Report staleness without writing hash files to disk")
def _cmd_check(ignore="", format="text", auto_commit=True, dry_run=False):
    """Check documentation coverage and consistency."""
    from selfdoc.check import check_docs, check_unified, filter_lints, print_results
    from selfdoc.config import load_config

    config = load_config(".")

    try:
        if config and config.get("unified"):
            result = check_unified(".", config=config, dry_run=dry_run)
        else:
            result = check_docs(".", dry_run=dry_run)
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    if auto_commit and not dry_run:
        from selfdoc.git import auto_commit as _auto_commit
        _auto_commit(
            [".selfdoc/hashes/hashes.json"],
            "selfdoc: update content hashes",
            ".",
        )

    # Build combined ignore set from CLI --ignore and config lint_ignore
    ignore_codes = set()
    if ignore:
        ignore_codes.update(
            code.strip() for code in ignore.split(",") if code.strip()
        )
    if config:
        ignore_codes.update(config.get("lint_ignore", []))

    # Filter lints
    result.lints = filter_lints(result.lints, ignore_codes)

    # Determine exit code before output
    has_failures = any(dr.status == "FAILED" for dr in result.directive_results)
    has_errors = any(lint.severity == "error" for lint in result.lints)

    # Coverage threshold check (uses documented count, not referenced)
    coverage_below_threshold = False
    if result.coverage is not None and result.coverage.total_public > 0:
        if result.coverage.documented < result.coverage.total_public:
            coverage_below_threshold = True

    exit_code = 1 if (
        has_failures
        or has_errors
        or coverage_below_threshold
    ) else 0

    if format == "json":
        output = {
            "directives": [
                {
                    "file": dr.file,
                    "line": dr.line,
                    "directive": dr.directive,
                    "status": dr.status,
                    "error": dr.error,
                }
                for dr in result.directive_results
            ],
            "coverage": None,
            "lints": [
                {
                    "file": lint.file,
                    "line": lint.line,
                    "code": lint.code,
                    "message": lint.message,
                    "severity": lint.severity,
                }
                for lint in result.lints
            ],
            "exit_code": exit_code,
        }
        if result.coverage is not None:
            cov = result.coverage
            output["coverage"] = {
                "total_public": cov.total_public,
                "referenced": cov.referenced,
                "documented": cov.documented,
                "referenced_symbols": cov.referenced_symbols,
                "documented_symbols": cov.documented_symbols,
                "unreferenced_symbols": cov.unreferenced_symbols,
            }
        print(json.dumps(output, indent=2))
    else:
        print_results(result)

    if coverage_below_threshold:
        cov = result.coverage
        print(
            f"Coverage: {cov.documented}/{cov.total_public} symbols documented."
            " All public symbols must be documented."
        )

    if exit_code != 0:
        sys.exit(1)
    return 0


@app.command("gen", help="Auto-generate documentation pages from project structure")
@strictcli.flag("auto-commit", type=bool, default=True, help="Automatically commit generated documentation pages and root files to git")
def _cmd_gen(auto_commit=True):
    """Auto-generate documentation pages from project structure."""
    from selfdoc.config import load_config
    from selfdoc.gen import generate_docs, generate_root_files

    config = load_config(".")
    if config is None:
        print("Error: No selfdoc.json found. Run 'selfdoc init' first.", file=sys.stderr)
        sys.exit(1)

    try:
        gen_result = generate_docs(config, base_dir=".")
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    # Generate root files (e.g. CLAUDE.md from docs/_CLAUDE.md)
    try:
        root_generated = generate_root_files(config, base_dir=".")
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    if root_generated:
        print(f"Generated {len(root_generated)} root file(s):")
        for path in root_generated:
            print(f"  {path}")

    docs_rel = config.get("docs", "docs/").rstrip("/")
    all_commit_files = []

    if gen_result.written:
        print(f"Generated {len(gen_result.written)} doc file(s):")
        for path in gen_result.written:
            print(f"  {path}")
        all_commit_files.extend(
            os.path.join(docs_rel, f) for f in gen_result.written
        )

    if gen_result.deleted:
        print(f"Deleted {len(gen_result.deleted)} stale doc file(s):")
        for path in gen_result.deleted:
            print(f"  {path}")
        all_commit_files.extend(
            os.path.join(docs_rel, f) for f in gen_result.deleted
        )

    all_commit_files.extend(root_generated)

    # Update content/description hashes so that a subsequent 'check' does
    # not report freshly-generated pages as stale.
    from selfdoc.docs import resolve_all_docs
    from selfdoc.staleness import update_hashes

    all_docs = resolve_all_docs(config, base_dir=".")
    locales = config.get("locales") or []
    if locales:
        locale_code = locales[0]["code"]
        prefixed = {f"{locale_code}/{rp}": val for rp, val in all_docs.items()}
        update_hashes(prefixed, ".")
    else:
        update_hashes(all_docs, ".")
    all_commit_files.append(".selfdoc/hashes/hashes.json")

    # Discover posts for manifest
    from selfdoc.posts import discover_posts

    posts_config = config.get("posts") or {}
    posts_dir = posts_config.get("dir", ".selfdoc/posts/")
    posts = discover_posts(posts_dir)
    posts_data = [
        {
            "path": p["path"],
            "title": p["title"],
            "date": p["date"],
            "slug": p["slug"],
            "tags": p["tags"],
        }
        for p in posts
        if not p.get("draft")
    ]

    # Generate manifest (.selfdoc/manifest.json)
    from selfdoc.manifest import generate_manifest

    generate_manifest(config, all_docs, posts_data=posts_data, dir_path=".")
    all_commit_files.append(".selfdoc/manifest.json")

    if all_commit_files and auto_commit:
        from selfdoc.git import auto_commit as _auto_commit
        _auto_commit(
            all_commit_files, "selfdoc gen: update generated docs", ".",
        )

    if not gen_result.written and not root_generated:
        print("No files generated.")
    return 0


@app.command("gen-data", help="Generate data files by running sandboxed scripts via bwrap")
@strictcli.flag("auto-commit", type=bool, default=True, help="Automatically commit the generated data output files to git after script execution")
def _cmd_gen_data(auto_commit=True):
    """Generate data files by running sandboxed scripts."""
    from selfdoc.config import load_config
    from selfdoc.gendata import GenDataError, generate_data

    config = load_config(".")
    if config is None:
        print("Error: No selfdoc.json found. Run 'selfdoc init' first.", file=sys.stderr)
        sys.exit(1)

    try:
        generated = generate_data(config, base_dir=".")
    except GenDataError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    if generated:
        print(f"Generated {len(generated)} data file(s):")
        for path in generated:
            print(f"  {path}")
        if auto_commit:
            from selfdoc.git import auto_commit as _auto_commit
            written_files = [
                os.path.relpath(p, ".") for p in generated
            ]
            _auto_commit(
                written_files,
                "selfdoc gen-data: update generated data",
                ".",
            )
    else:
        print("No gen-data scripts configured.")
    return 0


@assembly_group.command("init", help="Create and initialize the assembly GitHub repository with workflow and configuration files. Creates a private GitHub repo, pushes initial files via the Contents API, creates a Cloudflare Pages project if credentials are available, and sets GitHub secrets for deployment authentication.")
def _cmd_assembly_init():
    """Create the assembly GitHub repo and push initial files."""
    import base64
    import subprocess

    from selfdoc.assembly import assembly_init
    from selfdoc.config import load_config

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

    from selfdoc.assembly import assembly_push
    from selfdoc.config import load_config

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
        from selfdoc.utils import detect_project_version
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

    from selfdoc.assembly import assembly_status
    from selfdoc.config import load_config

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

    from selfdoc.assembly import assembly_rebuild
    from selfdoc.config import load_config

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
    from selfdoc.assembly import generate_redirects_file

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
def _cmd_assembly_generate_shared(site_dir="", manifests_dir="", docs_base=""):
    """Generate shared elements (homepage, blog index, nav, feed, sitemap, headers)."""
    from selfdoc.shared import (
        generate_blog_index,
        generate_homepage,
        generate_nav_json,
        generate_sitemap,
        generate_unified_feed,
        wrap_shared_page,
    )
    from selfdoc.utils import atomic_write

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
    base_manifests = []
    post_overlays = []
    if os.path.isdir(manifests_dir):
        for fname in sorted(os.listdir(manifests_dir)):
            if not fname.endswith(".json"):
                continue
            fpath = os.path.join(manifests_dir, fname)
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
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

    print(f"Generated {len(written)} shared file(s):")
    for path in written:
        print(f"  {path}")

    return 0


def run():
    """Parse arguments and dispatch to the appropriate subcommand."""
    app.run()
