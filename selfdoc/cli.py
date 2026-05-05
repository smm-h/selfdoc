"""CLI interface for selfdoc."""

import argparse
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
        starter = (
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

    from selfdoc.config import load_config

    config = load_config(".")
    output_dir = config["output"] if config else "docs/_build/"

    print(f"Built {len(written)} file(s) to {output_dir}")


def _cmd_serve(args):
    """Serve the documentation site locally."""
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

    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=output_dir, **kw)

        def log_message(self, format, *log_args):
            # Quieter logging
            pass

    server = http.server.HTTPServer(("", port), Handler)
    print(f"Serving docs at http://localhost:{port}/")
    print("Press Ctrl+C to stop.")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
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
    from selfdoc.check import check_docs, print_results

    try:
        result = check_docs(".")
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    print_results(result)

    # Exit with non-zero status if any directives failed
    if any(dr.status == "FAILED" for dr in result.directive_results):
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
    sub_check.set_defaults(func=_cmd_check)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    args.func(args)
