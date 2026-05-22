---
title: Multi-Language Support
description: "Using selfdoc with Go and TypeScript/JavaScript projects: language extractors, directive examples, source detection, and cross-language limitations."
nav_group: "Guides"
nav_order: 15
---

# Multi-Language Support

selfdoc supports three languages out of the box: **Python**, **Go**, and **TypeScript/JavaScript**. Each language has its own extractor that knows how to read source files and resolve directives. The same directive syntax works across all languages -- only the source file format changes.

## Setting the Language

Set `language` in your `selfdoc.json`:

```json
{
  "language": "go"
}
```

Valid values: `python`, `go`, `typescript`, `javascript` (alias for `typescript`).

If you omit `language`, selfdoc auto-detects by checking for marker files in your project root: `pyproject.toml` or `setup.py` for Python, `go.mod` for Go, `package.json` or `tsconfig.json` for TypeScript. Detection priority is Python, then Go, then TypeScript.

## Go Examples

### Module reference

Show package-level documentation and exported functions:

```markdown
:<: ref path="internal/config"
:=:
:>:
```

This extracts the package doc comment and lists exported functions with their signatures and doc comments.

### Struct schema table

Render a struct's fields as a table:

```markdown
:<: table-schema path="internal/server/handler.go" target="ServerConfig"
:=:
:>:
```

This finds the `ServerConfig` struct and generates a table with field names, types, and doc comments (or struct tags).

### Embedding test code

Pull a test function into your docs as a code example:

```markdown
:<: code-test path="internal/config/config_test.go" target="TestLoadConfig"
:=:
:>:
```

The test body is rendered as a Go code block, giving readers a real example they know actually compiles.

## TypeScript / JavaScript Examples

The TypeScript extractor handles `.ts`, `.tsx`, `.js`, and `.jsx` files.

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

Each extractor knows which file extensions to scan:

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
