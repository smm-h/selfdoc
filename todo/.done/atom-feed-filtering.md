# Atom feed filtering

## Problem

`_generate_atom_feed` includes all pages in the feed. Users subscribed to the feed get notified about every page, even those that haven't changed. There is no way to exclude pages (e.g., auto-generated glossary, changelog) or limit the feed to recently modified pages.

## Proposed solution

Two mechanisms:

1. **Frontmatter exclusion**: Pages with `exclude_from_feed: true` in frontmatter are omitted from the feed.
2. **Recent-only mode**: Add a config option `feed_max_entries: 20` (default: all) that limits the feed to the N most recently modified pages, sorted by `dateModified` descending.

## Affected files

- `selfdoc/build.py` — `_generate_atom_feed` filtering logic
- `selfdoc/config.py` — `feed_max_entries` config validation

## Effort

Low. Filter logic in the existing iteration loop, plus one config key.
