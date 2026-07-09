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


def extract_module_docstring(path: str, extractor: object) -> str:
    """Extract the module-level docstring from a source file via its extractor."""
    return extractor.module_docstring(path)


def compute_source_docstring_hash(
    source_files: list[tuple[str, object]],
) -> str | None:
    """Compute SHA-256 hash of concatenated module docstrings from source files.

    Args:
        source_files: List of (file_path, extractor) tuples.

    Returns:
        Hash string, or None if no docstrings were extracted.
    """
    sorted_files = sorted(source_files, key=lambda x: x[0])
    docstrings = [extract_module_docstring(fp, ext) for fp, ext in sorted_files]
    if not any(docstrings):
        return None
    combined = "\n".join(docstrings)
    return hashlib.sha256(combined.encode("utf-8")).hexdigest()


def compute_schema_hash(schema_slice: dict) -> str:
    """Compute SHA-256 hash of a CLI command's schema slice.

    The schema slice is serialized to JSON with sorted keys for
    deterministic hashing.  This captures help text, flags, args,
    and any other schema fields for a single command or group.
    """
    serialized = json.dumps(schema_slice, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def check_schema_drift(
    page_path: str,
    schema_hash: str | None,
    description_hash: str,
    stored_hashes: dict,
) -> str | None:
    """Check whether a CLI page's description drifted from its schema slice.

    Returns an error message if the command's schema slice changed but the
    page description did not.  Returns None otherwise (no schema hash,
    new page, first run with schema tracking, unchanged schema, or
    description was updated alongside schema changes).
    """
    if schema_hash is None:
        return None
    if page_path not in stored_hashes:
        return None
    stored = stored_hashes[page_path]
    if "schema_hash" not in stored:
        return None
    if schema_hash == stored["schema_hash"]:
        return None
    if description_hash != stored.get("description"):
        return None
    return (
        f"{page_path}: CLI schema changed but page description "
        f"was not updated (possible stale CLI description)"
    )


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


def check_drift(
    page_path: str,
    source_docstring_hash: str | None,
    description_hash: str,
    stored_hashes: dict,
) -> str | None:
    """Check whether a page's description drifted from source docstrings.

    Returns an error message if the source docstrings changed but the
    page description did not. Returns None otherwise (no source docstrings,
    new page, first run with drift tracking, unchanged source, or
    description was updated alongside source changes).
    """
    if source_docstring_hash is None:
        return None
    if page_path not in stored_hashes:
        return None
    stored = stored_hashes[page_path]
    if "source_docstring" not in stored:
        return None
    if source_docstring_hash == stored["source_docstring"]:
        return None
    if description_hash != stored.get("description"):
        return None
    return (
        f"{page_path}: source docstrings changed but page description "
        f"was not updated (possible documentation drift)"
    )


def compute_current_hashes(all_docs, base_dir=".", page_directives=None,
                           schema_hashes=None):
    """Compute the full current hash dict for every documentation page.

    Returns a dict mapping rel_path to a hash dict with ``content`` and
    ``description`` keys (always), plus ``source_docstring`` and
    ``schema_hash`` when the corresponding inputs are provided.  This is
    the baseline a page WOULD receive if it had no outstanding errors --
    it does not read or write ``.selfdoc/hashes/hashes.json`` and performs
    no staleness/drift comparison.

    Args:
        all_docs: Dict from resolve_all_docs {rel_path: (fm, resolved, raw, fm_lines)}
        base_dir: Project root (used to resolve source file paths).
        page_directives: Optional dict mapping rel_path to a list of
            resolved directive objects (see update_hashes).  When provided,
            source docstring hashes are computed.
        schema_hashes: Optional dict mapping rel_path to a schema hash
            string (for CLI pages gated on their command's schema slice).

    Returns:
        Dict mapping rel_path to its current hash dict.
    """
    current_hashes: dict[str, dict] = {}

    for rel_path in sorted(all_docs):
        metadata, resolved_content, _raw, _fm_lines = all_docs[rel_path]
        description = metadata.get("description")
        if description is None:
            continue
        current_hashes[rel_path] = {
            "content": compute_content_hash(resolved_content),
            "description": compute_description_hash(str(description)),
        }

    if page_directives is not None:
        for rel_path in sorted(all_docs):
            if rel_path not in page_directives:
                continue
            directives = page_directives[rel_path]
            source_files = []
            for rd in directives:
                source_entry = getattr(rd, "source_entry", None)
                if source_entry is None:
                    continue
                path_arg = rd.attrs.get("path", "")
                if not path_arg:
                    continue
                resolved_path = source_entry.extractor.resolve_path(
                    path_arg, [source_entry.path], base_dir,
                )
                if resolved_path is not None and (os.path.isfile(resolved_path) or os.path.isdir(resolved_path)):
                    source_files.append((resolved_path, source_entry.extractor))
            if not source_files:
                continue
            sd_hash = compute_source_docstring_hash(source_files)
            if sd_hash is not None and rel_path in current_hashes:
                current_hashes[rel_path]["source_docstring"] = sd_hash

    if schema_hashes is not None:
        for rel_path, s_hash in schema_hashes.items():
            if rel_path in current_hashes:
                current_hashes[rel_path]["schema_hash"] = s_hash

    return current_hashes


def update_hashes(all_docs, base_dir=".", dry_run=False, page_directives=None,
                  schema_hashes=None):
    """Compute content and description hashes for all docs and save.

    Args:
        all_docs: Dict from resolve_all_docs {rel_path: (fm, resolved, raw, fm_lines)}
        base_dir: Project root
        dry_run: If True, compute but don't write to disk
        page_directives: Optional dict mapping rel_path to a list of
            resolved directive objects (each has .attrs with "path" key,
            and .source_entry with .language and .extractor attributes).
            When provided, source docstring hashes are computed and drift
            detection is performed.
        schema_hashes: Optional dict mapping rel_path to a schema hash
            string (for CLI pages gated on their command's schema slice).

    Returns:
        Tuple of (stale_warnings, drift_warnings), each a list of
        (rel_path, message) tuples.
    """
    stored_hashes = load_hashes(base_dir)
    current_hashes = compute_current_hashes(
        all_docs, base_dir, page_directives, schema_hashes,
    )
    stale_warnings = []

    for rel_path in sorted(current_hashes):
        hashes = current_hashes[rel_path]
        stale_msg = check_staleness(
            rel_path, hashes["content"], hashes["description"], stored_hashes,
        )
        if stale_msg is not None:
            stale_warnings.append((rel_path, stale_msg))

    drift_warnings = []

    if page_directives is not None:
        for rel_path in sorted(current_hashes):
            sd_hash = current_hashes[rel_path].get("source_docstring")
            if sd_hash is None:
                continue
            d_hash = current_hashes[rel_path]["description"]
            drift_msg = check_drift(rel_path, sd_hash, d_hash, stored_hashes)
            if drift_msg is not None:
                drift_warnings.append((rel_path, drift_msg))

    # CLI schema-hash gating: for CLI pages, check whether the command's
    # schema slice changed without a corresponding description update.
    if schema_hashes is not None:
        for rel_path, s_hash in schema_hashes.items():
            d_hash = current_hashes.get(rel_path, {}).get("description")
            if d_hash is not None:
                schema_msg = check_schema_drift(
                    rel_path, s_hash, d_hash, stored_hashes,
                )
                if schema_msg is not None:
                    drift_warnings.append((rel_path, schema_msg))

    # Pages with staleness or drift errors keep their old baseline so the
    # error persists until the description is actually rewritten.  All hash
    # fields for a held page stay frozen (per-page-all-fields atomic hold).
    error_pages = {rp for rp, _ in stale_warnings} | {rp for rp, _ in drift_warnings}
    for rel_path, hashes in current_hashes.items():
        if rel_path in error_pages:
            continue  # do not advance baseline for pages with errors
        stored_hashes[rel_path] = hashes
    if not dry_run:
        save_hashes(stored_hashes, base_dir)

    return stale_warnings, drift_warnings


def _strip_frontmatter(content: str) -> str:
    """Strip YAML frontmatter from content, returning only the body."""
    if not content.startswith("---"):
        return content
    lines = content.split("\n")
    for idx in range(1, len(lines)):
        if lines[idx].strip() == "---":
            return "\n".join(lines[idx + 1:]).lstrip("\n")
    return content
