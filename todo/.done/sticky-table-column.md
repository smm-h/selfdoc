# Sticky first column on wide tables

## Problem

When a table overflows horizontally in `.table-wrap`, scrolling right hides the first column (usually row labels). Users lose context about which row they're reading.

## Proposed solution

Add CSS for sticky first column:

```css
.table-wrap th:first-child,
.table-wrap td:first-child {
    position: sticky;
    left: 0;
    background: var(--bg);
    z-index: 1;
    border-right: 1px solid var(--border);
}
```

Considerations:
- The sticky column needs an explicit background to cover scrolling content behind it.
- Dark mode needs the correct `--bg` value (already handled by CSS variable).
- Striped rows need the first cell to have the striped background, not `--bg` — may need `tr:nth-child(even) td:first-child { background: var(--code-bg); }`.
- This should only apply to tables wide enough to overflow. Could use a JS-based `has-overflow` class (already implemented for scroll affordances) to conditionally apply.

## Affected files

- `selfdoc/themes/minimal.css` — sticky first column CSS

## Effort

Low. Pure CSS with a few edge cases for row striping and dark mode.
