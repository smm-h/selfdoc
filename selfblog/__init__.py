"""selfblog: Blog system for selfdoc-based documentation sites.

This package handles blog post discovery, assembly infrastructure,
unified multi-project site building, and post-related CLI commands.
It imports from selfdoc_core but never from selfdoc.
"""

from selfdoc_core import register_post_check_hook, register_post_provider
from selfblog._version import __version__  # noqa: F401
from selfblog.posts import discover_posts

from selfblog.check import check_posts

# Register the post provider and post-check hook so selfdoc_core's build
# pipeline and selfdoc's check pipeline can handle posts without
# importing selfblog.
register_post_provider(discover_posts)
register_post_check_hook(check_posts)


def main():
    """Entry point for the selfblog CLI."""
    from selfblog.cli import run
    run()
