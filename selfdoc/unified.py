"""Monorepo unified site builder.

Re-export shim: actual implementation in selfblog.unified. selfblog is
an optional install for selfdoc (the selfdoc package does not depend on
it), so the import is guarded with a clean error.
"""

try:
    from selfblog.unified import *  # noqa: F401,F403
    from selfblog.unified import (  # noqa: F401
        _build_unified_nav,
        _generate_landing_page,
        _project_nav_title,
        _project_slug,
        _resolve_project_path,
        _validate_rlsbl_workspace,
    )
except ImportError as exc:
    raise ImportError(
        "selfdoc.unified moved to the selfblog package. "
        "Install it with: pip install selfblog"
    ) from exc
