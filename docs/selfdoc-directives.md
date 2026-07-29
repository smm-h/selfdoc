---
title: selfdoc.directives
description: "Directive parser for selfdoc's structured marker syntax -- tokenizes the 6 marker types into typed directive objects for resolution."
nav_group: "API Reference"
nav_order: 10
---

# selfdoc.directives

The directives module parses selfdoc's structured marker syntax, which embeds source-code extraction commands inside Markdown templates. It recognizes six marker types: `:-:` (one-liner/self-closing), `:<:` (block open), `:@:` (block attribute), `:=:` (body separator), `:::` (body content line), and `:>:` (block close). The parser is a line-oriented state machine that tracks fenced code blocks to avoid interpreting markers inside code examples. Each parsed directive becomes a `Directive` dataclass carrying its name, key-value attributes, optional body lines, and source location.

The main entry point is `parse_directives()`, which takes Markdown content and returns a list of `Directive` objects. It also supports inline directives (one-liners embedded mid-paragraph) and validates directive names against a provided set of known names, raising `DirectiveError` for unknown directives or unclosed blocks at EOF. Downstream modules -- `selfdoc.resolver`, `selfdoc.check`, and the build pipeline -- consume these parsed directives to extract content from source code and embed it in the generated documentation.

:-: ref path="selfdoc.directives" lang="python"
