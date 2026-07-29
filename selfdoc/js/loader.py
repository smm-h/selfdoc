"""Loader for selfdoc JS files using importlib.resources -- provides runtime access to bundled JavaScript for search, theming, and navigation.
#
# Re-export shim: actual implementation lives in selfdoc_core.js.loader.
# This file exists for backward compatibility during the Phase 4 migration.
"""

from selfdoc_core.js.loader import *  # noqa: F401,F403
