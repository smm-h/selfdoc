# Generated CLI page descriptions are too short for SEO

## Problem

`selfdoc gen` produces CLI documentation pages (`cli-*.md`) with short frontmatter descriptions like "Documentation for the release command" (37 chars). selfdoc's own SEO check (SEO009) requires 120-155 chars. Every generated CLI page triggers this warning.

## Cause

The description template in `gen` uses a generic pattern (`"Documentation for the {name} command"`) regardless of how descriptive the command's help text is. The help text itself (from strictcli's `help=` parameter) is often 120+ chars and would make a better description.

## Proposed fix

When generating CLI page frontmatter, use the command's help text as the description (truncated to 155 chars if needed) instead of the generic template. The help text is already available from the strictcli App introspection that `gen` performs.

Fallback to the generic template only when the command has no help text or it's very short (< 50 chars).

## Affected files

- `selfdoc/cli.py` or wherever `gen` produces CLI page frontmatter

## Effort

Small. Change the description assignment in the CLI page generation template.
