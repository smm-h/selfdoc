---
title: Check Guide
description: "Run selfdoc check to validate directives, measure coverage, execute marked examples, and apply every registered lint rule with its declared severity."
nav_group: "Guides"
nav_order: 10
---

# Check Guide

`selfdoc check` is your documentation linter. It validates every directive in your templates, measures how much of your public API is documented, runs SEO best-practice checks, and detects stale descriptions. Run it locally before pushing, or wire it into CI for automated enforcement.

## What It Does

A single `selfdoc check` run performs three categories of analysis that together cover directive correctness, API documentation coverage, and SEO best practices. Each category produces structured output with file paths, line numbers, and actionable messages:

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

Set `min_coverage` in your `selfdoc.json` to enforce a minimum percentage of public symbols that must be referenced by directives. If coverage falls below this threshold, `selfdoc check` exits with code 1, making it useful as a CI gate to prevent coverage regressions over time:

```json
{
  "min_coverage": 80
}
```

If coverage falls below this value, `selfdoc check` exits with code 1. Useful in CI to prevent coverage regressions.

### Excluding modules

Modules listed in `gen.exclude` are excluded from both coverage calculations and auto-generated documentation pages. Use this for intentionally-internal modules, test helpers, or implementation details that should never appear in public-facing documentation. Excluded symbols do not count against your coverage threshold:

```json
{
  "gen": {
    "exclude": ["mypackage._internal", "mypackage.tests"]
  }
}
```

## Lint Rules

Every `selfdoc check` invocation runs the whole lint registry: SEO and page structure, description staleness and source drift, cross-references and symbol documentation, example validation, CLI reference completeness, version consistency, blog posts, and unified sites. Each rule has a unique code, a severity, and an actionable message explaining what is wrong and how to fix it. Errors cause a non-zero exit; warnings are informational. The table below is generated from `selfdoc_core/lints.toml`, the one place a code and its severity are declared.

| Code | Severity | What it checks |
| ---- | -------- | -------------- |
| SEO001 | error | Multiple H1 headings on a page. Use a single `#` heading. |
| SEO002 | warning | Heading level gaps (e.g., H2 followed by H4 skipping H3). |
| SEO003 | warning | Image with empty alt text (`![](...)`). Add descriptive alt text. |
| SEO004 | warning | Page title exceeds 60 characters (combined with project name). Shorten it. |
| SEO006 | error | Missing `description` in frontmatter. Add one for meta tags. |
| SEO007 | warning | First paragraph after a heading is outside the 30-80 word range. Every page type is held to the same band, generated pages included. |
| SEO008 | warning | Low numeric data density. Pages with 200+ words should include concrete quantities; version strings and calendar years do not count. |
| SEO009 | warning | Description is shorter than 120 characters. Aim for 120-155. |
| SEO010 | warning | Frontmatter description exceeds 155 characters. Trim it. |
| SEO011 | warning | Empty heading section (heading followed by another heading with no content between). |
| SEO012 | warning | WCAG contrast ratio below threshold for theme colors. Fix in CSS custom properties. |
| SEO013 | error | No title source: neither frontmatter `title` nor an H1 heading exists on the page. |
| SEO014 | warning | Meaningless image alt text (e.g., "image", "screenshot", or a bare filename). Write something descriptive. |
| SEO015 | warning | Generic anchor text like "click here" or "read more". Use descriptive link text. |
| STALE001 | error | Page content changed but frontmatter description was not updated. Review and update the description. |
| STALE002 | warning | Manifest and disk disagree: a page or post exists on disk but is missing from `.selfdoc/manifest.json`, or the manifest lists one that is gone. Run `selfdoc gen`. |
| DRIFT001 | error | The source docstrings (or CLI schema) a page documents changed while its description did not. Update the description, or run `selfdoc baseline accept <page>` if it is still accurate. |
| DQ001 | warning | The frontmatter description restates the page or symbol name instead of describing it. |
| DQ002 | warning | Frontmatter description is shorter than 20 characters. |
| DQ003 | warning | A page carrying a `ref` directive has a description shorter than 30 characters. |
| XREF001 | warning | A Markdown link points at a `.md` page that does not exist in the docs tree. |
| XREF002 | error | A directive's `path` resolves but names a file that is not on disk. |
| PARAM001 | warning | A referenced symbol has a parameter its docstring never documents. |
| RETURN001 | warning | A referenced symbol returns a value its docstring never documents. |
| EXAMPLE001 | warning | A Python or JSON code block does not parse. Fix the snippet's syntax. |
| EXAMPLE002 | error | A code block marked `validate` failed its configured validator. The message carries the validator's exit code and output tail. |
| EXAMPLE003 | error | A code block is marked `validate` but no `examples` command is configured for its language. Add one, or drop the marker. |
| CLI001 | warning | strictcli project: a CLI reference page is missing for a command, or a flag in the schema is not documented on its page. |
| CLI002 | warning | strictcli project: a command, group, or flag help text is shorter than 50 characters. |
| LANG001 | error | A configured source entry names a language selfdoc has no extractor for. |
| SEARCH001 | error | `search_engine` is set to `pagefind` but pagefind is not installed. |
| VER001 | error | A version listed in `versions` could not be extracted from its git tag, so it could not be validated. |
| VER002 | error | `version` in selfdoc.json does not match the version detected from the project manifest (pyproject.toml, package.json, or a `VERSION` file). |
| VER003 | error | The last entry of the `versions` array does not match `version` in selfdoc.json. |
| VER004 | error | A generated root file that embeds `project.version` does not contain the expected version. Regenerate with `selfdoc gen --version-override <v>`. |
| POST001 | error | A post is missing the required `date` field in its frontmatter. |
| POST002 | error | A post is missing the required `title` field in its frontmatter. |
| POST003 | error | A post's `date` is not written as YYYY-MM-DD. |
| POST004 | error | Two posts resolve to the same slug. |
| POST005 | error | A published post's slug changed, which would break its permalink. |
| UNIFIED001 | error | A project listed in the `unified` section has no selfdoc.json. |
| UNIFIED002 | error | A constituent project, or the docs-site's own content, could not be checked. |

### Suppressing rules

Suppress specific lint rules globally in your config or per invocation via CLI flags. Both sources are merged, so you can set baseline suppressions in config and add per-run overrides as needed. Use suppression sparingly since each rule catches real SEO or accessibility issues:

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

Hashes are stored in `.selfdoc/hashes/hashes.json` and auto-committed after each check (unless you pass `--no-auto-commit` or `--dry-run`).

## Example Validation

Every Python and JSON code block is parsed during `selfdoc check`, and a block that does not parse raises `EXAMPLE001`. Parsing proves only that a snippet is well-formed, not that it still works: an example calling a function you renamed six months ago parses perfectly and is completely wrong. To catch that class, mark the block `validate` and configure a validator for its language:

````markdown
```python validate
from mylib import greet

print(greet("world"))
```
````

```json
{
  "examples": {
    "python": "uv run --directory python python {file}",
    "go": "scripts/validate-example-go.sh {file}",
    "ts": "scripts/validate-example-ts.sh {file}"
  }
}
```

selfdoc writes each marked block to a scratch file suffixed for its language, substitutes the path for `{file}`, and runs the command from the project root with a 60-second timeout. A non-zero exit becomes an `EXAMPLE002` error naming the exit code and the last five lines of the validator's output. A marked block whose language has no configured command becomes an `EXAMPLE003` error rather than being skipped, so an unhonored marker can never masquerade as a passing one.

The marker is opt-in per block: unmarked blocks are never executed and keep the `EXAMPLE001` syntax check exactly as before. Validators run without a sandbox, so configure commands that compile, type-check, and register rather than ones that execute arbitrary payloads.

## Output Formats

### Text (default)

Human-readable output with colored status indicators, file paths, line numbers, and rule codes. This is the default format designed for local development where you read the output directly in a terminal and fix issues one by one:

```bash
selfdoc check
```

### JSON

Machine-readable output for CI integration, custom tooling, or programmatic analysis. The JSON format includes the same information as text output but structured as arrays of objects with consistent field names for easy parsing:

```bash
selfdoc check --format json
```

Returns a JSON object with `directives`, `coverage`, `lints`, and `exit_code` fields. Example structure:

```text
{
  "directives": [{"file": "index.md", "line": 12, "status": "OK", ...}],
  "coverage": {"total_public": 23, "referenced": 15, ...},
  "lints": [{"code": "SEO006", "severity": "error", ...}],
  "exit_code": 0
}
```

## Exit Codes

`selfdoc check` uses standard exit codes to signal pass or fail, making it safe to use as a CI gate or pre-commit hook. It exits with code 0 when everything passes, and code 1 when any of these conditions are true:

- A directive resolution failed
- Any lint has severity `error`
- Coverage is below the `min_coverage` threshold

Warnings alone do not cause a non-zero exit. This makes it safe to use in CI -- warnings are informational, errors block the pipeline.

> [!TIP]
> Run `selfdoc check --dry-run` to see staleness results without writing hash files to disk. Useful for previewing what would change.

Next: [rlsbl Integration](rlsbl-integration/) -->
