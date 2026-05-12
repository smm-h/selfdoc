# SEO Linting Gaps: Directive Awareness and Exit Code Severity

Status: Proposed
Priority: High

## Context

The SEO linting system (introduced alongside `base_url` enforcement) has gaps that surface when linting directive-heavy documentation pages. Discovered while integrating selfdoc with rlsbl's docs target -- the build produces 25 SEO warnings on a 5-page site, all caused by the linter's inability to account for auto-generated content.

## Problems

### 1. SEO007 false positives on directive-generated content

The `:::cli`, `:::module`, `:::config` directives are selfdoc's own auto-generation features. A typical reference page looks like:

```markdown
## release

Orchestrate a release: bump version, validate changelog, tag, push, create GitHub Release.

:::cli rlsbl.commands.release
:::
```

SEO007 flags the 12-word intro paragraph as too short ("aim for 40-60 for AI citation"). But the directive below it expands into substantial content. The linter evaluates the markdown source, not the rendered output, so it can't see the auto-generated content.

This produces 22 of 25 warnings on rlsbl's docs. Every `:::cli` section triggers it. There's no way to write 40-60 word intros for 14 CLI commands without padding them artificially.

### 2. SEO001 false positive from directive heading injection

`:::module` directives inject content that may include their own headings. This creates "multiple H1" warnings on pages where the user authored exactly one H1. The linter penalizes headings the user didn't write.

### 3. Build exit code conflates success with lint quality

`selfdoc build` exits 1 when there are ANY SEO warnings, even though the build completed successfully ("Built 22 file(s) to docs/_build/"). Downstream consumers (like rlsbl's docs target) see only the exit code and report "docs target build failed."

The build didn't fail -- a post-build lint found quality suggestions. These are different things. An advisory warning like SEO008 ("no numeric data points") shouldn't have the same exit behavior as SEO006 ("missing description frontmatter").

### 4. No severity distinction between errors and warnings

SEO006 (missing description) is a real problem -- the page will have broken meta tags. SEO008 (no numeric data) is an optimization suggestion. Both produce exit code 1. The caller can't distinguish "output is broken" from "output is fine but could be better."

## Proposed Solutions

### For directive awareness (1, 2)

The SEO linter should either:
- **Post-render linting**: Run SEO checks on the rendered HTML/content, not the markdown source. This way directive-generated content is visible to the linter.
- **Directive-aware skipping**: When a heading's next sibling is a `:::` directive block, suppress SEO007 for that section (the directive will provide content).
- **Heading source tracking**: Track which headings came from directives vs. user markdown. Only apply SEO001 to user-authored headings.

### For exit code severity (3, 4)

- Exit 0 when build succeeds and only advisory warnings exist (SEO007, SEO008)
- Exit 1 when there are errors (SEO006) or structural problems (SEO001)
- Or: exit 0 for warnings, exit 1 for errors. The distinction already exists in the `severity` field.

## Affected Files

- `selfdoc/check.py` -- SEO rule implementations
- `selfdoc/cli.py` -- exit code logic (line ~450: `exit_code = 1 if (has_failures or has_warnings)`)
- `selfdoc/build.py` -- directive expansion (where rendered content is produced)

## Effort Estimate

Medium. Post-render linting is the most correct but requires restructuring the lint pipeline. Directive-aware skipping is a targeted fix. Exit code change is small.
