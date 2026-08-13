#!/usr/bin/env python3
"""Build the conformance fixture site and report tinymoon violations.

The same fixture ``tests/test_tinymoon_conformance.py`` asserts on, printed
as a grouped table instead of an assertion.  This is the working loop while
a violation class is being chased to zero: it says which file and which
rule, and with ``--detail`` it prints every message.

    python scripts/tm_conformance_report.py
    python scripts/tm_conformance_report.py --rule raw-color --detail
"""

from __future__ import annotations

import argparse
import collections
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tests"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rule", default="", help="only this rule")
    parser.add_argument("--path", default="", help="only paths containing this")
    parser.add_argument("--detail", action="store_true", help="print each message")
    parser.add_argument("--site", default="", help="scan this built site instead")
    args = parser.parse_args()

    from tinymoon.checker import scan_dir

    if args.site:
        site = args.site
    else:
        import tempfile

        from test_tinymoon_conformance import build_conformance_fixture

        site = build_conformance_fixture(tempfile.mkdtemp(prefix="tm-conf-"))

    violations = scan_dir(site)
    if args.rule:
        violations = [v for v in violations if v.rule == args.rule]
    if args.path:
        violations = [v for v in violations if args.path in v.path]

    by_rule: collections.Counter = collections.Counter(v.rule for v in violations)
    by_file: collections.Counter = collections.Counter(
        (v.path, v.rule) for v in violations
    )

    print(f"site: {site}")
    print(f"total: {len(violations)}")
    print("\nby rule:")
    for rule, count in by_rule.most_common():
        print(f"  {count:5d}  {rule}")
    print("\nby file+rule:")
    for (path, rule), count in by_file.most_common(60):
        print(f"  {count:5d}  {rule:16s} {path}")
    if args.detail:
        print("\ndetail:")
        seen: collections.Counter = collections.Counter()
        for v in violations:
            seen[v.message] += 1
        for message, count in seen.most_common():
            print(f"  {count:5d}  {message}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
