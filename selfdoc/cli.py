"""CLI interface for selfdoc -- defines the command-line entry point, argument parsing via strictcli, and subcommand dispatch for all commands."""

import datetime
import http.server
import json
import os
import sys
import threading

import strictcli

from selfdoc import payload_schemas
from selfdoc._version import __version__
from selfdoc_core import effects


app = strictcli.App(
    name="selfdoc",
    version=__version__,
    help="Code-aware static site generator with directive-based content extraction",
)

baseline_group = app.group("baseline", help="Manage the content and description hash baselines that drive staleness (STALE001) and source-drift (DRIFT001) detection during selfdoc check")


#: Everything a command can raise that is the *project's* fault rather than
#: selfdoc's: an unusable config, a suppression list naming a code that is
#: unknown or not suppressible, a directive no extractor answers, and the
#: RuntimeErrors the build and check raise for a defect they name.  All of
#: them are user errors, so all of them print one line and exit 1 -- a
#: traceback is what selfdoc owes for its own bugs, not for a bad file.
def _user_errors():
    from selfdoc_core.config import ConfigError
    from selfdoc_core.directives import DirectiveError

    return (ConfigError, DirectiveError, RuntimeError)


def _fail(exc):
    """Print *exc* as a refusal and exit 1."""
    print(f"Error: {exc}", file=sys.stderr)
    sys.exit(1)


def _absent_means(value, fallback):
    """Resolve an optional flag's absence to the fallback its help declares.

    strictcli's mutating-default ban forbids ``default=`` on any flag of a
    ``mutating`` command: a value the framework picks is a value the framework
    writes.  selfdoc's opt-out booleans (``--auto-commit``, ``--drafts``) and
    the one convenience scalar (``--port``) therefore declare
    ``presence="optional"`` and name their fallback in their own help text.
    This is the one place where absence becomes that fallback, so no
    downstream branch ever sees a ``None`` it would read as false.
    """
    return fallback if value is None else value


def _load_config_or_fail(dir_path="."):
    """Load the project config, or refuse cleanly.

    Every command reads the config, and a present-but-unusable one is a
    user error at each of them.  Loading through here is what keeps a
    command from ending on a ConfigError traceback because it forgot the
    handler that its neighbour remembered.
    """
    from selfdoc.config import load_config

    try:
        return load_config(dir_path)
    except _user_errors() as exc:
        _fail(exc)


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


@app.command("init", help="Initialize selfdoc configuration and starter docs template", effect="mutating")
@strictcli.flag("base-url", type=str, presence="required", help="Base URL the generated site will be served from (e.g. 'https://docs.example.com'). Required: it is the site's own address, which selfdoc cannot infer, and every canonical link, sitemap entry and feed URL is built from it")
@strictcli.flag("author-name", type=str, presence="required", help="Display name of the site's author. Required: every page carries structured data naming who wrote it, and a name is a fact about a person that selfdoc cannot invent")
@strictcli.flag("author-url", type=str, presence="required", help="Canonical URL identifying the site's author (e.g. 'https://you.example'). Required alongside --author-name: the structured data names an identity, and an identity has an address")
@strictcli.flag("auto-commit", type=bool, presence="optional", help="Automatically commit the generated selfdoc.json and docs/index.md template files to git. Omitted, it commits; pass --no-auto-commit to leave the files uncommitted")
@effects.handler
def _cmd_init(ctx, base_url, author_name, author_url, auto_commit=None):
    """Initialize selfdoc in the current project."""
    auto_commit = _absent_means(auto_commit, True)
    from selfdoc.extractors import detect_languages
    from selfdoc_core.utils import detect_project_version

    if os.path.isfile("selfdoc.json"):
        print("selfdoc.json already exists. Aborting.")
        sys.exit(1)

    if not base_url.strip():
        print("--base-url must be a non-empty URL.", file=sys.stderr)
        sys.exit(1)

    # The author is a fact about a person, so it is an input, never a guess.
    # A scaffolded config that omitted it would emit a site whose structured
    # data named nobody -- or, as it once did, an organisation invented from
    # the directory name.
    if not author_name.strip():
        print("--author-name must be a non-empty name.", file=sys.stderr)
        sys.exit(1)
    if not author_url.strip():
        print("--author-url must be a non-empty URL.", file=sys.stderr)
        sys.exit(1)

    # A project with no detectable language is a codeless project: a
    # portfolio or personal site that is nothing but markdown pages.  It gets
    # a config with no 'source' key at all -- an empty array would declare
    # the same thing more verbosely -- and a starter page with no
    # code-extraction directive.
    detected = detect_languages(".")

    source_entries = []
    for entry in detected:
        source_entries.extend(_detect_source_entries(entry["language"]))

    # Use the first detected language for the starter template
    primary_language = detected[0]["language"] if detected else None
    detected_languages = [e["language"] for e in detected]

    project_name = os.path.basename(os.path.abspath("."))
    main_module = _detect_main_module() if detected else None

    # What the project states about its own version decides what goes in the
    # file, and nothing is invented.  A codeless project publishes no
    # artifact, so it declares it has no public version and its pages carry
    # no badge, no version filter and no picker.  A project with code reads
    # its version out of its own manifest; when the manifest states none,
    # init refuses rather than writing a number the project never released.
    if source_entries:
        detected_version = detect_project_version(".")
        if not detected_version:
            print(
                "No version found in pyproject.toml, package.json or "
                "VERSION. A project that ships code has a version, so "
                "declare it there and run init again.",
                file=sys.stderr,
            )
            sys.exit(1)
        version_declaration = {"versions": [{"version": detected_version}]}
    else:
        version_declaration = {"unversioned": True}

    # Everything load_config and build require is written into the file, so
    # the emitted config is buildable with no hand-editing.  base_url comes
    # from the caller; the version declaration above and the single default
    # locale are the honest starting point for a new site.
    config = {
        "base_url": base_url.strip().rstrip("/"),
        "author": {
            "name": author_name.strip(),
            "url": author_url.strip().rstrip("/"),
        },
    }
    if source_entries:
        config["source"] = source_entries
    config.update({
        "docs": "docs/",
        "output": "docs/_build/",
        **version_declaration,
        "locales": [{"code": "en", "label": "English", "default": True}],
        "search_engine": "pagefind",
    })

    # Write selfdoc.json atomically
    config_json = json.dumps(config, indent=2) + "\n"
    effects.atomic_write("selfdoc.json", config_json)

    # Create docs/ directory
    effects.makedirs("docs", exist_ok=True)

    # Create starter index.md.  The API reference section only appears when
    # there is source code to extract from -- in a codeless project a 'ref'
    # directive is a hard error, not an empty section.
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
        )
        if detected:
            starter += (
                f"\n"
                f"## API Reference\n"
                f"\n"
                f':-: ref path="{main_module}" lang="{primary_language}"\n'
            )
        effects.write_text(index_path, starter)

    source_path_strs = [e["path"] for e in source_entries]
    langs_str = ", ".join(detected_languages)
    if detected:
        print(f"Initialized selfdoc for {langs_str} project '{project_name}'")
    else:
        print(
            f"Initialized selfdoc for codeless project '{project_name}' "
            "(no source code detected)"
        )
    print("  Created: selfdoc.json")
    print("  Created: docs/index.md")
    if source_path_strs:
        print(f"  Source:  {', '.join(source_path_strs)}")
    print(f"  Base URL: {config['base_url']}")
    print(f"  Author:   {config['author']['name']} <{config['author']['url']}>")
    print("\nRun 'selfdoc build' to generate documentation.")

    if auto_commit:
        from selfdoc.git import auto_commit as _auto_commit
        _auto_commit(
            ["selfdoc.json", "docs/index.md"], "selfdoc init", os.getcwd(),
        )

    return 0


@app.command("build", help="Build the documentation site from templates and source code", effect="mutating")
@strictcli.flag("auto-commit", type=bool, presence="optional", help="Automatically commit updated content hash tracking files to git after the build. Omitted, it commits; pass --no-auto-commit to leave them uncommitted")
@strictcli.flag("locale", type=str, presence="optional", help="Build only the specified locale instead of all (e.g., 'en')")
@strictcli.flag("version", type=str, presence="optional", help="Build only the specified version instead of all (e.g., '1.0.0')")
@strictcli.flag("drafts", type=bool, presence="optional", help="Include posts marked as draft in the build output alongside published posts. Omitted, drafts are left out; pass --drafts to include them")
@strictcli.flag("target", type=str, presence="optional", help="Build target. Omitted, the whole site is built; the only other value 'posts' now refuses and names selfblog, where posts-only builds moved")
@strictcli.flag("theme", type=str, presence="optional", help="Theme name that overrides the one selfdoc.json declares, for this build only (e.g. 'tinymoon'). Omitted, the config decides. Nothing is written back to selfdoc.json -- this exists so the same pages can be built under a different theme and looked at, without editing every project's config to do it")
@effects.handler
def _cmd_build(ctx, auto_commit=None, locale=None, version=None, drafts=None, target=None, theme=None):
    """Build the documentation site."""
    auto_commit = _absent_means(auto_commit, True)
    drafts = _absent_means(drafts, False)
    # A present-but-invalid selfdoc.json is a user error like any other:
    # it prints the message and exits 1, rather than ending the process on
    # an uncaught ConfigError and a traceback.
    config = _load_config_or_fail()

    # Unified sites and posts-only builds moved to selfblog.
    if config and config.get("unified"):
        print(
            "Error: building unified sites moved to selfblog -- "
            "use the selfblog CLI (pip install selfblog).",
            file=sys.stderr,
        )
        sys.exit(1)
    if target == "posts":
        print(
            "Error: posts-only builds moved to selfblog -- run "
            "'selfblog build --target posts' instead (pip install selfblog).",
            file=sys.stderr,
        )
        sys.exit(1)

    from selfdoc.build import build

    try:
        written = build(
            ".",
            version_filter=version,
            locale_filter=locale,
            include_drafts=drafts,
            # The engine's own API spells "no override" as the empty string;
            # the CLI now spells absence as absence, so the two meet here.
            target=target or "",
            theme=theme or "",
        )
    except _user_errors() as e:
        _fail(e)

    from selfdoc.check import check_docs, check_exit_code, filter_lints

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
    try:
        check_result = check_docs(".", version_filter=version)
        lints = filter_lints(check_result.lints, ignore_codes)
    except _user_errors() as e:
        _fail(e)
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

    # Reduced verdict: the build already reported directive failures inline
    # and measures no coverage, so only the lints reach the shared rules.
    if check_exit_code(lints) != 0:
        sys.exit(1)
    return 0


@app.command("serve", help="Serve the documentation site locally with live reload", effect="mutating")
@strictcli.flag("port", short="p", type=int, presence="optional", help="HTTP port number to serve on (e.g., 3000). Omitted, the server binds port 8000")
@strictcli.flag("drafts", type=bool, presence="optional", help="Rebuild the site with draft posts included before starting the local server. Omitted, drafts are left out; pass --drafts to include them")
@effects.handler
def _cmd_serve(ctx, port=None, drafts=None):
    """Serve the documentation site locally with SSE-based live reload."""
    port = _absent_means(port, 8000)
    drafts = _absent_means(drafts, False)
    config = _load_config_or_fail()
    if config is None:
        print("Error: No selfdoc.json found. Run 'selfdoc init' first.", file=sys.stderr)
        sys.exit(1)

    if drafts:
        if config.get("unified"):
            print(
                "Error: building unified sites moved to selfblog -- "
                "use the selfblog CLI (pip install selfblog).",
                file=sys.stderr,
            )
            sys.exit(1)
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


@app.command(
    "deploy",
    help="Deploy the built documentation site to the configured provider",
    effect="mutating",
    # Consequential: this is the one selfdoc command whose effects leave the
    # machine and land on a live, publicly-visible site. The Cloudflare Pages
    # provider makes the uploaded tree live the moment it lands; the GitHub
    # Pages provider force-pushes gh-pages, so the previously published tree is
    # gone from the remote and is not recoverable there. Neither can be undone
    # by rerunning the command.
    consequential=True,
    grants=[
        strictcli.Grant(
            "deploy",
            "publishes the built site to the configured Cloudflare Pages "
            "project; the deployment is live the moment it lands",
            strictcli.PROC_MUTATE,
        ),
        strictcli.Grant(
            "force-push",
            "replaces the remote gh-pages branch wholesale; the previous "
            "published tree is not recoverable from the remote afterwards",
            strictcli.PROC_MUTATE,
        ),
    ],
)
@effects.handler
def _cmd_deploy(ctx):
    """Deploy the documentation site."""
    from selfdoc.deploy import (
        DeployError,
        deploy_cloudflare_pages,
        deploy_github_pages,
    )

    config = _load_config_or_fail()
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
            # The project root is the deploy target: this command already
            # operates on "." (config, output dir), so the repository whose
            # origin receives the force-push is stated, not inferred.
            deploy_github_pages(output_dir, version, target=".")
        else:
            print(f"Error: Unknown deploy provider '{provider}'", file=sys.stderr)
            sys.exit(1)
    except DeployError as e:
        print(f"Deploy error: {e}", file=sys.stderr)
        sys.exit(1)
    return 0




@app.command("check", help="Check documentation coverage, directive resolution, and lint rules", effect="mutating", payload_schema=payload_schemas.CHECK)
@strictcli.flag("ignore", type=str, presence="optional", help="Comma-separated SEO codes to suppress (e.g., SEO007,SEO008)")
@strictcli.flag("auto-commit", type=bool, presence="optional", help="Automatically commit updated content hash tracking files to git after checking. Omitted, it commits; pass --no-auto-commit to leave them uncommitted")
@strictcli.flag("version-override", type=str, presence="optional", help="Project version that version-bearing generated content is expected to embed (VER004), instead of the version currently recorded in pyproject.toml/package.json. Pass the same value given to 'selfdoc gen --version-override' so the check runs correctly in the release window between generation and the version bump")
@effects.handler
def _cmd_check(ctx, ignore=None, auto_commit=None, version_override=None):
    """Check documentation coverage and consistency."""
    auto_commit = _absent_means(auto_commit, True)
    from selfdoc.check import (
        check_docs,
        check_result_exit_code,
        coverage_below_threshold,
        filter_lints,
        print_results,
        serialize_check_result,
    )
    from selfdoc_core.lints import LintSuppressionError, parse_ignore_codes

    # Validated before any work is done: a mistyped code suppresses nothing,
    # a check run that silently ignored the typo would report lints the
    # caller believes it silenced, and an error-severity code is not
    # suppressible at all.
    try:
        flag_ignore_codes = parse_ignore_codes(ignore)
    except LintSuppressionError as exc:
        _fail(exc)

    config = _load_config_or_fail()

    if config and config.get("unified"):
        print(
            "Error: unified projects are checked by selfblog. "
            "Run 'selfblog check' instead.",
            file=sys.stderr,
        )
        sys.exit(1)

    # No ``dry_run=`` is threaded into check_docs: under --dry-run the hash
    # write is RECORDED by the effects chokepoint rather than executed, which
    # both preserves the old "report staleness without writing" behavior and
    # makes the preview honest about the write a real run would perform.
    try:
        result = check_docs(
            ".", version_override=version_override,
        )
    except _user_errors() as e:
        _fail(e)

    if auto_commit:
        from selfdoc.git import auto_commit as _auto_commit
        _auto_commit(
            [".selfdoc/hashes/hashes.json"],
            "selfdoc: update content hashes",
            ".",
        )

    # Build combined ignore set from CLI --ignore and config lint_ignore
    # (both already validated against the registry).
    ignore_codes = set(flag_ignore_codes)
    if config:
        ignore_codes.update(config.get("lint_ignore", []))

    # Filter lints
    result.lints = filter_lints(result.lints, ignore_codes)

    # Coverage threshold check (uses documented count, not referenced)
    below_threshold = coverage_below_threshold(result.coverage, config)

    # Determine exit code before output
    exit_code = check_result_exit_code(result, config)

    # The payload is supplied in both modes -- the framework decides what to
    # do with it -- and the human report is written only outside machine
    # mode, where stdout carries the envelope and nothing else.
    ctx.payload(serialize_check_result(result, exit_code))

    if not ctx.json:
        print_results(result)

        if below_threshold:
            cov = result.coverage
            threshold = config.get("coverage_threshold", 1.0) if config else 1.0
            pct = cov.documented * 100 / cov.total_public
            threshold_pct = threshold * 100
            print(
                f"Coverage: {cov.documented}/{cov.total_public} symbols documented"
                f" ({pct:.0f}%). Threshold is {threshold_pct:.0f}%."
            )

    if exit_code != 0:
        sys.exit(1)
    return 0


@baseline_group.command("accept", help="Accept a reviewed staleness or drift dead-end by advancing a page's stored content and description hash baseline to its current values. Use this only after a human has confirmed the page's content changed but its existing frontmatter description was reviewed and is still accurate. Each named page must currently be reporting a STALE001 or DRIFT001 error; accepting clears that error so selfdoc check passes without rewriting an already-correct description.", effect="mutating")
@strictcli.arg("page", variadic=True, presence="required", help="Page identifier(s) to accept, named exactly as shown in 'selfdoc check' output (e.g. 'en/index.md'). Each page must currently report a STALE001 or DRIFT001 error; pages are named explicitly with no glob or --all shortcut so acceptance stays a deliberate per-page action.")
@strictcli.flag("auto-commit", type=bool, presence="optional", help="Automatically commit the updated content hash tracking file to git after accepting the named pages. Omitted, it commits; pass --no-auto-commit to leave it uncommitted")
@effects.handler
def _cmd_baseline_accept(ctx, page, auto_commit=None):
    """Accept reviewed staleness/drift for the named pages."""
    auto_commit = _absent_means(auto_commit, True)
    from selfdoc.check import AcceptError, accept_baselines

    config = _load_config_or_fail()
    if config is None:
        print("Error: No selfdoc.json found. Run 'selfdoc init' first.", file=sys.stderr)
        sys.exit(1)

    if config.get("unified"):
        print(
            "Error: unified projects are checked by selfblog. "
            "Run 'selfblog check' instead.",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        accepted = accept_baselines(page, dir_path=".", config=config)
    except (AcceptError, RuntimeError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"Accepted new baseline for {len(accepted)} page(s):")
    for page_id, code in accepted:
        print(f"  {page_id} (cleared {code})")

    if auto_commit:
        from selfdoc.git import auto_commit as _auto_commit
        _auto_commit(
            [".selfdoc/hashes/hashes.json"],
            "selfdoc baseline accept: " + ", ".join(p for p, _ in accepted),
            ".",
        )
    return 0


@app.command("gen", help="Auto-generate documentation pages from project structure", effect="mutating")
@strictcli.flag("auto-commit", type=bool, presence="optional", help="Automatically commit generated documentation pages and root files to git. Omitted, it commits; pass --no-auto-commit to leave them uncommitted")
@strictcli.flag("version-override", type=str, presence="optional", help="Project version to stamp into version-bearing generated content instead of the version currently recorded in pyproject.toml/package.json. Release orchestrators pass the about-to-be-released version here so generated root files are not one release behind (generation runs before the version bump is committed)")
@effects.handler
def _cmd_gen(ctx, auto_commit=None, version_override=None):
    """Auto-generate documentation pages from project structure."""
    auto_commit = _absent_means(auto_commit, True)
    from selfdoc.gen import GenResult, generate_docs, generate_root_files
    from selfdoc_core.content import VERSION_OVERRIDE_KEY

    config = _load_config_or_fail()
    if config is None:
        print("Error: No selfdoc.json found. Run 'selfdoc init' first.", file=sys.stderr)
        sys.exit(1)

    if version_override:
        config[VERSION_OVERRIDE_KEY] = version_override

    # A codeless project declares no 'source', which is the declaration that
    # there are no API or CLI reference pages to derive.  Say so and go
    # straight to the root-file templates, which need no source code.
    if config.get("source"):
        try:
            gen_result = generate_docs(config, base_dir=".")
        except RuntimeError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
    else:
        gen_result = GenResult()
        print(
            "No 'source' entries in selfdoc.json -- skipping API and CLI "
            "reference pages (codeless project). Root file templates still "
            "generate."
        )

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
    # gen regenerates content and description together, so no page is left
    # stale here -- the skeleton exemption is unnecessary. Pass an empty set
    # explicitly (update_hashes requires the keyword).
    if locales:
        locale_code = locales[0]["code"]
        prefixed = {f"{locale_code}/{rp}": val for rp, val in all_docs.items()}
        update_hashes(prefixed, ".", skeleton_pages=set())
    else:
        update_hashes(all_docs, ".", skeleton_pages=set())
    all_commit_files.append(".selfdoc/hashes/hashes.json")

    # Discover posts for manifest -- via the post provider registered by
    # selfblog (posts moved to selfblog).  Skipped when no posts
    # directory exists; posts present without a provider is a hard
    # error naming selfblog.
    posts_config = config.get("posts") or {}
    posts_dir = posts_config.get("dir", ".selfdoc/posts/")
    if os.path.isdir(posts_dir):
        from selfdoc_core import require_post_provider

        posts = require_post_provider()(posts_dir)
    else:
        posts = []
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


@app.command("gen-data", help="Generate data files by running sandboxed scripts via bwrap", effect="mutating")
@strictcli.flag("auto-commit", type=bool, presence="optional", help="Automatically commit the generated data output files to git after script execution. Omitted, it commits; pass --no-auto-commit to leave them uncommitted")
@effects.handler
def _cmd_gen_data(ctx, auto_commit=None):
    """Generate data files by running sandboxed scripts."""
    auto_commit = _absent_means(auto_commit, True)
    from selfdoc.gendata import GenDataError, generate_data

    config = _load_config_or_fail()
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


@app.command("spell-corpus", help="Spell-check the docs of every selfdoc project beside this one, using the same engine 'selfdoc check' runs (SPELL001) and the shared accept list. Read-only over every project it visits", effect="read_only", payload_schema=payload_schemas.SPELL_CORPUS)
@strictcli.flag("root", type=str, presence="optional", help="Directory whose immediate subdirectories are searched for selfdoc.json. Omitted, the parent of the current directory is searched, i.e. this project's siblings")
@strictcli.flag("detail", type=bool, default=True, help="List each project's unknown words with a first location and any suggestion, after the summary table")
@effects.handler
def _cmd_spell_corpus(ctx, root=None, detail=True):
    """Run the spelling engine across every sibling selfdoc project."""
    from selfdoc_core.spelling import AcceptListError
    from selfdoc.spell_corpus import render_corpus_text, run_spell_corpus

    target = root or os.path.dirname(os.path.abspath("."))
    try:
        document, exit_code = run_spell_corpus(target)
    except AcceptListError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    ctx.payload(document)
    if not ctx.json:
        print(render_corpus_text(document, detail=detail))
    return exit_code


@app.command("quality", help="Show documentation quality tier and metrics for the current project", effect="read_only", payload_schema=payload_schemas.QUALITY)
@effects.handler
def _cmd_quality(ctx):
    from selfdoc.quality import format_single_text, run_quality

    try:
        result = run_quality()
    except _user_errors() as exc:
        _fail(exc)

    ctx.payload(result)
    if not ctx.json:
        print(format_single_text(result))
    return 0


def run():
    """Parse arguments and dispatch to the appropriate subcommand."""
    # If selfblog is installed, importing it registers the post provider
    # (and post-check hook) with selfdoc_core so build/gen/check handle
    # posts-carrying projects.  Without selfblog, posts-carrying
    # operations hard-error naming selfblog (selfdoc_core.
    # require_post_provider) -- installing selfblog IS the mode selection.
    try:
        import selfblog  # noqa: F401
    except ImportError:
        pass
    app.run()
