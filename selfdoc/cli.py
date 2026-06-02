"""CLI interface for selfdoc."""

import datetime
import http.server
import json
import os
import sys
import threading

import strictcli

from selfdoc import __version__


app = strictcli.App(
    name="selfdoc",
    version=__version__,
    help="Code-aware static site generator with directive-based content extraction",
)


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
    elif language in ("typescript", "javascript"):
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


@app.command("init", help="Initialize selfdoc in the current project")
@strictcli.flag("no-commit", type=bool, help="Skip auto-committing changed files")
def _cmd_init(no_commit=False):
    """Initialize selfdoc in the current project."""
    from selfdoc.extractors import detect_language

    if os.path.isfile("selfdoc.json"):
        print("selfdoc.json already exists. Aborting.")
        sys.exit(1)

    language = detect_language(".")
    if language is None:
        print(
            "Could not detect project language. "
            "Supported: pyproject.toml (Python), go.mod (Go), "
            "tsconfig.json/package.json (TypeScript/JavaScript)"
        )
        sys.exit(1)
    source_entries = _detect_source_entries(language)

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
            f':-: ref path="{main_module}"\n'
        )
        with open(index_path, "w", encoding="utf-8") as f:
            f.write(starter)

    source_path_strs = [e["path"] for e in source_entries]
    print(f"Initialized selfdoc for {language} project '{project_name}'")
    print(f"  Created: selfdoc.json")
    print(f"  Created: docs/index.md")
    print(f"  Source:  {', '.join(source_path_strs)}")
    print(f"\nRun 'selfdoc build' to generate documentation.")

    if not no_commit:
        from selfdoc.git import auto_commit
        auto_commit(
            ["selfdoc.json", "docs/index.md"], "selfdoc init", os.getcwd(),
        )

    return 0


@app.command("build", help="Build the documentation site")
@strictcli.flag("no-commit", type=bool, help="Skip auto-committing changed files")
@strictcli.flag("locale", type=str, default="", help="Build only this locale (e.g., 'en')")
@strictcli.flag("version", type=str, default="", help="Build only this version (e.g., '1.0.0')")
def _cmd_build(no_commit=False, locale="", version=""):
    """Build the documentation site."""
    from selfdoc.config import load_config

    config = load_config(".")

    # Detect unified config and dispatch accordingly
    if config and config.get("unified"):
        from selfdoc.unified import build_unified

        try:
            written = build_unified(".", config=config)
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
            )
        except RuntimeError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)

    from selfdoc.check import check_docs, filter_lints

    output_dir = config["output"] if config else "docs/_build/"

    if not no_commit:
        from selfdoc.git import auto_commit
        auto_commit(
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


@app.command("serve", help="Serve the documentation site locally")
@strictcli.flag("port", short="p", type=int, default=8000, help="Port to serve on (default: 8000)")
def _cmd_serve(port=8000):
    """Serve the documentation site locally with SSE-based live reload."""
    from selfdoc.config import load_config

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

    # JS snippet injected into HTML responses to enable live reload
    _RELOAD_SCRIPT = (
        b"\n<script>"
        b"const es = new EventSource('/__reload');"
        b"es.onmessage = () => location.reload();"
        b"</script>\n"
    )

    # Shared state for SSE: a threading.Event that the watcher sets
    # when any file mtime changes, and a list of connected SSE wfiles.
    reload_event = threading.Event()
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
            content_type = None
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


@app.command("deploy", help="Deploy the documentation site")
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




@app.command("check", help="Check documentation coverage and consistency")
@strictcli.flag("ignore", type=str, default="", help="Comma-separated SEO codes to suppress (e.g., SEO007,SEO008)")
@strictcli.flag("format", type=str, default="text", choices=["text", "json"], help="Output format (default: text)")
@strictcli.flag("no-commit", type=bool, help="Skip auto-committing changed files")
@strictcli.flag("dry-run", type=bool, help="Report staleness without writing hashes")
def _cmd_check(ignore="", format="text", no_commit=False, dry_run=False):
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

    if not no_commit and not dry_run:
        from selfdoc.git import auto_commit
        auto_commit(
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
@strictcli.flag("no-commit", type=bool, help="Skip auto-committing changed files")
def _cmd_gen(no_commit=False):
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

    if all_commit_files and not no_commit:
        from selfdoc.git import auto_commit
        auto_commit(
            all_commit_files, "selfdoc gen: update generated docs", ".",
        )

    if not gen_result.written and not root_generated:
        print("No files generated.")
    return 0


@app.command("gen-data", help="Generate data files by running sandboxed scripts")
@strictcli.flag("no-commit", type=bool, help="Skip auto-committing changed files")
def _cmd_gen_data(no_commit=False):
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
        if not no_commit:
            from selfdoc.git import auto_commit
            written_files = [
                os.path.relpath(p, ".") for p in generated
            ]
            auto_commit(
                written_files,
                "selfdoc gen-data: update generated data",
                ".",
            )
    else:
        print("No gen-data scripts configured.")
    return 0


def run():
    """Parse arguments and dispatch to the appropriate subcommand."""
    app.run()
