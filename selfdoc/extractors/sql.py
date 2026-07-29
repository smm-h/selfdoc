"""SQL schema extractor for selfdoc -- parses PostgreSQL DDL files to extract table definitions, views, types, and COMMENT ON documentation."""

from selfdoc_core.extractors.sql import *  # noqa: F401,F403
from selfdoc_core.extractors.sql import (  # noqa: F401
    _parse_comments,
    _parse_create_function,
    _parse_create_table,
    _parse_create_type,
    _parse_create_view,
)
