# Lint H1 check should ignore fenced code blocks

## Problem

The multiple-H1 lint check in `check_docs()` counts lines starting with `# ` inside fenced code blocks (triple backticks) as H1 headings. This causes false positives when documentation contains bash code examples with comments:

```markdown
## Getting started

```bash
# Initialize a workspace
rlsbl monorepo init

# Add a project
rlsbl monorepo add --name mylib
```
```

selfdoc reports: "monorepo.md: multiple H1 headings found (line 1, line 8, line 11, ...)" — but lines 8 and 11 are bash comments inside a code block, not markdown headings.

## Impact

This blocks `selfdoc build` entirely (the check raises a hard error), which in turn blocks the auto-commit hashes feature from running on affected projects.

## Fix

The H1 heading check should skip lines that are inside fenced code blocks. Track a boolean state: when a line matches `` ^```  `` (opening fence), set inside=True; when another fence line appears, set inside=False. Only count `# ` lines as H1 headings when inside=False.

## Affected file

`selfdoc/check.py` — the heading count logic (around the "multiple H1 headings" error).

## Effort

Small. A few lines of fence-tracking state in the heading counter.
