"""Post revision tracking via sidecar revisions.json.

Tracks content changes to blog posts using SHA-256 hashes of the
rendered body text.  A new revision is appended only when the body
content actually changes (frontmatter-only edits are invisible).

The sidecar file lives at ``.selfdoc/revisions.json`` -- separate from
the manifest to avoid any manifest format risk.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import os

from selfdoc_core.utils import atomic_write


_REVISIONS_FILENAME = "revisions.json"


def compute_post_content_hash(body: str) -> str:
    """Compute a deterministic SHA-256 hash of a post's body text.

    The body is the rendered content with frontmatter already stripped.
    Whitespace is normalized (strip + collapse blank lines) so that
    insignificant formatting changes do not trigger false revisions.

    Site-context-dependent values (base URLs, theme names) must NOT
    appear in the input -- callers pass only the body text.
    """
    normalized = _normalize_body(body)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _normalize_body(body: str) -> str:
    """Normalize body text for deterministic hashing.

    Strips leading/trailing whitespace per line and collapses runs of
    blank lines into a single blank line.  This makes the hash stable
    across trivial whitespace edits.
    """
    lines = [line.strip() for line in body.splitlines()]
    # Collapse consecutive blank lines into one
    result: list[str] = []
    prev_blank = False
    for line in lines:
        if not line:
            if not prev_blank:
                result.append("")
            prev_blank = True
        else:
            result.append(line)
            prev_blank = False
    # Strip leading/trailing blank lines from the whole result
    text = "\n".join(result).strip()
    return text


def load_revisions(dir_path: str) -> dict:
    """Load revisions.json from .selfdoc/, returning the parsed dict.

    Returns ``{"posts": {}}`` if the file does not exist.
    """
    path = os.path.join(dir_path, ".selfdoc", _REVISIONS_FILENAME)
    if not os.path.isfile(path):
        return {"posts": {}}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_revisions(data: dict, dir_path: str) -> str:
    """Save revisions.json to .selfdoc/ atomically.

    Returns the absolute path of the written file.
    """
    selfdoc_dir = os.path.join(dir_path, ".selfdoc")
    os.makedirs(selfdoc_dir, exist_ok=True)
    path = os.path.join(selfdoc_dir, _REVISIONS_FILENAME)
    atomic_write(path, json.dumps(data, indent=2) + "\n")
    return path


def record_revision(
    dir_path: str,
    slug: str,
    body: str,
    summary: str = "",
) -> bool:
    """Record a revision for a post if the body content changed.

    Computes the content hash, compares against the latest revision
    for this slug, and appends a new entry only if the hash differs.

    Args:
        dir_path: Project root directory.
        slug: The post's slug identifier.
        body: The rendered body text (frontmatter stripped).
        summary: Optional human-readable summary of the change.

    Returns:
        True if a new revision was appended, False if content unchanged.
    """
    content_hash = compute_post_content_hash(body)
    data = load_revisions(dir_path)
    posts = data.setdefault("posts", {})
    revisions = posts.setdefault(slug, {}).setdefault("revisions", [])

    # Check if the latest revision has the same hash
    if revisions and revisions[-1]["content_hash"] == content_hash:
        return False

    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
    entry: dict = {
        "content_hash": content_hash,
        "timestamp": timestamp,
    }
    if summary:
        entry["summary"] = summary

    revisions.append(entry)
    save_revisions(data, dir_path)
    return True


def get_post_revisions(dir_path: str, slug: str) -> list[dict]:
    """Return the list of revisions for a post, or empty list."""
    data = load_revisions(dir_path)
    post_data = data.get("posts", {}).get(slug, {})
    return post_data.get("revisions", [])


def get_last_updated(dir_path: str, slug: str) -> str | None:
    """Return the timestamp of the most recent revision, or None."""
    revisions = get_post_revisions(dir_path, slug)
    if not revisions:
        return None
    return revisions[-1]["timestamp"]
