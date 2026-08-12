"""Post discovery and validation for selfdoc blog posts, scanning the posts directory for dated markdown files with frontmatter metadata."""

from __future__ import annotations

import os
import re

from selfdoc_core.directives import find_directive_markers
from selfdoc_core.manifest import _to_kebab, load_manifest_from_git
from selfdoc_core.utils import parse_frontmatter

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def discover_posts(
    posts_dir: str,
    manifest_path: str | None = None,
) -> list[dict]:
    """Discover, validate, and return blog posts from a directory.

    Walks ``posts_dir`` for ``.md`` files, parses frontmatter, validates
    required fields, and returns metadata dicts sorted newest-first.

    Posts are pages discovered from a different directory.  They get
    ``type: "post"`` and ``versioned: False`` injected automatically.
    The existing unversioned page infrastructure handles the rest.

    Parameters
    ----------
    posts_dir:
        Directory to scan for ``.md`` post files.
    manifest_path:
        Optional path to an existing manifest JSON file.  When provided,
        slug immutability is enforced: if a post file path matches an
        entry in the manifest but the slug differs, a ``RuntimeError``
        is raised.

    Returns
    -------
    list[dict]
        Post metadata dicts sorted by date descending, then slug
        ascending for same-date posts.
    """
    if not os.path.isdir(posts_dir):
        return []

    # Load manifest from git for slug immutability check.
    # We read from git HEAD (not disk) because selfdoc gen may have
    # already regenerated manifest.json with new slugs by this point.
    manifest = None
    if manifest_path is not None:
        dir_path = os.path.dirname(os.path.dirname(manifest_path))
        manifest = load_manifest_from_git(dir_path)

    # Build a lookup from path -> slug for manifest posts.
    manifest_slugs: dict[str, str] = {}
    if manifest is not None:
        for entry in manifest.posts:
            manifest_slugs[entry["path"]] = entry["slug"]

    posts: list[dict] = []

    for dirpath, _dirnames, filenames in os.walk(posts_dir):
        for fname in filenames:
            if not fname.endswith(".md"):
                continue

            full_path = os.path.join(dirpath, fname)
            rel_path = os.path.relpath(full_path, posts_dir)

            with open(full_path, "r", encoding="utf-8") as f:
                raw = f.read()

            posts.append(parse_post(
                raw, rel_path, published_slug=manifest_slugs.get(rel_path),
            ))

    # -- Validate slug uniqueness ------------------------------------------

    seen_slugs: dict[str, str] = {}
    for post in posts:
        slug = post["slug"]
        if slug in seen_slugs:
            raise RuntimeError(
                f"Duplicate slug {slug!r}: used by both "
                f"{seen_slugs[slug]!r} and {post['path']!r}"
            )
        seen_slugs[slug] = post["path"]

    # -- Sort: newest first, then slug ascending for ties ------------------

    posts.sort(key=lambda p: (-_date_sort_key(p["date"]), p["slug"]))

    return posts


def parse_post(
    raw: str,
    rel_path: str,
    published_slug: str | None = None,
) -> dict:
    """Parse and validate one post's markdown source into a post dict.

    This is the whole of what makes a post a post: field validation, the
    required ``directives`` declaration, slug derivation, and the injected
    ``type``/``versioned`` keys.
    ``discover_posts`` calls it per file on disk; the render path calls it
    on an editor buffer that may never be saved, so both agree on what the
    source means.

    Parameters
    ----------
    raw:
        The post's markdown source, frontmatter included.
    rel_path:
        The post's path relative to the posts directory, used in error
        messages and carried on the returned dict.
    published_slug:
        The slug this post was published under, when it has one.  A
        different derived slug is a slug immutability violation.

    Returns
    -------
    dict
        Post metadata, in the shape ``discover_posts`` returns.
    """
    frontmatter, content = parse_frontmatter(raw)

    # -- Validate required fields ------------------------------------------

    title = frontmatter.get("title")
    if not title:
        raise RuntimeError(
            f"Post {rel_path}: 'title' is required and must be non-empty"
        )

    date = frontmatter.get("date")
    if not date:
        raise RuntimeError(f"Post {rel_path}: 'date' is required")
    date = str(date)
    if not _DATE_RE.match(date):
        raise RuntimeError(
            f"Post {rel_path}: 'date' must be YYYY-MM-DD, got {date!r}"
        )

    # -- The directive declaration -------------------------------------------
    #
    # Required, boolean, no default.  A post is authored content that may or
    # may not carry executable markers, and which of the two it is cannot be
    # inferred from the file: a post about directive syntax reads exactly
    # like a post that uses it.  So the author declares, and a post that
    # declares nothing is refused rather than guessed at.  Documentation
    # pages carry no such key -- the whole docs tree is directive territory.

    declaration = frontmatter.get("directives")
    if declaration is None:
        raise RuntimeError(
            f"Post {rel_path}: 'directives' is required and has no default. "
            f"Declare 'directives: true' if the post carries directive "
            f"markers, or 'directives: false' if it is plain prose."
        )
    if not isinstance(declaration, bool):
        raise RuntimeError(
            f"Post {rel_path}: 'directives' must be true or false, "
            f"got {declaration!r}."
        )

    if not declaration:
        # Line numbers are the post file's own: the scan runs over the body,
        # so the frontmatter it sits behind is added back.
        fm_offset = len(raw.split("\n")) - len(content.split("\n"))
        found = find_directive_markers(content)
        if found:
            body_line, marker = found[0]
            raise RuntimeError(
                f"Post {rel_path}: declares 'directives: false' but line "
                f"{body_line + fm_offset} carries the directive marker "
                f"'{marker}'. Declare 'directives: true' to have it "
                f"resolved, or remove the marker."
            )

    # -- Auto-generate slug if missing --------------------------------------

    slug = frontmatter.get("slug")
    if slug:
        slug = str(slug)
    else:
        slug = _to_kebab(str(title))

    # -- Slug immutability check --------------------------------------------

    if published_slug is not None and published_slug != slug:
        raise RuntimeError(
            f"Post {rel_path}: slug changed from "
            f"{published_slug!r} to {slug!r}. Slug immutability "
            f"violation -- slugs cannot change once published."
        )

    # -- Inject type and versioned ------------------------------------------

    frontmatter["type"] = "post"
    frontmatter["versioned"] = False

    # -- Defaults for optional fields ---------------------------------------

    tags = frontmatter.get("tags")
    if tags is None:
        tags = []
    frontmatter["tags"] = tags

    draft = frontmatter.get("draft", False)

    return {
        "path": rel_path,
        "title": str(title),
        "date": date,
        "slug": slug,
        "tags": tags,
        "draft": bool(draft),
        "directives": declaration,
        "type": "post",
        "versioned": False,
        "locale": frontmatter.get("locale"),
        "version": frontmatter.get("version"),
        "prev_version": frontmatter.get("prev_version"),
        "bump_type": frontmatter.get("bump_type"),
        "release_url": frontmatter.get("release_url"),
        "registry_urls": frontmatter.get("registry_urls"),
        "content": content,
        "frontmatter": frontmatter,
    }


def _date_sort_key(date_str: str) -> int:
    """Convert a YYYY-MM-DD string to an integer for sorting."""
    return int(date_str.replace("-", ""))
