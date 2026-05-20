"""Description staleness detection via content hashing.

Tracks SHA-256 hashes of page content and frontmatter descriptions.
When a page's content changes but its description stays the same,
the description is considered "stale" and check will report an error.
"""

import hashlib
import json
import os
import tempfile


def compute_content_hash(resolved_content: str) -> str:
    """Compute SHA-256 hash of resolved page content (frontmatter stripped).

    The frontmatter (if present) is stripped before hashing so that only
    the actual page body is considered.
    """
    body = _strip_frontmatter(resolved_content)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def compute_description_hash(description: str) -> str:
    """Compute SHA-256 hash of a frontmatter description string."""
    return hashlib.sha256(description.encode("utf-8")).hexdigest()


def load_hashes(base_dir: str) -> dict[str, dict]:
    """Load hash store from .selfdoc/hashes/hashes.json.

    Returns a dict mapping page path (relative to docs/) to
    {"content": hash, "description": hash}. Returns empty dict
    if the file does not exist.
    """
    path = os.path.join(base_dir, ".selfdoc", "hashes", "hashes.json")
    if not os.path.isfile(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_hashes(hashes: dict, base_dir: str) -> None:
    """Save hash store to .selfdoc/hashes/hashes.json.

    Creates the .selfdoc/hashes/ directory if it doesn't exist.
    Uses atomic write (temp file + os.replace) for safety.
    """
    hashes_dir = os.path.join(base_dir, ".selfdoc", "hashes")
    os.makedirs(hashes_dir, exist_ok=True)
    target = os.path.join(hashes_dir, "hashes.json")
    fd, tmp_path = tempfile.mkstemp(dir=hashes_dir, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(hashes, f, indent=2, sort_keys=True)
            f.write("\n")
        os.replace(tmp_path, target)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def check_staleness(
    page_path: str,
    content_hash: str,
    description_hash: str,
    stored_hashes: dict,
) -> str | None:
    """Check whether a page's description is stale.

    Returns an error message if the page content changed but the
    description did not. Returns None otherwise (new page, unchanged
    content, or description was updated alongside content).
    """
    if page_path not in stored_hashes:
        # New page -- no staleness
        return None
    stored = stored_hashes[page_path]
    if content_hash == stored.get("content"):
        # Content unchanged -- no staleness
        return None
    if description_hash != stored.get("description"):
        # Description was updated too -- no staleness
        return None
    # Content changed but description stayed the same
    return (
        f"{page_path}: content changed but frontmatter description "
        f"was not updated (possible stale description)"
    )


def update_hashes(all_docs, base_dir=".", dry_run=False):
    """Compute content and description hashes for all docs and save.

    Args:
        all_docs: Dict from resolve_all_docs {rel_path: (fm, resolved, raw, fm_lines)}
        base_dir: Project root
        dry_run: If True, compute but don't write to disk

    Returns:
        List of LintResult-compatible tuples (rel_path, stale_msg) for stale pages.
    """
    stored_hashes = load_hashes(base_dir)
    current_hashes: dict[str, dict] = {}
    stale_warnings = []

    for rel_path in sorted(all_docs):
        metadata, resolved_content, _raw, _fm_lines = all_docs[rel_path]
        description = metadata.get("description")
        if description is None:
            continue
        c_hash = compute_content_hash(resolved_content)
        d_hash = compute_description_hash(str(description))
        current_hashes[rel_path] = {
            "content": c_hash,
            "description": d_hash,
        }
        stale_msg = check_staleness(rel_path, c_hash, d_hash, stored_hashes)
        if stale_msg is not None:
            stale_warnings.append((rel_path, stale_msg))

    # Merge current hashes into stored (preserve pages not in this run)
    stored_hashes.update(current_hashes)
    if not dry_run:
        save_hashes(stored_hashes, base_dir)

    return stale_warnings


def _strip_frontmatter(content: str) -> str:
    """Strip YAML frontmatter from content, returning only the body."""
    if not content.startswith("---"):
        return content
    lines = content.split("\n")
    for idx in range(1, len(lines)):
        if lines[idx].strip() == "---":
            return "\n".join(lines[idx + 1:]).lstrip("\n")
    return content
