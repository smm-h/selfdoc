---
title: Staleness Detection
description: "How selfdoc detects stale frontmatter descriptions by hashing page content, how to fix STALE001 errors, and how to accept a reviewed dead-end with selfdoc baseline accept."
nav_group: "Guides"
nav_order: 18
---

# Staleness Detection

You update a page's content but forget to update the frontmatter `description`. Now your meta tags, OG cards, and search snippets show outdated text. selfdoc catches this automatically by tracking content hashes.

## The Problem

Frontmatter descriptions feed into `<meta name="description">`, Open Graph tags, Twitter cards, search index summaries, and the Atom feed. When the page body changes significantly but the description stays the same, those external-facing representations go stale. Users see one thing in search results and something different on the page.

This is easy to miss during normal editing. You change the content, the page looks fine, and you move on -- never noticing the description no longer matches.

## How It Works

selfdoc maintains a hash store at `.selfdoc/hashes/hashes.json` that tracks each page's content and description independently. By comparing current hashes against stored baselines on every `selfdoc check` run, it detects when content has drifted from its description. For each documentation page with a frontmatter description, it tracks two SHA-256 hashes:

- **Content hash** -- computed from the page body (frontmatter stripped, directives resolved)
- **Description hash** -- computed from the frontmatter `description` string

On each run of `selfdoc check`, the current hashes are compared against the stored ones. The logic is straightforward:

| Content changed? | Description changed? | Result |
| --- | --- | --- |
| No | No | OK -- nothing changed |
| No | Yes | OK -- description updated independently |
| Yes | Yes | OK -- both updated together |
| Yes | No | **STALE** -- content changed but description did not |

Only the last case triggers a staleness error.

## The STALE001 Error

When staleness is detected, `selfdoc check` reports an error-level diagnostic with the affected filename and a clear message explaining that the content changed but the description did not. This is classified as an error (not a warning) because stale descriptions degrade search results, social cards, and AI summaries:

```
STALE001 [error] getting-started.md: content changed but frontmatter
description was not updated (possible stale description)
```

This is an error, not a warning -- it causes `selfdoc check` to exit with code 1. If you have checks in CI or in an rlsbl pre-checks hook, stale descriptions block the pipeline.

## Fixing It

Update the frontmatter `description` to reflect the current page content, then run `selfdoc check` again to record the new baseline hashes and clear the error. Aim for 120-155 characters that accurately summarize what the page covers after the content change:

```markdown
---
title: Getting Started
description: "Install selfdoc, initialize a project, and build your first documentation site in under five minutes."
---
```

Then run `selfdoc check` again. The hashes update and the error clears.

## Accepting a Reviewed Dead-End

Sometimes the content legitimately changed but the existing description is still accurate, and rewriting it would be dishonest busywork. The most common trigger is a page that embeds `project.version` (via a var directive): its resolved content changes on every release even though nothing about the page's meaning did. Because the baseline is frozen while a page is in an error state, `selfdoc gen` and `selfdoc check` can never clear STALE001 on their own -- the page is stuck until a human intervenes:

```
selfdoc baseline accept en/index.md en/cli-index.md
```

`selfdoc baseline accept <page> [<page>...]` is a deliberate, auditable action that means "reviewed: the content changed, and the existing frontmatter description is still accurate." It advances each named page's baseline to the current content and description hashes -- exactly as if the description had been rewritten -- so the next `selfdoc check` passes without touching the description.

Acceptance is intentionally per-page and unforgiving:

- Name each page explicitly, exactly as it appears in `selfdoc check` output (e.g. `en/cli-index.md`). There is no `--all`, no glob, and no `--force`.
- Accepting a page that does not exist, has no recorded baseline, or is not currently reporting STALE001 or DRIFT001 is a hard error -- "nothing to accept" never silently succeeds.
- The same guardrails apply to DRIFT001 (source-docstring and CLI-schema drift); accepting advances every tracked hash for the page.

Like `selfdoc check`, the command commits the updated `.selfdoc/hashes/hashes.json` by default; pass `--no-auto-commit` to stage the change for a larger manual commit.

## Hash Storage

Hashes are stored in `.selfdoc/hashes/hashes.json`, a JSON file mapping each page path to its content and description SHA-256 hashes. This file is written atomically using a temporary file plus `os.replace` to prevent corruption, and should be committed to your repository as the baseline for future comparisons:

```json
{
  "getting-started.md": {
    "content": "a1b2c3d4...",
    "description": "e5f6g7h8..."
  }
}
```

This file is written atomically (temp file + `os.replace`) and should be committed to your repo. It is the baseline for future comparisons -- without it, every page looks new and no staleness is detected.

## Dry Run Mode

To preview staleness results without updating the hash file on disk, use the `--dry-run` flag. This computes all hashes, compares them against the stored baselines, and reports any stale pages but does not write changes to `.selfdoc/hashes/hashes.json`. Useful for previewing what would be flagged:

```bash
selfdoc check --dry-run
```

This computes all hashes and reports stale pages but does not write to `.selfdoc/hashes/hashes.json`. Useful for seeing what would be flagged without changing state.

## The `--no-auto-commit` Flag

By default, `selfdoc check` auto-commits hash updates when it writes to the hash file, using the best available commit tool (rlsbl, safegit, or plain git). Use `--no-auto-commit` to write the updated hashes to disk without creating a commit, which is useful when the hash update is part of a larger change you will commit manually:

```bash
selfdoc check --no-auto-commit
```

This is useful when you want to update hashes as part of a larger change that you will commit manually.

> [!TIP]
> New pages (ones not yet in the hash store) never trigger STALE001. Staleness is only detected on subsequent runs after the initial hashes are recorded. Run `selfdoc check` once after adding new pages to establish the baseline.

Next: [Glossary](glossary-terms/) -->
