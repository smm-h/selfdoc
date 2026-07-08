"""Assembly infrastructure for unified multi-project documentation deployment via GitHub Actions dispatch and Cloudflare Pages.

Re-export shim: actual implementation in selfblog.assembly. selfblog is
an optional install for selfdoc (the selfdoc package does not depend on
it), so the import is guarded with a clean error.
"""

try:
    from selfblog.assembly import *  # noqa: F401,F403
except ImportError as exc:
    raise ImportError(
        "selfdoc.assembly moved to the selfblog package. "
        "Install it with: pip install selfblog"
    ) from exc
