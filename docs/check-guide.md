---
title: Check Guide
description: "Use selfdoc check to validate directives, measure documentation coverage, run SEO lints, detect stale descriptions, and integrate checks into CI pipelines."
nav_group: "Guides"
nav_order: 10
---

# Check Guide

`selfdoc check` is your documentation linter. It validates every directive in your templates, measures how much of your public API is documented, runs SEO best-practice checks, and detects stale descriptions. Run it locally before pushing, or wire it into CI for automated enforcement.

## What It Does

A single `selfdoc check` run performs three categories of analysis:

1. **Directive validation** -- resolves every directive marker in your `docs/` templates and reports whether each one succeeds or fails.
2. **Coverage analysis** -- counts public/exported symbols in your source code and checks how many are referenced by directives.
3. **SEO linting** -- scans templates for heading structure, meta description, alt text, contrast ratio, and other best practices.

```bash
selfdoc check
```

## Directive Validation

Every directive in your docs is resolved against the actual source code. If a module path is wrong, a target symbol does not exist, or a custom directive script throws an error, the check reports it with file and line number:

```
Directives
  index.md:12  ref path="mypackage"        OK
  api.md:8     ref path="mypackage.core"    OK
  api.md:20    table-schema path="bad.path" FAILED: Module not found
```

Fix failures by correcting the directive's `path` or `target` attribute to match your actual source code.

## Coverage

Coverage measures how much of your public API surface is documented. selfdoc walks your `source` directories, extracts public symbols using the language-specific extractor (Python, Go, or TypeScript), and checks whether each symbol appears in the resolved content of a directive.

```
Coverage: 15/23 public symbols documented (65%)
Undocumented symbols:
  mypackage/core.py: helper_function, InternalConfig
```

### Coverage threshold

Set `min_coverage` in your `selfdoc.json` to enforce a minimum:

```json
{
  "min_coverage": 80
}
```

If coverage falls below this value, `selfdoc check` exits with code 1. Useful in CI to prevent coverage regressions.

### Excluding modules

Modules listed in `gen.exclude` are excluded from coverage calculations. This is for intentionally-internal modules that should not appear in public documentation:

```json
{
  "gen": {
    "exclude": ["mypackage._internal", "mypackage.tests"]
  }
}
```

## Lint Rules

selfdoc runs 15 SEO lint rules plus a staleness check. Each rule has a code, severity, and actionable message.

| Code | Severity | What it checks |
| ---- | -------- | -------------- |
| SEO001 | error | Multiple H1 headings on a page. Use a single `#` heading. |
| SEO002 | warning | Heading level gaps (e.g., H2 followed by H4 skipping H3). |
| SEO003 | warning | Image with empty alt text (`![](...)`). Add descriptive alt text. |
| SEO004 | warning | Page title exceeds 60 characters (combined with project name). Shorten it. |
| SEO006 | error | Missing `description` in frontmatter. Add one for meta tags. |
| SEO007 | warning | First paragraph after a heading is outside the 30-80 word range. Aim for 40-60 words for AI citation. |
| SEO008 | warning | Low numeric data density. Pages with 200+ words should include concrete numbers for AI citation. |
| SEO009 | warning | Description is shorter than 120 characters. Aim for 120-155. |
| SEO010 | warning | Frontmatter description exceeds 155 characters. Trim it. |
| SEO011 | warning | Empty heading section (heading followed by another heading with no content between). |
| SEO012 | warning | WCAG contrast ratio below threshold for theme colors. Fix in CSS custom properties. |
| SEO013 | error | No title source: neither frontmatter `title` nor an H1 heading exists on the page. |
| SEO014 | warning | Meaningless image alt text (e.g., "image", "screenshot", or a bare filename). Write something descriptive. |
| SEO015 | warning | Generic anchor text like "click here" or "read more". Use descriptive link text. |
| STALE001 | error | Page content changed but frontmatter description was not updated. Review and update the description. |

### Suppressing rules

Suppress specific lint rules globally in your config:

```json
{
  "lint_ignore": ["SEO007", "SEO008"]
}
```

Or per invocation with `--ignore`:

```bash
selfdoc check --ignore SEO007,SEO008
```

Both sources are combined -- CLI flags and config are merged.

## Staleness Detection

selfdoc tracks SHA-256 hashes of each page's resolved content and frontmatter description. When the content changes but the description stays the same, it raises a STALE001 error. This catches the common case where you update a page's content but forget to revise the description that feeds into meta tags and search results.

Hashes are stored in `.selfdoc/hashes/hashes.json` and auto-committed after each check (unless you pass `--no-commit` or `--dry-run`).

## Output Formats

### Text (default)

Human-readable output with colored status indicators:

```bash
selfdoc check
```

### JSON

Machine-readable output for CI integration:

```bash
selfdoc check --format json
```

Returns a JSON object with `directives`, `coverage`, `lints`, and `exit_code` fields. Example structure:

```json
{
  "directives": [{"file": "index.md", "line": 12, "status": "OK", ...}],
  "coverage": {"total_public": 23, "referenced": 15, ...},
  "lints": [{"code": "SEO006", "severity": "error", ...}],
  "exit_code": 0
}
```

## Exit Codes

`selfdoc check` exits with code 0 when everything passes, and code 1 when any of these are true:

- A directive resolution failed
- Any lint has severity `error`
- Coverage is below the `min_coverage` threshold

Warnings alone do not cause a non-zero exit. This makes it safe to use in CI -- warnings are informational, errors block the pipeline.

> [!TIP]
> Run `selfdoc check --dry-run` to see staleness results without writing hash files to disk. Useful for previewing what would change.

Next: [rlsbl Integration](rlsbl-integration/) -->
