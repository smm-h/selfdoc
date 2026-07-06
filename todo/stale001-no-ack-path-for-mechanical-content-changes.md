# STALE001/DRIFT001: no legitimate clearing path for mechanical, semantics-preserving content changes

## Context

Commit `200a0bf` ("staleness: baseline does not advance while errors are outstanding") made STALE001/DRIFT001 sticky: pages with outstanding errors keep their old baseline in `.selfdoc/hashes/hashes.json`, so re-running `selfdoc check` no longer self-heals. Per `docs/staleness.md` ("Fixing It"), the only documented way to clear the error is to update the frontmatter `description`.

This creates a dead end for a whole class of changes: **mechanical, semantics-preserving edits to page bodies** — most notably updating `ref path="..."` directive attributes to the current canonical page-naming convention (as required after the XREF002 naming tightening in 0.26.x). The page's meaning is unchanged, the description is still accurate, yet STALE001 fires and cannot be honestly cleared:

- Rewording an already-accurate description just to flip the description hash is fabrication — gaming the guardrail, exactly what the check exists to prevent.
- Hand-editing `hashes.json` bypasses the guardrail.
- `lint_ignore: ["STALE001"]` disables staleness detection permanently for the whole project — an escape hatch, not a fix.

DRIFT001 has the same failure mode: fixing a directive path so it now resolves to (or resolves differently to) source files changes the concatenated source-docstring hash, firing "source docstrings changed" even though no docstring changed — only the *set of resolved refs* changed due to the mechanical path update.

## Repro

1. In a project with staleness tracking active (hashes.json baselines recorded), take a hand-authored page with an accurate frontmatter description and one or more `:-: ref path="old.name"` directives.
2. Rename the directive paths to the canonical form (`sourcedir.old.name`) — e.g. to fix XREF002 after upgrading to 0.26.1. Change nothing else.
3. Run `selfdoc check` — STALE001 fires for the page (content hash changed, description hash unchanged).
4. Run `selfdoc check` again — error persists (baseline held). There is no operation that clears it without dishonestly editing the description or bypassing the hash store.

Observed at scale: a consumer project that mechanically updated a few hundred directive paths across ~20 hand-authored pages got ~20 sticky STALE001 errors plus 2 DRIFT001, hard-blocking its release pipeline (release flow runs `selfdoc check` and aborts on exit 1), with no compliant way forward.

## Expected vs actual

- **Expected:** a semantics-preserving change to directive plumbing (path attributes that resolve to the same modules) should either not perturb the content hash, or there should be an honest, auditable way to record "description re-verified against new content, still accurate."
- **Actual:** STALE001/DRIFT001 fire and persist forever; the only documented remedy is to reword a description that needs no rewording.

## Affected code paths

- `selfdoc/staleness.py` — `compute_content_hash` (hashes resolved content including directive-path-derived text), `check_staleness`, `check_drift`, and the baseline-hold block at the end of `update_hashes` (error pages excluded from baseline advance).
- `selfdoc/check.py` — STALE001/DRIFT001 emission around the `update_hashes` call.
- `docs/staleness.md` — "Fixing It" documents description-rewording as the only path.
- Same structural question applies to the new CLI schema-hash gating (`check_schema_drift`).

## Possible solutions

1. **Normalize hashed content so directive-path renames are invisible** (recommended direction). Compute the content hash from the resolved page body with directive-identity markup (path strings, path-derived anchors/headings/links) canonicalized or excluded — hash what the reader semantically sees, keyed by resolved target module rather than by path spelling. Same for the drift hash: key docstring hashes by resolved file path set, not by which spelling of the ref found them (this one may already hold; the DRIFT001 trigger here was the ref set changing from partially-unresolvable to fully-resolvable).
   - Pros: makes the false-positive class structurally impossible; no new commands; no escape hatch.
   - Cons: needs careful definition of "semantic content"; a one-time baseline migration; risk of under-hashing (missing real changes) if normalization is too aggressive.
2. **Explicit, auditable re-verification marker in the page itself**, e.g. frontmatter `description_verified: <content-hash-prefix>` that the author must set to the *current* content hash (check tells them the value). Clearing the error requires touching the page with a value tied to the exact content state — deliberate, reviewable in diffs, and self-invalidating on the next content change.
   - Pros: honest ack path for any false positive, not just path renames; forces per-page deliberate action; leaves an audit trail.
   - Cons: it is still an ack mechanism agents could reflexively apply; mitigate by making check print the required value only alongside the full description so the agent must re-read it.
3. **Do nothing / require description rewording always.** Rejected: forces fabricated edits, which trains agents to game the check and degrades description quality.

Options 1 and 2 are complementary; 1 fixes this class, 2 covers any residual false positives.

## Effort estimate

- Option 1: ~0.5-1 day (hash normalization + tests + baseline migration note in docs/staleness.md).
- Option 2: ~0.5 day (frontmatter field, check plumbing, docs, tests).
