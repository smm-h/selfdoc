# Coverage should measure documentation quality, not just symbol references

## Problem

Running `selfdoc gen` creates auto-generated pages with `:-: ref path="module"` directives. These pages have zero human-written content — just the raw extracted API surface. Yet `selfdoc check` counts every symbol on those pages as "documented," inflating coverage to 100%.

Coverage should measure how much meaningful documentation exists (the meat), not how many symbols are mechanically referenced by a directive (the bone). Currently the metric is gameable by running `selfdoc gen` and never writing a word of explanation.

## What "documented" should mean

A symbol is truly documented when a human has written context around it: a description of what it does and why, usage examples, caveats, or relationships to other parts of the system. A symbol that only appears in auto-generated `ref` output is *referenced*, not *documented*.

## Proposed approach

Distinguish two tiers:

- **Referenced**: a directive points at this symbol. This is what coverage measures today.
- **Documented**: the page containing the symbol has been meaningfully edited beyond the auto-generated template.

Heuristics for "meaningfully edited":

1. **Description customized**: the page's `description` frontmatter differs from the auto-generated default ("API reference for X"). The `selfdoc gen` system already tracks this — `generated: true` pages with default descriptions haven't been touched.
2. **Content beyond the directive**: the page has prose paragraphs, headings, or examples outside the `ref` directive block. A page that's just frontmatter + one directive is skeleton.
3. **`generated: true` discount**: symbols on pages with `generated: true` and no customization count as referenced, not documented. Symbols on pages where `generated: true` but the description was customized (the preservation logic already detects this) count as documented.

## Reporting

`selfdoc check` could report both numbers:

```
Coverage: 55/67 public symbols documented (82%)
          67/67 public symbols referenced (100%)
```

`min_coverage` would check the documented number, not the referenced number.

## Affected files

- `selfdoc/check.py` — `_compute_coverage` needs the new heuristic
- `selfdoc/gen.py` — already tracks `generated: true` and description customization
- `selfdoc/docs.py` — `resolve_all_docs` already provides frontmatter

## Effort

Medium. The data is already available (generated marker, description customization). The main work is defining the heuristic precisely and updating the coverage computation.
