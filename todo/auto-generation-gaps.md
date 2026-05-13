# Directive system redesign and auto-generation

Status: Proposed
Priority: High

## Context

selfdoc's directive system (`:::name arg` / `:::`) has served its purpose but has accumulated design debt: ambiguous closers, no structured attributes, two-line minimum for bodyless directives, custom directives that silently drop body content, and domain-specific naming that conflates source type with output type.

A thorough design review and ASKME session produced a comprehensive redesign covering syntax, naming, new commands, security, and migration. This todo supersedes the original auto-generation-gaps proposal.

## 1. Directive syntax overhaul

Replace the old `:::name arg` / `:::` syntax with symmetric colon-bracket delimiters:

- `:-: name attr="value"` -- one-liner, no body
- `:<: name attr="value"` -- block open
- `::: ` -- body line prefix (strip prefix, remainder is Markdown)
- `:>:` -- block close

Examples:

```markdown
:-: code-source path="selfdoc/config.py" target="load_config"

:<: table-schema path="selfdoc/config.py" target="Config"
::: exclude: _private_field
::: exclude: _internal_method
:>:

:<: list-glossary
::: **directive**: a block in Markdown that selfdoc resolves from source code
::: **extractor**: language-specific module that reads code structure
:>:

:-: callout-warning
::: This is a breaking change from v1.
:>:
```

Parsing rules:
- `:<:` followed by word chars = block open
- `:-:` followed by word chars = one-liner (no body, no closer)
- `::: ` (colon-colon-colon-space) = body line, strip prefix
- `:>:` alone on a line = block close
- No nesting (`:>:` always closes the nearest open block)

## 2. Directive naming: contenttype-semantic

Directive names are `contenttype-semantic`, dash-separated. Content type first (what the output looks like), semantic second (what it means). Full catalog shipped built-in, extensible by consumer projects.

### Built-in catalog

Tables:
- `table-schema` -- field/type/default/description from dataclasses, structs, interfaces
- `table-config` -- key/type/value from JSON/TOML/JSONC files
- `table-param` -- parameter/type/required/description
- `table-endpoint` -- method/path/description for API routes
- `table-env` -- environment variable/type/default/description
- `table-compare` -- feature x option comparison matrix
- `table-dep` -- dependency/version/license
- `table-error` -- error code/meaning/resolution
- `table-shortcut` -- key/action for keyboard shortcuts
- `table-status` -- item/status/notes
- `table-registry` -- name/handler/description from introspected dicts (runtime import, Python only for now, extensible later)
- `table-migration` -- from/to/action
- `table-timeline` -- date/version/description
- `table-perm` -- role x action permission matrix
- `table-plan` -- feature x tier pricing matrix

Code blocks:
- `code-source` -- function/method/class implementation
- `code-test` -- test function source
- `code-example` -- usage example
- `code-help` -- CLI help output verbatim
- `code-session` -- shell command + output transcript
- `code-repl` -- interactive REPL session
- `code-config` -- sample configuration file
- `code-diff` -- before/after code changes
- `code-error` -- exception/traceback output
- `code-schema` -- type/struct/interface definition source
- `code-template` -- file template with placeholders
- `code-log` -- application log lines
- `code-query` -- SQL/GraphQL/API request
- `code-wire` -- protocol message, HTTP request/response
- `code-build` -- compiler/test runner/CI output

Lists:
- `list-glossary` -- flat term/definition pairs (renders as `<dl>`)
- `list-toc` -- table of contents from headings
- `list-check` -- items with checkboxes
- `list-steps` -- ordered procedure
- `list-faq` -- question/answer pairs
- `list-features` -- feature + one-line description
- `list-tree` -- file/directory tree
- `list-deps` -- dependency tree (nested)
- `list-breadcrumb` -- navigation path
- `list-related` -- see-also links with context
- `list-errors` -- error + cause + fix
- `list-decisions` -- decision + rationale
- `list-reqs` -- must/should/could requirements
- `list-api` -- grouped endpoints/methods
- `list-changelog` -- version with nested changes

Callouts:
- `callout-note` -- neutral supplementary info
- `callout-warning` -- potential pitfall
- `callout-tip` -- helpful suggestion
- `callout-danger` -- destructive/irreversible action
- `callout-important` -- must-read information
- `callout-example` -- illustrative scenario
- `callout-deprecated` -- end-of-life notice
- `callout-security` -- security-relevant info
- `callout-perf` -- performance implication
- `callout-compat` -- browser/version/platform note
- `callout-experimental` -- unstable/alpha feature
- `callout-see-also` -- cross-reference
- `callout-breaking` -- breaking change info
- `callout-success` -- confirmation/positive outcome
- `callout-quote` -- attributed quotation

Prose:
- `prose-desc` -- module/function docstring
- `prose-summary` -- one-line overview
- `prose-caption` -- figure/table/code caption
- `prose-rationale` -- why a decision was made
- `prose-caveat` -- known issues/limitations
- `prose-migration` -- upgrade instructions
- `prose-changelog` -- version + date + changes
- `prose-release` -- user-facing release summary
- `prose-prereq` -- prerequisites for a section
- `prose-abstract` -- document-level summary
- `prose-deprecation` -- what's deprecated + replacement
- `prose-attribution` -- author/source/license
- `prose-definition` -- inline term definition
- `prose-annotation` -- footnote/supplementary detail
- `prose-example` -- narrative explaining an example

Compound:
- `ref` -- full API reference for a module (headings + code blocks + prose per symbol). Default compound; users who want custom layout compose with individual contenttype-semantic directives instead.

### Extensibility

Consumer projects register additional directive names in `selfdoc.json`. The handler is a script in a declared directory. Unknown directive names produce a clear error.

## 3. `selfdoc gen` command

Full overwrite model -- generated files are always regenerated from scratch, never merged or updated in place.

- Auto-discovers project structure (language, modules, CLI entry points, config files)
- Config overrides in `selfdoc.json` under a `gen` section (exclude patterns, grouping hints)
- Generated files are read-only at Unix level (0444 permissions)
- Generated files have `generated: true` in frontmatter AND `<!-- generated by selfdoc gen, do not edit -->` HTML comment
- selfdoc build/check can distinguish generated vs hand-written pages via the frontmatter field
- strictcli projects: gen auto-produces CLI reference pages with full command/flag/arg tables

## 4. `selfdoc gen-data` command

Separate build phase for script execution. Directives never trigger execution -- they only read static output files.

- Scripts declared in `selfdoc.json` (not in Markdown files)
- Each script declaration includes explicit mount paths (what the script can read)
- Executed in bwrap (bubblewrap) sandbox: no environment variables, no access to secrets/env files, read-only access to declared mounts only
- Output written to `.selfdoc/data/`
- Directives reference the output files: `:-: table-registry path=".selfdoc/data/targets.json"`
- Any language: the command is shelled out (Go projects can use Go scripts, Python projects can use Python, etc.)
- Output must be JSON or CSV

## 5. Description staleness detection

Force explicit frontmatter descriptions. Track content hashes to detect when a page's content changes but its description doesn't.

- Hash store: `.selfdoc/hashes/` directory, committed to git
- When directive resolution changes the content of a page (tracked via hash), `selfdoc check` emits a hard error until the description hash also changes
- Build proceeds regardless -- staleness is enforced at check time only, not build time
- No auto-generation of descriptions; the user must write and maintain them

## 6. strictcli first-class support

selfdoc natively understands strictcli-based projects. No directive needed -- `selfdoc gen` handles it.

- selfdoc introspects strictcli's dataclasses directly (via AST or runtime import). No changes needed in strictcli.
- Gen produces full CLI reference pages: command trees, flag tables (name, short, type, default, env, help), arg tables, group sections, usage strings
- Hard error if a project uses strictcli (detected by `import strictcli` in source) but has `code-help` or old `cli` directives. Must use gen-produced pages instead.

## 7. Custom directive body forwarding

Fix the gap in `resolver.py` where custom directive scripts receive `(arg, config)` but not the body. Forward body as a third parameter: `resolve(arg, config, body)`.

## 8. Migration

Hard switch from old `:::` syntax to the new `:-:` / `:<:` / `:>:` syntax. No deprecation period -- the old syntax is removed.

Scope: 59 directive instances across 9 projects (15 Markdown files). Heaviest users: rlsbl (21), selfdoc (19), codehome (10). Five projects have 1 directive each.

Migration is manual via subagents when the new parser is implemented. No migration command needed.

## 9. Todos to file elsewhere

- ~/Work/super: broken topic docs in `gendocs.py` (`TOPIC_DOCS` uses dotted command paths that don't match `_load_commands()` keys, so all topic pages are empty). Also suggest adopting selfdoc.

## What should remain manual

- Prose explanations and examples
- Page navigation and structure decisions
- Strategic context (why a feature exists, when to use it)
- Frontmatter descriptions (enforced, not auto-generated)

## Effort

- Syntax overhaul + parser: Medium -- rewrite `directives.py` state machine
- Directive naming + full catalog: Large -- rewrite extractors, resolver, and all handlers
- `selfdoc gen`: Large -- new command, project introspection, template generation
- `selfdoc gen-data` + bwrap: Medium -- new command, sandbox integration
- Description staleness: Small -- hash computation in check.py, `.selfdoc/hashes/` management
- strictcli support: Medium -- AST/runtime extractor for strictcli dataclasses
- Body forwarding fix: Small -- one-line change in resolver.py
- Migration: Medium -- manual edits across 9 projects
