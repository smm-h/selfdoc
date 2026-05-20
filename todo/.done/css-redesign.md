# CSS redesign: multi-theme support

## Status: In progress | Priority: High | Effort: Large

## Problem

The minimal theme CSS has grown to 2153 lines across many feature additions. The visual quality needs improvement. The settings panel in `demo/index.html` is built as a design iteration tool with 21 knobs, but no CSS redesign has been done using it yet.

## Plan

1. Decouple hardcoded values from HTML template (fonts, accent color)
2. Create a "clean" Stripe-like theme as the first alternative to minimal
3. Build-time theme selection via `"theme"` config field (already works)
4. Ship with 0.4.0 release

## Architecture notes

- Theme registry at `selfdoc/themes/__init__.py` auto-discovers `.css` files
- CSS split at `/* --- NON-CRITICAL --- */` marker for critical CSS inlining
- New themes must style the same HTML class names (.topbar, .sidebar, .layout, etc.)
- New themes must handle `[data-theme='dark']` for light/dark toggle
- Fonts are currently hardcoded in HTML template — need to be made theme-configurable
- Accent color hardcoded in Python (favicon, OG cards) — needs extraction

## Design tool

`demo/index.html` has a 21-knob settings panel for CSS iteration. Serve with `python3 -m http.server` from project root and open `/demo/index.html`.

## Progress

Completed in this session:

1. **Clean theme contrast fixed** -- accent color changed from `#635bff` to `#5046e4`; all color pairs now pass WCAG AA contrast requirements.
2. **High-contrast overrides** -- `prefers-contrast: more` media query added for both themes, covering all key CSS custom properties.
3. **SEO012 extended** -- the SEO check now also validates user `custom.css` overrides (not just built-in theme CSS).
4. **Demo page** -- `demo/index.html` created with a theme switcher supporting minimal and clean themes.
5. **Theme metadata system** -- `selfdoc/themes/__init__.py` and per-theme `.json` metadata files are in place.

## Remaining

- Fonts still hardcoded in HTML template (plan item 1 not fully addressed)
- Accent color still hardcoded in Python for favicon/OG card generation (plan item 1)
- No CSS redesign pass using the 21-knob design tool has been done yet (original problem statement)
- Ship with 0.4.0 release (plan item 4)
