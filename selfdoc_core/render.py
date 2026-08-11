"""Render a page from content held in memory, writing nothing.

The build pipeline turns a post into a page by writing it into the docs
tree, building, and deleting it again.  That is fine for a build and
useless for an editor: previewing an unsaved buffer must not touch the
working tree at all -- no injected files, no staleness baselines, no
manifest.

This module is the render path.  It hands the same payloads the injector
would have written to ``build_single`` as an in-memory overlay, with
baseline writing off, and returns the page HTML exactly as the build
would have written it.  Same directive resolution, same HTML pass, same
addressing -- the only difference is that nothing lands on disk.
"""

from __future__ import annotations

import os

from selfdoc_core import require_post_parser, require_post_provider
from selfdoc_core.build import (
    _minify_html,
    build_single,
    post_docs_payloads,
)
from selfdoc_core.config import load_config
from selfdoc_core.html import _md_to_html_path


def render_post(dir_path, source_path, content, config=None,
                include_drafts=False):
    """Render one post to final HTML from an in-memory buffer.

    The result is byte-identical to the file ``build(target="posts")``
    writes for the same content saved to disk, and the call writes
    nothing anywhere.

    Args:
        dir_path: Project root directory.
        source_path: The post's path relative to the posts directory
            (e.g. ``"hello.md"``).  The file need not exist -- an unsaved
            new post renders the same way.
        content: The post's markdown source, frontmatter included, as it
            would be saved.
        config: Pre-loaded config dict (loaded from selfdoc.json if None).
        include_drafts: Render the post even when its frontmatter marks it
            a draft.  Mirrors the build flag of the same name: with it
            off, a draft has no page and asking for one is an error.

    Returns:
        The page HTML.

    Raises:
        RuntimeError: If no config is found, if the post is a draft and
            *include_drafts* is off, or if the rendered page is missing
            from the build result.
    """
    if config is None:
        config = load_config(dir_path)
    if config is None:
        raise RuntimeError(
            "No selfdoc.json found. Run 'selfdoc init' to initialize."
        )

    edited = require_post_parser()(content, source_path)

    if edited["draft"] and not include_drafts:
        raise RuntimeError(
            f"Post {source_path} is a draft and has no page. "
            f"Pass include_drafts=True to render it anyway."
        )

    posts_config = config.get("posts") or {}
    posts_dir = os.path.join(dir_path, posts_config.get("dir", ".selfdoc/posts/"))
    manifest_path = os.path.join(dir_path, ".selfdoc", "manifest.json")

    # The rest of the posts come from disk: a post page's nav and listing
    # neighbours are whatever is saved.  The edited post replaces its own
    # saved copy in place, so its position in the listing is the saved
    # one until it is saved again.
    discovered = require_post_provider()(posts_dir, manifest_path=manifest_path)
    posts = [dict(post) for post in discovered]
    for idx, post in enumerate(posts):
        if post["path"] == source_path:
            posts[idx] = edited
            break
    else:
        posts.append(edited)

    published = [
        post for post in posts
        if include_drafts or not post["draft"]
    ]
    payloads = post_docs_payloads(published)

    page_md = f"posts/{edited['slug']}.md"
    result = build_single(
        dir_path=dir_path,
        config=config,
        mount_locale="",
        mount_version="",
        version_override="",
        page_filter=set(payloads),
        overlay_docs=payloads,
        write_baselines=False,
    )

    output_key = _md_to_html_path(page_md)
    if output_key not in result.html_files:
        raise RuntimeError(
            f"Post {source_path} produced no page at {output_key!r}."
        )

    return _minify_html(result.html_files[output_key])
