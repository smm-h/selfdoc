# Enforce that code comments feed into docs

## Problem

Code comments exist in isolation -- they help whoever reads that specific file but are invisible to the documentation system. There's no mechanism to verify that comments which describe important behavior, constraints, or assumptions are captured in the generated docs. Comments rot silently.

## Proposed solution

Use AST analysis to find all comments across all source files in a project. For each comment, check whether its content (or the code construct it annotates) is referenced by a selfdoc directive or appears in generated docs. Hard error for comments that describe public API behavior but don't feed into docs.

## Categories

- **API comments** (docstrings, function/class-level comments): should always be captured by `ref` directives
- **Constraint comments** (e.g., "Scaffold runs single-threaded"): should be flagged for review -- are they documenting something that belongs in architecture docs?
- **TODO/FIXME comments**: separate concern (existing linters handle these)
- **Implementation comments** (e.g., "use setdefault to merge"): these are for code readers, not docs -- should be exempt

## Effort

Medium-large. Needs AST comment extraction for Python/Go/TypeScript, a classification heuristic, and integration with the existing selfdoc check pipeline.
