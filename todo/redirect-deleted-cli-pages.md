# Add redirect support for deleted/renamed CLI doc pages

## Problem

When rlsbl renames or moves CLI commands (e.g., `edit-release` → `release edit`), the corresponding doc page URL changes (`cli-edit-release.html` → part of `cli-release.html`). The old URL returns 404 on Cloudflare Pages. Anyone who bookmarked or linked to the old page gets a dead link.

## Proposed solution

Add a redirect mechanism to selfdoc's build/deploy pipeline. Options:

1. **Cloudflare Pages `_redirects` file**: A `_redirects` file in the build output with lines like `/cli-edit-release.html /cli-release.html 301`. Cloudflare Pages supports this natively.
2. **HTML meta refresh**: Generate a small HTML file at the old path with a `<meta http-equiv="refresh">` tag pointing to the new URL.
3. **selfdoc.json config**: A `redirects` key in `selfdoc.json` mapping old paths to new paths, processed during `selfdoc gen`.

## Context

Discovered during rlsbl v0.42.0+ when `edit-release`, `undo`, and `yank` were moved into the `release` command group, causing their standalone doc pages to be removed.

## Effort

Small. The `_redirects` file approach requires no code changes to selfdoc — just documentation of the convention. A built-in mechanism (option 3) is more work but more maintainable.
