# Automated doc quality assurance checks

## Context

Coverage enforcement (100% documented) ensures every public symbol appears on a non-skeleton page. But coverage only answers "is every symbol documented?" -- not "are the docs any good?" This todo covers automated quality checks that verify documentation content, not just presence.

## Proposed checks

### Description quality (DQ001-DQ003)
- DQ001: Description is just the function/class name restated (e.g., `load_config` described as "Load config")
- DQ002: Description too short to be useful (below a threshold, e.g., <20 chars)
- DQ003: Description missing key information (params, return type, exceptions) for functions that have them

### Docstring-to-docs drift (DRIFT001)
- Source docstring changes but the docs page description is not updated. Extends the existing STALE001 concept to the source-to-docs direction. STALE001 detects content-changed-but-description-unchanged; DRIFT001 would detect source-docstring-changed-but-docs-description-unchanged.

### Cross-reference integrity (XREF001-XREF002)
- XREF001: Internal links between doc pages resolve to valid targets
- XREF002: Directive `path` attributes resolve to existing source files

### Example code validation (EXAMPLE001)
- Code blocks with a declared language (e.g., ```python) should parse without syntax errors. Not a full execution check -- just AST/syntax validation.

### Parameter documentation completeness (PARAM001)
- Functions referenced in docs that have parameters should have those parameters described somewhere on the page.

### Return type documentation (RETURN001)
- Functions referenced in docs that have non-None return types should describe what they return.

### CLI docs completeness (CLI001)
- Generated CLI reference pages should cover all flags and subcommands. Compare the strictcli schema against the generated CLI pages and flag any missing entries.

## Integration point

All checks would produce `LintResult` entries with codes in the ranges above, integrate with the existing `selfdoc check` pipeline, and respect the `lint_ignore` config (which should be widened from `^SEO\d+$` to accept all lint code prefixes).

## Effort

Large. Each check category is independently implementable. Description quality and cross-reference integrity are the highest-value, lowest-effort starting points.
