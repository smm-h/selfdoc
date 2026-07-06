"""selfblog: Blog system for selfdoc-based documentation sites.

This package handles blog post discovery, assembly infrastructure,
unified multi-project site building, and post-related CLI commands.
It imports from selfdoc_core but never from selfdoc.
"""

from selfdoc_core._version import __version__  # noqa: F401


def main():
    """Entry point for the selfblog CLI."""
    from selfblog.cli import run
    run()
