---
title: Staleness Detection
description: "How selfdoc detects stale frontmatter descriptions by hashing page content, and how to fix STALE001 errors from selfdoc check."
nav_group: "Guides"
nav_order: 18
---

# Staleness Detection

You update a page's content but forget to update the frontmatter `description`. Now your meta tags, OG cards, and search snippets show outdated text. selfdoc catches this automatically by tracking content hashes.

## The Problem

Frontmatter descriptions feed into `<meta name="description">`, Open Graph tags, Twitter cards, search index summaries, and the Atom feed. When the page body changes significantly but the description stays the same, those external-facing representations go stale. Users see one thing in search results and something different on the page.

This is easy to miss during normal editing. You change the content, the page looks fine, and you move on -- never noticing the description no longer matches.

## How It Works

selfdoc maintains a hash store at `.selfdoc/hashes/hashes.json`. For each documentation page with a frontmatter description, it tracks two SHA-256 hashes:

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

When staleness is detected, `selfdoc check` reports:

```
STALE001 [error] getting-started.md: content changed but frontmatter
description was not updated (possible stale description)
```

This is an error, not a warning -- it causes `selfdoc check` to exit with code 1. If you have checks in CI or in an rlsbl pre-checks hook, stale descriptions block the pipeline.

## Fixing It

Update the frontmatter `description` to reflect the current page content. Aim for 120-155 characters that summarize what the page covers:

```markdown
---
title: Getting Started
description: "Install selfdoc, initialize a project, and build your first documentation site in under five minutes."
---
```

Then run `selfdoc check` again. The hashes update and the error clears.

## Hash Storage

Hashes are stored in `.selfdoc/hashes/hashes.json`, a JSON file mapping page paths to their content and description hashes:

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

To preview staleness results without updating the hash file on disk:

```bash
selfdoc check --dry-run
```

This computes all hashes and reports stale pages but does not write to `.selfdoc/hashes/hashes.json`. Useful for seeing what would be flagged without changing state.

## The `--no-commit` Flag

By default, `selfdoc check` auto-commits hash updates when it writes to the hash file. Use `--no-commit` to write the updated hashes without committing:

```bash
selfdoc check --no-commit
```

This is useful when you want to update hashes as part of a larger change that you will commit manually.

> [!TIP]
> New pages (ones not yet in the hash store) never trigger STALE001. Staleness is only detected on subsequent runs after the initial hashes are recorded. Run `selfdoc check` once after adding new pages to establish the baseline.

Next: [Glossary](glossary-terms/) -->
