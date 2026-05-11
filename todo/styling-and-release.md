# Styling overhaul and release loose ends

Status: In progress
Priority: High

## Context

50 documentation site features were implemented in a single session. The structural features work (layout, search, TOC, dark mode, etc.) but the visual quality is still not right — the user described the output as "still ugly" after every batch. The fundamental CSS styling needs focused attention separate from feature additions.

## Styling work needed

- Full visual audit with the user present — identify what specifically looks wrong (typography, spacing, colors, alignment, proportions)
- Likely needs a ground-up CSS rewrite guided by visual feedback, not feature checklists
- The CSS is now 1233 lines accumulated across 5 batches — may have conflicting rules, inconsistent spacing, or rules that override each other

## Release loose ends

- v0.2.0 npm publish failed (NPM_TOKEN secret now set on repo, but the failed CI run needs to be rerun or a new release cuts it)
- All 50 features are committed locally but not released — needs a selfdoc release
- 8 Cloudflare Pages sites (migrable, go-toml-edit, safegit, howmuchleft, claudewheel, codehome, predraw, selfdoc) have stale content deployed from before the 50-feature overhaul
- The `docs` rlsbl target tries `selfdoc deploy` during release and fails with a warning because env vars aren't sourced in that context — the post-release hook handles it correctly, but the warning is noisy

## Post-release hook standardization

8 projects have standardized hooks committed but not pushed:
- migrable, selfdoc, go-toml-edit, safegit, howmuchleft, claudewheel, codehome, predraw
- Each needs a `git push` (no release needed, just sync)

## Cleanup needed

chessmmo and ProductEngine had selfdoc files committed (selfdoc.json, docs/index.md, .gitignore additions, post-release hook changes) when their Pages projects were set up, but the Pages projects were later deleted. The committed files are orphaned and should be reverted.

## Effort estimate

- Styling: 1-2 sessions of iterative visual feedback
- Release + redeploy: ~15 min
- Push hooks: ~5 min (one loop)
- Cleanup chessmmo/ProductEngine: ~10 min
