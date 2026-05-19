# Generate CLAUDE.md and README.md

## Problem

selfdoc generates full HTML documentation sites, but many projects also need:

- **CLAUDE.md** -- instructions and architecture reference for AI coding agents (Claude Code, Cursor, etc.)
- **README.md** -- user-facing project overview, setup, and usage

These files currently must be written and maintained by hand, which causes them to drift from the actual codebase. selfdoc already has the machinery to extract structured information from source code (AST parsing, directive resolution, config reading). Extending it to produce these Markdown files would keep them in sync with the codebase automatically.

## Proposed feature

Add optional CLAUDE.md and README.md generation to `selfdoc build` (and possibly a dedicated `selfdoc gen-docs` subcommand).

### Configuration

In `selfdoc.json`:

```json
{
  "generate": {
    "claude_md": true,
    "readme_md": true
  }
}
```

Both default to `true` (on by default). Set to `false` to opt out.

### CLAUDE.md generation

The generated CLAUDE.md should include:

- Project name, description, and language
- Directory structure (from `source` paths)
- Key modules, classes, and functions (from existing AST extractors)
- Architecture patterns (inferred from import graph, inheritance, protocol usage)
- Entry points and CLI commands (from existing `code-help` directive machinery)
- Configuration files and their schema (from existing `table-config` directive)
- Dependencies and their purpose
- Any content from `docs/claude.md` template if it exists (allowing projects to add custom sections like constraints, conventions, dangerous operations)

The output should be a single flat Markdown file (no HTML, no directives) suitable for inclusion in `.claude/` or project root.

### README.md generation

The generated README.md should include:

- Project name, description, badges
- Installation / setup instructions
- Usage examples (from docstrings, test files, or a `docs/readme.md` template)
- API overview (from extracted symbols)
- Configuration reference
- License

### Template override

Projects can provide `docs/claude.md` and `docs/readme.md` as templates. These would support the same directive syntax as regular selfdoc pages, but the output would be plain Markdown (directives resolved, but no HTML conversion). This lets projects mix auto-extracted content with hand-written sections.

### Monorepo support

For monorepo workspaces (detected by `pyproject.toml` `[tool.uv.workspace]`, `pnpm-workspace.yaml`, or Go `go.work`):

- Generate a root CLAUDE.md and README.md for the workspace
- Optionally generate per-package CLAUDE.md and README.md if the package has its own `selfdoc.json` or is listed in a workspace-level config

## Affected files

- `selfdoc/config.py` -- new `generate` config fields
- `selfdoc/build.py` -- hook generation into build pipeline
- `selfdoc/gen.py` or new `selfdoc/gen_docs.py` -- generation logic
- `selfdoc/resolver.py` -- Markdown-output mode (resolve directives but skip HTML conversion)
- `selfdoc/extractors/*.py` -- may need to expose higher-level summaries (not just per-symbol details)

## Effort estimate

Medium-large. The extraction machinery exists; the main work is:

1. Designing the Markdown output format for each section
2. Adding a "resolve directives to Markdown" mode (currently directives resolve to HTML)
3. Architecture inference heuristics (import graph analysis, pattern detection)
4. Monorepo workspace detection and per-package orchestration
5. Template override support with directive resolution

## Alternatives considered

- **Keep manual**: Works but drifts. Every project with a CLAUDE.md has this problem.
- **Separate tool**: Could build a standalone `claudegen` tool, but it would duplicate selfdoc's extraction machinery.
- **AI-based generation**: Use an LLM to read the codebase and generate docs. Nondeterministic, expensive, and hard to keep in sync. selfdoc's deterministic extraction is a better foundation.
