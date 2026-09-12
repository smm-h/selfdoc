#!/usr/bin/env python3
"""Record the exact bytes the Python writes for a hash store and a manifest.

The Go ports of ``selfdoc_core.staleness`` and ``selfdoc_core.manifest``
reproduce these two documents byte for byte -- the hash store because a
changed byte re-baselines every page in every repository, the manifest
because the assembly reads it and a reordered key rewrites every project's
committed copy. Rather than hand-transcribing the bytes, this writes what the
Python implementation actually produces into the Go packages' testdata, so the
expectation is always a recorded observation.

The Go tests rebuild the same two inputs in Go. Both inputs are defined here;
keep the two sides in step.

Run from the repository root:

    UV_NO_SYNC=1 uv run python scripts/record_staleness_manifest_bytes.py
"""

import json
import os
import tempfile

from selfdoc_core.manifest import generate_manifest
from selfdoc_core.staleness import save_hashes

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# One page per field combination the store can hold, plus a non-ASCII key and
# a locale-prefixed key, so the recorded bytes pin the key sort order and the
# ensure_ascii escaping as well as the field order.
HASH_STORE = {
    "en/index.md": {
        "content": "a" * 64,
        "description": "b" * 64,
    },
    "en/cli-build.md": {
        "content": "c" * 64,
        "description": "d" * 64,
        "schema_hash": "e" * 64,
        "seed_hash": "f" * 64,
    },
    "en/référence.md": {
        "content": "1" * 64,
        "description": "2" * 64,
        "source_docstring": "3" * 64,
    },
}

MANIFEST_CONFIG = {
    "name": "Récord Project",
    "topology": {"slug": "record-project"},
    "version": "1.2.3",
    "description": 'A project with a "quoted" description — and an em dash.',
    "source": [{"path": "src/", "language": "python"}],
    "base_url": "https://example.com",
    "theme": "brutalist",
}

GUIDE_PAGE = (
    "# Guide\n"
    "\n"
    "Intro.\n"
    "\n"
    "## Setup\n"
    "\n"
    "One.\n"
    "\n"
    "## Setup\n"
    "\n"
    "Two.\n"
    "\n"
    "### Déeper\n"
    "\n"
    "```python\n"
    "# not a heading\n"
    "```\n"
)

MANIFEST_PAGES = {
    "guide.md": ({"type": "tutorial"}, GUIDE_PAGE, GUIDE_PAGE, 0),
    "api.md": ({"title": "API Réference"}, "Just a paragraph.\n",
               "Just a paragraph.\n", 0),
}

MANIFEST_POSTS = [
    {
        "path": "posts/hello.md",
        "title": "Hello, wörld",
        "date": "2026-01-02",
        "slug": "hello-world",
        "tags": ["news", "release"],
    },
    {
        "path": "posts/bare.md",
        "title": "Bare",
        "date": "2026-01-03",
        "slug": "bare",
        "tags": [],
    },
]


def record_hash_store():
    """Write the hash store's recorded bytes into the staleness testdata."""
    with tempfile.TemporaryDirectory() as tmp:
        save_hashes(json.loads(json.dumps(HASH_STORE)), tmp)
        with open(os.path.join(tmp, ".selfdoc", "hashes", "hashes.json"),
                  "rb") as handle:
            recorded = handle.read()
    target = os.path.join(
        REPO_ROOT, "internal", "staleness", "testdata", "python_hashes.json",
    )
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(target, "wb") as handle:
        handle.write(recorded)
    print(f"wrote {target} ({len(recorded)} bytes)")


def record_manifest():
    """Write the manifest's recorded bytes into the manifest testdata."""
    with tempfile.TemporaryDirectory() as tmp:
        generate_manifest(
            MANIFEST_CONFIG, MANIFEST_PAGES, posts_data=MANIFEST_POSTS,
            dir_path=tmp,
        )
        with open(os.path.join(tmp, ".selfdoc", "manifest.json"), "rb") as handle:
            recorded = handle.read()
    target = os.path.join(
        REPO_ROOT, "internal", "manifest", "testdata", "python_manifest.json",
    )
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(target, "wb") as handle:
        handle.write(recorded)
    print(f"wrote {target} ({len(recorded)} bytes)")


if __name__ == "__main__":
    record_hash_store()
    record_manifest()
