#!/usr/bin/env python3
"""Emit the reference backtick-span verdicts the Go scanner is tested against.

The Python surface finds code spans with a regex the Go regexp engine cannot
express (a backreference plus lookaround), so the Go port replaces it with a
hand scanner. This script generates the differential corpus: for each input
line it prints the masked form, the blanked form, and each span's offsets, as
the Python regex sees them. Run it from the repository root and paste the
output into internal/directives/scanner_test.go's table when the corpus grows.

    PYTHONPATH=. python3 scripts/backtick_span_corpus.py
"""

import itertools
import json
import sys

from selfdoc_core.directives import (
    BACKTICK_SPAN_RE,
    _mask_backtick_spans,
    blank_backtick_spans,
)

CASES = [
    "",
    "no spans here",
    "`a`",
    "``a``",
    "```a```",
    "`a`` b",
    "`a``",
    "``a`",
    "`` ` ``",
    "a `b` c `d` e",
    "`unclosed",
    "```` a ``` b ````",
    "``a``b``c``",
    "`a\nb`",
    "text `` `x` `` more",
    "`:-: var key=\"x\"`",
    "``:-: var``",
    "`single` and ``double :-: var`` then :-: ref end",
    "`",
    "``",
    "```",
    "`a` `b",
    "x``y``z",
    "``` `` ```",
]
# Every short string over {`, a} up to length 6, so the closing-run and
# retry-with-a-shorter-opener rules are exercised exhaustively.
for n in range(1, 7):
    for combo in itertools.product("`a", repeat=n):
        CASES.append("".join(combo))


def main() -> int:
    out = []
    for line in CASES:
        spans = [
            {
                "start": m.start(),
                "end": m.end(),
                "content_start": m.start(2),
                "content_end": m.end(2),
                "fence": len(m.group(1)),
            }
            for m in BACKTICK_SPAN_RE.finditer(line)
        ]
        masked, placeholders = _mask_backtick_spans(line)
        out.append(
            {
                "line": line,
                "spans": spans,
                "masked": masked,
                "placeholders": placeholders,
                "blanked": blank_backtick_spans(line),
            }
        )
    json.dump(out, sys.stdout, indent=1, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
