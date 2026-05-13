# Reading progress indicator

## Problem

When reading a long documentation page, users have no visual indicator of how far they've scrolled. The topbar has a decorative gradient strip but no progress bar.

## Proposed solution

Add a thin (2-3px) progress bar at the very top of the viewport (above or overlapping the topbar) that fills from left to right as the user scrolls. Use the accent color (`var(--link)`).

Implementation:
1. Add a `<div class="scroll-progress" id="scroll-progress">` as the first child of `<body>`.
2. CSS: `position: fixed; top: 0; left: 0; height: 3px; background: var(--link); z-index: 1001; transition: width 50ms;`
3. JS: on scroll, compute `scrollTop / (scrollHeight - clientHeight) * 100` and set `width` as percentage.
4. Make it opt-in via config or always-on since it's non-intrusive.

## Affected files

- `selfdoc/html.py` — HTML element + JS block
- `selfdoc/themes/minimal.css` — `.scroll-progress` styling

## Effort

Low. Simple scroll handler + a single div.
