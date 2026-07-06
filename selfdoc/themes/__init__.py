"""Theme registry for selfdoc.

Re-export shim: actual implementation lives in selfdoc_core.themes.
This file exists for backward compatibility during the Phase 4 migration.
"""

from selfdoc_core.themes import *  # noqa: F401,F403

# Override __file__ so that os.path.dirname(themes_mod.__file__)
# resolves to selfdoc_core/themes/ where the CSS files actually live.
# This is needed for tests that write temporary theme files.
import selfdoc_core.themes as _core_themes
__file__ = _core_themes.__file__
