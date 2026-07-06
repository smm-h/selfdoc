"""selfdoc: Code-aware static site generator with directive-based content extraction."""

from selfdoc._version import __version__  # noqa: F401

# Register selfdoc-specific directives (table-commands) in the core registry.
# This import triggers the registration side effect in selfdoc.content.
import selfdoc.content  # noqa: F401


def main():
    """Entry point for the selfdoc CLI."""
    from selfdoc.cli import run
    run()
