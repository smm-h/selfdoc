# Version-only content changes trip STALE001 on every release

## Context

Pages that embed the project version in their generated content (observed with a strictcli-generated CLI index page, which renders the current version) change their content hash on every release: the release flow's schema dump regenerates the page with the new version string before selfdoc check runs. STALE001 compares content-hash change against description-hash change, sees content moved while the description did not, and flags possible staleness.

## Problem

The staleness signal fires on every single release of an affected project, even though nothing semantically changed — the only delta is the version number. Observed twice in a row on consecutive releases of the same consumer project; each time the release aborted at the selfdoc gate and required a manual `selfdoc baseline accept` (or a make-work description edit) to proceed. A check that cries wolf on every release trains operators and agents to reflexively accept baselines, which erodes the value of STALE001 for catching real staleness.

## Solutions

1. **Exclude version-like tokens from the content hash** (recommended). Normalize content before hashing: strip or canonicalize substrings matching the project's current version (selfdoc knows it from its config sync) so version-only regeneration is hash-stable. Pros: fixes the class for all pages, zero per-project config. Cons: normalization must be careful not to mask a genuine content change that happens to contain the version string; scoping the normalization to exact current-version matches keeps this tight.
2. **Page-level opt-out of content-staleness for version-bearing generated pages.** A frontmatter or config flag marking a page as version-volatile. Pros: explicit. Cons: per-page config that consumers must discover exactly by hitting the failure; the flag is close to an escape hatch.
3. **Release-flow awareness.** When invoked in the release pipeline (the caller could signal it), treat a content delta that consists solely of the old-version to new-version substitution as non-stale. Pros: precisely targets the observed trigger. Cons: requires an orchestration handshake with the release tool; narrower than option 1.

## Affected files

- The staleness check implementation (content hashing in selfdoc_core/staleness.py or equivalent)
- Possibly the strictcli-support page generator (whether the version needs to be in the content at all is worth a look — removing it from the generated index body would also fix this specific page)

## Effort

Small to moderate: hashing normalization plus tests reproducing the version-bump scenario (generate at version A, accept, regenerate at version B with no other changes, assert no STALE001).
