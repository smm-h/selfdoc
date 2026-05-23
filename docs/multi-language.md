---
title: Multi-Language Support
description: "Using selfdoc with Go and TypeScript/JavaScript projects: language extractors, directive examples, source detection, and cross-language limitations."
nav_group: "Guides"
nav_order: 15
---

# Multi-Language Support

selfdoc supports 3 languages out of the box: **Python**, **Go**, and **TypeScript/JavaScript**. Each language has its own extractor that knows how to read source files and resolve directives. The same directive syntax works across all languages -- only the source file format changes.

## Setting the Language

Set `language` in your `selfdoc.json` to tell selfdoc which extractor to use when resolving directives against your source code. If omitted, selfdoc auto-detects the language by checking for marker files like `pyproject.toml`, `go.mod`, or `package.json` in your project root:

```json
{
  "language": "go"
}
```

Valid values: `python`, `go`, `typescript`, `javascript` (alias for `typescript`).

If you omit `language`, selfdoc auto-detects by checking for marker files in your project root: `pyproject.toml` or `setup.py` for Python, `go.mod` for Go, `package.json` or `tsconfig.json` for TypeScript. Detection priority is Python, then Go, then TypeScript.

## Go Examples

### Module reference

Show package-level documentation and all exported functions for a Go package. The `ref` directive extracts the package doc comment from the source files and lists every exported function with its full signature and associated doc comment. Use the package import path relative to your `source` directories:

```markdown
:<: ref path="internal/config"
:=:
:>:
```

### Struct schema table

Render a Go struct's exported fields as a Markdown table with columns for field name, type, and documentation extracted from doc comments or struct tags. This is useful for configuration structs, request/response types, and any data structure readers need to understand at a glance:

```markdown
:<: table-schema path="internal/server/handler.go" target="ServerConfig"
:=:
:>:
```

This finds the `ServerConfig` struct and generates a table with field names, types, and doc comments (or struct tags).

### Embedding test code

Pull a Go test function body into your documentation as a runnable code example. The `code-test` directive extracts the function body and renders it as a Go code block, giving readers a real example they know compiles and passes tests:

```markdown
:<: code-test path="internal/config/config_test.go" target="TestLoadConfig"
:=:
:>:
```

The test body is rendered as a Go code block, giving readers a real example they know actually compiles.

## TypeScript / JavaScript Examples

The TypeScript extractor handles 4 file extensions (`.ts`, `.tsx`, `.js`, `.jsx`) using regex-based parsing to match `export` declarations, interfaces, type aliases, and JSDoc/TSDoc comments. The same directive syntax works across all four file extensions since they share the same export conventions:

### Module reference

```markdown
:<: ref path="src/client"
:=:
:>:
```

Shows exported functions, classes, and interfaces from the module with their JSDoc or TSDoc comments.

### Interface or class schema

```markdown
:<: table-schema path="src/types.ts" target="AppConfig"
:=:
:>:
```

Renders an interface or class as a table of property names, types, and descriptions from doc comments.

### Code examples from tests

```markdown
:<: code-test path="src/__tests__/client.test.ts" target="creates a new client"
:=:
:>:
```

For TypeScript tests, the `target` matches the test description string (the first argument to `it()` or `test()`).

## Source File Detection

Each language extractor knows which file extensions to scan when walking your source directories. Only files matching the active extractor's extensions are read during directive resolution, coverage analysis, and symbol enumeration for the auto-generated documentation pages:

| Language | Extensions |
| --- | --- |
| Python | `.py` |
| Go | `.go` |
| TypeScript/JavaScript | `.ts`, `.tsx`, `.js`, `.jsx` |

The `source` config array tells selfdoc which directories to scan for source files:

```json
{
  "language": "go",
  "source": ["internal/", "cmd/"]
}
```

## Cross-Language Limitations

Each project has one language. If your codebase has a Go backend and a TypeScript frontend, selfdoc documents one at a time. For multi-language documentation, the recommended approach is a monorepo-style setup where each component is its own selfdoc project with its own `selfdoc.json`, and you use unified builds to merge them into a single site.

> [!NOTE]
> The `javascript` language value is an alias for `typescript` -- they use the same extractor and the same file extensions. Use whichever name matches your project.

Next: [Root Files](root-files/) -->
