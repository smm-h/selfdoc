"""Convert Markdown files to static HTML with a built-in minimal converter -- handles headings, code blocks, tables, and inline formatting.

Re-export shim: actual implementation in selfdoc_core.html.
"""

from selfdoc_core.html import *  # noqa: F401,F403

# Explicit re-exports of private names used by tests and other modules
from selfdoc_core.html import (  # noqa: F401
    _extract_title,
    _wrap_page,
    _minify_js,
    _render_seo_tags,
    _parse_table,
    _build_nav,
    _md_to_html_path,
    _html_path_to_url,
    _html_to_md_path,
    _slugify,
    _escape_html,
)
