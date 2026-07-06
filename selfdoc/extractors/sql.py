"""Re-export shim: actual implementation in selfdoc_core.extractors.sql."""

from selfdoc_core.extractors.sql import *  # noqa: F401,F403
from selfdoc_core.extractors.sql import (  # noqa: F401
    _parse_comments,
    _parse_create_function,
    _parse_create_table,
    _parse_create_type,
    _parse_create_view,
)
