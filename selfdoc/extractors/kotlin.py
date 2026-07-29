"""Kotlin source extractor for selfdoc -- parses .kt files to extract public declarations, KDoc comments, and data class schemas for documentation."""

from selfdoc_core.extractors.kotlin import *  # noqa: F401,F403
from selfdoc_core.extractors.kotlin import _parse_kdoc  # noqa: F401
