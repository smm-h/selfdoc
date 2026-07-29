"""Language extractor registry and auto-detection -- discovers and loads extractors for Python, Go, TypeScript, and other supported languages.
#
# Re-export shim: actual implementation lives in selfdoc_core.extractors.
# This file exists for backward compatibility during the Phase 4 migration.
"""

from selfdoc_core.extractors import *  # noqa: F401,F403

# Re-export SourceEntry explicitly since it's a dataclass imported by name
from selfdoc_core.extractors import SourceEntry  # noqa: F401
from selfdoc_core.extractors import EXTRACTORS  # noqa: F401
from selfdoc_core.extractors import _DETECTION_ORDER  # noqa: F401
