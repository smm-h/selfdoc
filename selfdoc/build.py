"""Build pipeline for selfdoc -- scans docs/ templates, resolves directives against source code, and generates static HTML output.

Re-export shim: actual implementation in selfdoc_core.build.
"""

from selfdoc_core.build import *  # noqa: F401,F403

# Explicit re-exports of private names used by tests and other modules
from selfdoc_core.build import (  # noqa: F401
    _add_image_dimensions,
    _build_posts_only,
    _cleanup_injected_posts,
    _compress_output,
    _extract_critical_css,
    _extract_version_content,
    _generate_atom_feed,
    _generate_auxiliary_files,
    _generate_favicon_svg,
    _generate_headers,
    _generate_og_png_basic,
    _generate_robots_txt,
    _generate_sitemap,
    _inject_posts_into_docs,
    _make_feed_entry,
    _make_url_builder,
    _minify_css,
    _minify_html,
    _partition_pages,
    _versioned_html_paths,
    check_post_slug_uniqueness,
    _check_reserved_page_paths,
    _read_jpeg_dimensions,
    _read_webp_dimensions,
    _render_post_listing,
    _run_pagefind,
    _build_body,
    _HAS_PREDRAW,
)
