"""CLI interface for selfdoc."""

import argparse
import datetime
import http.server
import json
import os
import sys
import threading

from selfdoc import __version__


COMMANDS = {
    "init": "Initialize selfdoc in the current project",
    "build": "Build the documentation site",
    "serve": "Serve the documentation site locally",
    "deploy": "Deploy the documentation site",
    "check": "Check documentation coverage and consistency",
}


def _detect_language():
    """Auto-detect project language from project files.

    Returns (language, source_paths) tuple or (None, None) if undetectable.
    """
    if os.path.isfile("pyproject.toml") or os.path.isfile("setup.py"):
        # Detect Python source directories
        sources = []
        for candidate in ("src", "lib"):
            if os.path.isdir(candidate):
                sources.append(f"{candidate}/")
                break
        if not sources:
            # Look for a top-level package (directory with __init__.py)
            for entry in sorted(os.listdir(".")):
                init_path = os.path.join(entry, "__init__.py")
                if os.path.isdir(entry) and os.path.isfile(init_path):
                    sources.append(f"{entry}/")
                    break
        if not sources:
            sources = ["."]
        return "python", sources

    if os.path.isfile("go.mod"):
        sources = []
        for candidate in ("pkg", "internal", "cmd"):
            if os.path.isdir(candidate):
                sources.append(f"{candidate}/")
        if not sources:
            sources = ["."]
        return "go", sources

    if os.path.isfile("tsconfig.json"):
        sources = []
        for candidate in ("src", "lib"):
            if os.path.isdir(candidate):
                sources.append(f"{candidate}/")
                break
        if not sources:
            sources = ["."]
        return "typescript", sources

    if os.path.isfile("package.json"):
        sources = []
        for candidate in ("src", "lib"):
            if os.path.isdir(candidate):
                sources.append(f"{candidate}/")
                break
        if not sources:
            sources = ["."]
        return "javascript", sources

    return None, None


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


def _cmd_init(args):
    """Initialize selfdoc in the current project."""
    if os.path.isfile("selfdoc.json"):
        print("selfdoc.json already exists. Aborting.")
        sys.exit(1)

    language, sources = _detect_language()
    if language is None:
        print(
            "Could not detect project language. "
            "Supported: pyproject.toml (Python), go.mod (Go), "
            "tsconfig.json/package.json (TypeScript/JavaScript)"
        )
        sys.exit(1)

    project_name = os.path.basename(os.path.abspath("."))
    main_module = _detect_main_module()

    config = {
        "language": language,
        "source": sources,
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
            f":::module {main_module}\n"
            f":::\n"
        )
        with open(index_path, "w", encoding="utf-8") as f:
            f.write(starter)

    print(f"Initialized selfdoc for {language} project '{project_name}'")
    print(f"  Created: selfdoc.json")
    print(f"  Created: docs/index.md")
    print(f"  Source:  {', '.join(sources)}")
    print(f"\nRun 'selfdoc build' to generate documentation.")


def _cmd_build(args):
    """Build the documentation site."""
    from selfdoc.build import build

    try:
        written = build(".")
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    from selfdoc.check import check_docs, filter_lints
    from selfdoc.config import load_config

    config = load_config(".")
    output_dir = config["output"] if config else "docs/_build/"

    print(f"Built {len(written)} file(s) to {output_dir}")

    # Build ignore set from config
    ignore_codes = set()
    if config:
        ignore_codes.update(config.get("lint_ignore", []))

    # Run lint checks after build completes
    check_result = check_docs(".")
    lints = filter_lints(check_result.lints, ignore_codes)
    warn_count = 0
    for lint in lints:
        line_part = f":{lint.line}" if lint.line is not None else ""
        print(
            f"{lint.severity}: [{lint.code}] "
            f"{lint.file}{line_part} - {lint.message}"
        )
        if lint.severity == "warning":
            warn_count += 1

    if warn_count > 0:
        print(f"{warn_count} SEO warning(s) found.")
        sys.exit(1)


def _cmd_serve(args):
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

    port = args.port

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


def _cmd_deploy(args):
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

    # Detect version from project files
    version = _detect_version()

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


def _detect_version():
    """Detect project version from pyproject.toml or package.json."""
    # Try pyproject.toml
    if os.path.isfile("pyproject.toml"):
        try:
            try:
                import tomllib
            except ModuleNotFoundError:
                import tomli as tomllib  # type: ignore[no-redef]
            with open("pyproject.toml", "rb") as f:
                data = tomllib.load(f)
            return data.get("project", {}).get("version", "0.0.0")
        except Exception:
            pass

    # Try package.json
    if os.path.isfile("package.json"):
        try:
            with open("package.json", "r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get("version", "0.0.0")
        except Exception:
            pass

    return "0.0.0"


def _cmd_check(args):
    """Check documentation coverage and consistency."""
    from selfdoc.check import check_docs, filter_lints, print_results
    from selfdoc.config import load_config

    try:
        result = check_docs(".")
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    # Build combined ignore set from CLI --ignore and config lint_ignore
    ignore_codes = set()
    cli_ignore = getattr(args, "ignore", "")
    if cli_ignore:
        ignore_codes.update(
            code.strip() for code in cli_ignore.split(",") if code.strip()
        )
    config = load_config(".")
    if config:
        ignore_codes.update(config.get("lint_ignore", []))

    # Filter lints
    result.lints = filter_lints(result.lints, ignore_codes)

    # Determine exit code before output
    has_failures = any(dr.status == "FAILED" for dr in result.directive_results)
    has_warnings = any(lint.severity == "warning" for lint in result.lints)
    warn_only = getattr(args, "warn_only", False)

    # Coverage threshold check
    coverage_below_threshold = False
    min_coverage = config.get("min_coverage") if config else None
    if (
        min_coverage is not None
        and result.coverage is not None
        and result.coverage.total_public > 0
    ):
        actual_pct = result.coverage.referenced * 100 // result.coverage.total_public
        if actual_pct < min_coverage:
            coverage_below_threshold = True

    exit_code = 1 if (
        has_failures
        or (has_warnings and not warn_only)
        or coverage_below_threshold
    ) else 0

    if getattr(args, "format", "text") == "json":
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
                "documented_symbols": cov.documented_symbols,
                "undocumented_symbols": cov.undocumented_symbols,
            }
        print(json.dumps(output, indent=2))
    else:
        print_results(result)

    if coverage_below_threshold:
        actual_pct = result.coverage.referenced * 100 // result.coverage.total_public
        print(f"Coverage {actual_pct}% is below minimum threshold {min_coverage}%")

    if exit_code != 0:
        sys.exit(1)


def run():
    """Parse arguments and dispatch to the appropriate subcommand."""
    parser = argparse.ArgumentParser(
        prog="selfdoc",
        description="Code-aware static site generator with directive-based content extraction",
    )
    parser.add_argument(
        "--version", "-v", action="version", version=f"selfdoc {__version__}"
    )

    subparsers = parser.add_subparsers(dest="command", title="commands")

    # init
    sub_init = subparsers.add_parser("init", help=COMMANDS["init"])
    sub_init.set_defaults(func=_cmd_init)

    # build
    sub_build = subparsers.add_parser("build", help=COMMANDS["build"])
    sub_build.set_defaults(func=_cmd_build)

    # serve
    sub_serve = subparsers.add_parser("serve", help=COMMANDS["serve"])
    sub_serve.add_argument(
        "--port", "-p", type=int, default=8000, help="Port to serve on (default: 8000)"
    )
    sub_serve.set_defaults(func=_cmd_serve)

    # deploy
    sub_deploy = subparsers.add_parser("deploy", help=COMMANDS["deploy"])
    sub_deploy.set_defaults(func=_cmd_deploy)

    # check
    sub_check = subparsers.add_parser("check", help=COMMANDS["check"])
    sub_check.add_argument("--ignore", type=str, default="",
        help="Comma-separated SEO codes to suppress (e.g., SEO007,SEO008)")
    sub_check.add_argument("--format", choices=["text", "json"], default="text",
        help="Output format (default: text)")
    sub_check.add_argument("--warn-only", action="store_true", default=False,
        help="Treat SEO lint warnings as non-fatal (only directive failures and coverage threshold violations cause exit 1)")
    sub_check.set_defaults(func=_cmd_check)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    args.func(args)
