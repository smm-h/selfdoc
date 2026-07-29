"""Svelte source extractor for selfdoc -- parses .svelte files to extract component props, exports, and documentation for reference pages."""

from selfdoc_core.extractors.svelte import *  # noqa: F401,F403
from selfdoc_core.extractors.svelte import (  # noqa: F401
    _extract_component_doc,
    _extract_exports,
    _extract_legacy_props,
    _extract_props,
    _extract_script_blocks,
)
