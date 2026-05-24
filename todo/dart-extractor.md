# Dart extractor

## Context

The F monorepo (~/Work/F) is a 41-package Flutter monorepo that needs documentation via selfdoc's unified site feature (0.8.0). selfdoc currently supports Python, Go, and TypeScript. Dart is the fourth language.

This extractor only needs to support modern Dart 3+ patterns. Legacy Dart (pre-null-safety, old class syntax, `/** */` comments, `part`/`part of`) is out of scope.

## What we need

### Dart AST extraction

Parse `.dart` files and extract:

**Constructs:**
- Classes (including abstract, sealed, base, final, interface modifiers)
- Sealed class hierarchies as one documented unit (the sealed parent + all direct subclasses, shown together)
- Enums with members (fields, methods, named constructors)
- Extension types (`extension type Foo(int i) implements int`)
- Top-level functions
- Top-level variables and constants
- Records (named fields and positional fields in type signatures)

**Not needed:**
- Mixins (we use sealed classes and composition instead)
- Typedefs (we use inline function types or extension types)
- `part`/`part of` (we use `export` barrel files, not parts)

### Doc comments

Only `///` triple-slash comments. No `/** */` block comments.

Must parse dartdoc Markdown inside `///` comments:
- `[ClassName]` and `[ClassName.member]` cross-references (resolve to links in the docs site)
- Inline code, code blocks, bullet lists
- `{@macro name}` and `{@template name}` tags (used by Flutter SDK, may appear in our code)
- `{@example}` tags if present

### Directive path resolution

Support both styles:
- File-relative: `lib/src/order.dart` (consistent with Go/TS extractors)
- Package-style: `package:marketplace_contract/order_state.dart` resolves to `marketplace_contract/lib/order_state.dart` by reading the package name from the target package's `pubspec.yaml`

Package-style is essential for the monorepo unified site: when documenting `flow_order`, directives reference types from `marketplace_contract`, `payments_contract`, etc. Cross-package references are the norm, not the exception.

### Export following

When a directive targets a barrel file (e.g., `lib/marketplace_contract.dart` that contains `export 'src/order.dart'; export 'src/listing.dart';`), follow the exports and extract the full public API surface. This is how Dart packages define their API: one barrel file re-exports everything public.

Do NOT follow `part`/`part of` directives (we don't use them).

### Annotation-aware extraction

Two annotations that fundamentally change what the public API looks like:

**`@freezed` (package:freezed_annotation)**
- When a class is annotated `@freezed`, it's a code-generated immutable data class
- The source defines: class name, constructor parameters (the fields), union cases (factory constructors)
- The generated `.freezed.dart` file adds: `copyWith()`, `==`/`hashCode`, `toString()`, `when()`/`map()` for union types, `toJson()`/`fromJson()` if `@JsonSerializable` is also present
- selfdoc should: extract the annotated source (not the generated file), recognize `@freezed`, and append a "Generated members" section documenting the implied API. The exact generated members depend on the class structure (union vs single-class, json-serializable vs not).

**`@riverpod` (package:riverpod_annotation)**
- When a function or class is annotated `@riverpod`, it defines a Riverpod provider
- The source defines: the function/class, its parameters (dependencies), its return type
- The generated `.g.dart` file adds: a `Provider` variable, `Ref` type, auto-dispose behavior
- selfdoc should: extract the annotated source, recognize `@riverpod`, and document it as a provider with its dependencies and return type, not as a plain function/class

### Flutter widget recognition

Flutter widgets follow a recognizable pattern:
- `class Foo extends StatelessWidget` or `class Foo extends StatefulWidget`
- Constructor parameters are the widget's "props" (its public API)
- `build(BuildContext context)` method is the render logic

selfdoc should recognize this pattern and present widgets with their constructor parameters prominently (these are what consumers pass in), rather than treating them as generic classes where the constructor is one member among many.

### What NOT to extract

- Generated files (`.g.dart`, `.freezed.dart`) -- read annotations from source instead
- Test files (`test/`, `integration_test/`) -- not public API
- Private members (names starting with `_`) unless explicitly targeted

## Integration with monorepo unified site

selfdoc 0.8.0's unified site reads rlsbl workspace.toml. For the F monorepo:
- Each of the 35 Dart packages becomes a section in the unified site
- `selfdoc gen` should produce per-package API reference pages
- Cross-package `[ClassName]` references in doc comments should resolve to the correct package's page in the unified site
- The 3 spec packages (sdui_spec, llm_spec, conformance_spec) are YAML/JSON data, not Dart -- they should get simple file-listing pages, not AST extraction
- The 1 Python package (tooling) uses the existing Python extractor

## Affected projects

- F (~/Work/F) -- 41-package Flutter monorepo, the immediate consumer
- Any future Dart/Flutter project using selfdoc
