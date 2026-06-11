# Support inline directives

## Problem

Directives use `^:-:` regex (start-of-line only). Block-level directives cannot be embedded inline in paragraphs or list items. Example: "rlsbl has :-: check-count checks" is impossible — the directive must be on its own line.

## Use case

Dynamic counts and values that appear mid-sentence, like check counts, version numbers, or feature counts.

## Effort

Large. The directive parser operates line-by-line with a state machine. Inline support would require: refactoring the regex to match mid-line, changes to the block state machine, output replacement at inline position, and conflict resolution with code block fence tracking.
