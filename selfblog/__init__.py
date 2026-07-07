"""selfblog: Blog system for selfdoc-based documentation sites.

This package handles blog post discovery, assembly infrastructure,
unified multi-project site building, and post-related CLI commands.
It imports from selfdoc_core but never from selfdoc.
"""

from selfdoc_core import register_post_provider
from selfdoc_core._version import __version__  # noqa: F401
from selfdoc_core.posts import discover_posts

# Register the post provider so selfdoc_core's build pipeline can
# discover posts without importing selfblog.
register_post_provider(discover_posts)


def main():
    """Entry point for the selfblog CLI."""
    from selfblog.cli import run
    run()
