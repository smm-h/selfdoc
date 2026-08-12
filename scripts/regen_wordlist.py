#!/usr/bin/env python3
"""Regenerate the vendored English word list under ``selfdoc_core/wordlist/``.

The spelling checker's acceptance oracle is a pinned snapshot of the English
Speller Database (ESDB, formerly SCOWL), retrieved from the project's own
custom-list generator at https://app.aspell.net/create with the exact
parameters recorded below.  This script is the only sanctioned way to
refresh that snapshot: it writes the three vendored files together, so the
words, the upstream copyright and the retrieval record can never disagree.

What it writes into ``selfdoc_core/wordlist/``:

- ``words.txt`` -- one word per line, upstream order, no header.
- ``COPYRIGHT.txt`` -- the upstream ``Copyright`` file, verbatim, fetched
  from the pinned ESDB release tag.  It carries the sub-source notices
  (UKACD, Australian English, WordNet) that upstream requires to be
  displayed, so shipping it verbatim is what makes redistribution legal.
- ``SOURCE.json`` -- the retrieval record: generator URL, every parameter,
  the ESDB and app git revisions the generator reported, the pinned release
  tag the copyright came from, the SHA-256 of ``words.txt`` and its word
  count.

Requires network access.  Read-only with respect to everything except the
three files it writes.

Usage:
    python scripts/regen_wordlist.py [--check]

``--check`` re-fetches and compares against the vendored snapshot without
writing, exiting non-zero when upstream has moved.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import urllib.request
from datetime import date

# The generator endpoint and the exact parameter set the snapshot was built
# with.  Every value is a deliberate choice:
#
# - ``max_size=70`` is the "large" level.  Size 35/50 flag ordinary English
#   ("subdirectory" is absent below 70); size 80+ starts admitting material
#   too obscure to serve as an acceptance oracle, and upstream's copyright
#   attaches the UKACD clause to generated lists larger than 80.
# - Four spellings (US, British -ise, British -ize, Canadian) because fleet
#   documentation is written in all of them and a spelling difference is not
#   a misspelling.
# - ``variant_level=1`` is upstream's default: primary spellings plus their
#   common variants, without the disputed and archaic tiers.
# - ``diacritic=both`` accepts "naive" and "naïve" alike.
# - The hacker and roman-numeral special lists are upstream's defaults and
#   both earn their place in technical documentation.
GENERATOR_URL = "http://app.aspell.net/create"
GENERATOR_PARAMS: list[tuple[str, str]] = [
    ("max_size", "70"),
    ("spelling", "US"),
    ("spelling", "GBs"),
    ("spelling", "GBz"),
    ("spelling", "CA"),
    ("variant_level", "1"),
    ("diacritic", "both"),
    ("special", "hacker"),
    ("special", "roman-numerals"),
    ("encoding", "utf-8"),
    ("format", "inline"),
    ("download", "wordlist"),
]

# The ESDB source release the verbatim copyright is taken from.  Pinned to a
# tag, never a branch: the notice shipped beside the words must be the notice
# that governed them.
ESDB_REPO_TAG = "rel-2026.02.25"
COPYRIGHT_URL = (
    f"https://raw.githubusercontent.com/en-wl/wordlist/{ESDB_REPO_TAG}/Copyright"
)

# The generator separates its header from the words with a lone "---".
_HEADER_SEPARATOR = "---"

_TIMEOUT = 180

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_WORDLIST_DIR = os.path.join(_REPO_ROOT, "selfdoc_core", "wordlist")


def _generator_url() -> str:
    """Build the fully-parameterized generator URL."""
    query = "&".join(f"{key}={value}" for key, value in GENERATOR_PARAMS)
    return f"{GENERATOR_URL}?{query}"


def _fetch(url: str) -> str:
    """Fetch *url* as UTF-8 text."""
    with urllib.request.urlopen(url, timeout=_TIMEOUT) as response:  # noqa: S310
        return response.read().decode("utf-8")


def _split_payload(payload: str) -> tuple[list[str], list[str]]:
    """Split the generator response into (header lines, word lines)."""
    lines = payload.split("\n")
    try:
        cut = lines.index(_HEADER_SEPARATOR)
    except ValueError:
        raise SystemExit(
            "the generator response carries no '---' header separator; "
            "the endpoint's output format changed and this script needs "
            "updating before the snapshot can be trusted"
        ) from None
    header = [line for line in lines[:cut]]
    words = [line for line in lines[cut + 1:] if line]
    if len(words) < 50_000:
        raise SystemExit(
            f"the generator returned only {len(words)} words, far below the "
            "expected size for these parameters -- refusing to vendor a "
            "truncated snapshot"
        )
    return header, words


def _revision(header: list[str], label: str) -> str:
    """Pull a ``<label>: <value>`` line out of the generator header."""
    prefix = f"{label}:"
    for line in header:
        if line.startswith(prefix):
            return line[len(prefix):].strip()
    return ""


def main(argv: list[str]) -> int:
    """Fetch upstream and either write or verify the vendored snapshot."""
    check_only = "--check" in argv[1:]

    payload = _fetch(_generator_url())
    header, words = _split_payload(payload)
    copyright_text = _fetch(COPYRIGHT_URL)

    words_blob = "\n".join(words) + "\n"
    digest = hashlib.sha256(words_blob.encode("utf-8")).hexdigest()

    record = {
        "source": "English Speller Database (ESDB, formerly SCOWL)",
        "home": "https://wordlist.aspell.net",
        "generator_url": GENERATOR_URL,
        "generator_params": [list(pair) for pair in GENERATOR_PARAMS],
        "esdb_git_revision": _revision(header, "ESDB Git Revision"),
        "app_git_revision": _revision(header, "App Git Revision"),
        "copyright_source": COPYRIGHT_URL,
        "copyright_tag": ESDB_REPO_TAG,
        "retrieved": date.today().isoformat(),
        "word_count": len(words),
        "words_sha256": digest,
        "generator_header": header,
        "regenerate_with": "python scripts/regen_wordlist.py",
    }

    words_path = os.path.join(_WORDLIST_DIR, "words.txt")
    copyright_path = os.path.join(_WORDLIST_DIR, "COPYRIGHT.txt")
    record_path = os.path.join(_WORDLIST_DIR, "SOURCE.json")

    if check_only:
        with open(record_path, "r", encoding="utf-8") as f:
            vendored = json.load(f)
        drifted = []
        if vendored.get("words_sha256") != digest:
            drifted.append(
                f"words.txt: vendored {vendored.get('words_sha256')} "
                f"!= upstream {digest}"
            )
        with open(copyright_path, "r", encoding="utf-8") as f:
            if f.read() != copyright_text:
                drifted.append("COPYRIGHT.txt differs from upstream")
        for line in drifted:
            print(line, file=sys.stderr)
        if drifted:
            print(
                "upstream has moved; rerun without --check to re-vendor",
                file=sys.stderr,
            )
            return 1
        print(f"snapshot matches upstream ({len(words)} words)")
        return 0

    os.makedirs(_WORDLIST_DIR, exist_ok=True)
    with open(words_path, "w", encoding="utf-8") as f:
        f.write(words_blob)
    with open(copyright_path, "w", encoding="utf-8") as f:
        f.write(copyright_text)
    with open(record_path, "w", encoding="utf-8") as f:
        json.dump(record, f, indent=2, ensure_ascii=False)
        f.write("\n")

    print(f"wrote {len(words)} words to {words_path}")
    print(f"wrote upstream copyright to {copyright_path}")
    print(f"wrote retrieval record to {record_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
