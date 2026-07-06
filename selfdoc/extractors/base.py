"""Re-export shim: actual implementation in selfdoc_core.extractors.base."""

from selfdoc_core.extractors.base import *  # noqa: F401,F403
from selfdoc_core.extractors.base import (  # noqa: F401
    _config_from_json,
    _config_from_toml,
)
