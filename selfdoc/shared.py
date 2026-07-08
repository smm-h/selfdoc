"""Generate shared elements for multi-project documentation assembly including homepage, blog index, nav JSON, RSS feed, and sitemap.

Re-export shim: actual implementation in selfblog.shared. selfblog is
an optional install for selfdoc (the selfdoc package does not depend on
it), so the import is guarded with a clean error.
"""

try:
    from selfblog.shared import *  # noqa: F401,F403
    from selfblog.shared import _page_path_to_url_segment  # noqa: F401
except ImportError as exc:
    raise ImportError(
        "selfdoc.shared moved to the selfblog package. "
        "Install it with: pip install selfblog"
    ) from exc
