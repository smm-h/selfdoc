"""Manifest generation and loading for selfdoc projects, producing JSON metadata for pages, posts, slugs, and version info.

Re-export shim: actual implementation in selfdoc_core.manifest.
"""

from selfdoc_core.manifest import *  # noqa: F401,F403
from selfdoc_core.manifest import _extract_title, _to_kebab, manifest_compat  # noqa: F401
