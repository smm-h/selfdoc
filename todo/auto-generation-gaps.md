# Auto-generation gaps: reduce manual markdown maintenance

Status: Proposed
Priority: High

## Context

selfdoc's promise is code-aware documentation: write directives in markdown, selfdoc resolves them from source code. But significant manual maintenance remains — frontmatter, registry tables, section intros, and page scaffolding all require hand-written markdown that duplicates information already in the codebase.

Discovered while maintaining rlsbl's docs: 5 markdown files require manual frontmatter descriptions (triggering SEO006), a 14-row targets table that goes stale when targets are added, and 13 command section intros that duplicate module docstrings.

## Opportunities

### 1. Auto-generate frontmatter descriptions (quick win)

When a page has no explicit `description` in frontmatter, extract the first paragraph (first non-heading, non-directive text) and use it as the description, truncated to 155 chars. This eliminates SEO006 errors without any user action.

Affected: every page without frontmatter. In rlsbl, all 5 docs pages.

### 2. `selfdoc gen` command (high value)

A command that scaffolds markdown pages from code structure:
- Detect the project type (Python CLI, library, etc.)
- Scan for command modules → generate a commands.md with `:::cli` directives
- Scan for target/plugin registries → generate a registry page with tables
- Scan for config files → generate a configuration.md with `:::config` directives
- Generate an index.md with links to all pages

This is like `rlsbl scaffold` but for docs. Run once to bootstrap, then selfdoc keeps the directive content in sync. The user only writes prose and examples.

Should also support `selfdoc gen --update` to add pages for newly detected modules without overwriting existing customizations.

### 3. Registry table directive (medium value)

A directive like `:::registry module.path DICT_NAME` that introspects a Python dict and generates a markdown table. Example:

```markdown
:::registry rlsbl.targets TARGETS
:::
```

Would generate a table with target name, version file, detection method by calling methods on each dict value. The directive needs a way to specify which attributes/methods to call for each column.

Generalizable: any project with a plugin/target/handler registry could use this.

### 4. Module docstring as section intro (medium value)

Extend `:::cli` or create `:::cli-intro` that extracts the module's first docstring line and formats it as prose before the help text. Currently the user writes a one-line intro manually, duplicating the module docstring.

### 5. Auto-populate description from :::cli output (low effort)

When a page has `:::cli` directives but no frontmatter description, use the first directive's extracted docstring as the page description. This is a variant of opportunity #1 but directive-aware.

## What should remain manual

- Prose explanations and examples (the value-add of docs)
- Page navigation and structure decisions
- Strategic context (why a feature exists, when to use it)

## Effort

- Opportunity 1 (frontmatter): Small — add fallback in build.py frontmatter parsing
- Opportunity 2 (gen command): Medium-large — new command, code structure detection, template scaffolding
- Opportunity 3 (registry directive): Medium — new directive type, introspection API
- Opportunity 4 (module intro): Small — extend existing :::cli directive
- Opportunity 5 (description from directive): Small — post-directive description extraction
