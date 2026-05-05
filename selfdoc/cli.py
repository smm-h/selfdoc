"""CLI interface for selfdoc."""

import argparse
import sys

from selfdoc import __version__


COMMANDS = {
    "init": "Initialize selfdoc in the current project",
    "build": "Build the documentation site",
    "serve": "Serve the documentation site locally",
    "deploy": "Deploy the documentation site",
    "check": "Check documentation coverage and consistency",
}


def _stub(args):
    """Placeholder handler for unimplemented subcommands."""
    print(f"selfdoc {args.command}: not yet implemented")


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

    for name, help_text in COMMANDS.items():
        sub = subparsers.add_parser(name, help=help_text)
        sub.set_defaults(func=_stub, command=name)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    args.func(args)
