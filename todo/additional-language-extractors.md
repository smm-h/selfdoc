# Additional language extractors

## Dart

The F monorepo (~/Work/F) is a 41-package Flutter monorepo. Dart is the primary language (641 files, 40 source entries in selfdoc.json). This is the highest-priority extractor.

Modern Dart 3+ only. Parse `.dart` files and extract:

**Constructs:** Classes (including abstract, sealed, base, final, interface modifiers), sealed class hierarchies as one documented unit, enums with members, extension types, top-level functions, top-level variables and constants, records. Skip mixins, typedefs, `part`/`part of`.

**Doc comments:** `///` triple-slash only. Parse dartdoc Markdown: `[ClassName]` cross-references, `{@macro}`, `{@template}`, `{@example}` tags.

**Directive path resolution:** File-relative (`lib/src/order.dart`) and package-style (`package:marketplace_contract/order_state.dart` resolves via `pubspec.yaml`). Package-style is essential for cross-package references in the monorepo unified site.

**Export following:** When targeting a barrel file (`lib/marketplace_contract.dart` with `export 'src/order.dart'`), follow exports and extract the full public API surface. Do NOT follow `part`/`part of`.

**Annotation-aware extraction:**
- `@freezed`: Code-generated immutable data class. Extract annotated source, append "Generated members" section (copyWith, ==, hashCode, toString, when/map for unions, toJson/fromJson if JsonSerializable).
- `@riverpod`: Provider definition. Document as a provider with dependencies and return type, not a plain function/class.

**Flutter widget recognition:** Classes extending StatelessWidget/StatefulWidget — present constructor parameters as the widget's "props" (public API), not as a generic class.

**Exclude:** Generated files (`.g.dart`, `.freezed.dart`), test files, private members.

**Detection:** `pubspec.yaml` in the project root.

**Monorepo integration:** Each of 35 Dart packages becomes a section in the unified site. Cross-package `[ClassName]` references resolve to the correct package's page. Spec packages (YAML/JSON data) get file-listing pages, not AST extraction.

**Effort:** Large — export following, annotation awareness, and cross-package resolution are non-trivial.

## Swift

incantino has real iOS source (ContentView, ActionDispatcher, ConfigProvider) — 121 files with application logic. Swift has `public`/`open` visibility, `///` doc comments, `struct`/`class`/`enum`/`protocol` types. Detection via `Package.swift`. Very similar to the Zig extractor patterns.

**Effort:** Small.

## Kotlin

Currently zero `.kt` application source across ~/Projects — all `.kts` files are Gradle build scripts. incantino has 130 `.kt` files across android/incantino-core and android/incantino-compose. Kotlin has `public`/`internal` visibility, `/** */` KDoc comments, `class`/`data class`/`object`/`fun` declarations. Detection via `build.gradle.kts` or `src/main/kotlin/`.

**Effort:** Medium.

## SQL (schema extraction)

46 SQL files across projects — schema definitions, migrations, generated DDL. SQL doesn't fit the traditional public-API extraction model (no functions/classes), but `CREATE TABLE` definitions are documentation-worthy (table name, column types, constraints, comments). This would be a different kind of directive — `table-schema` reading from `.sql` files rather than source structs. Detection via `.sql` files in a declared path.

**Effort:** Medium, novel concept.

## Svelte

94 Svelte files across incantino (74) and gamehome (20). Svelte components have `<script>` blocks containing TypeScript/JavaScript. The TypeScript extractor could theoretically parse the script section if it learned to strip the template/style markup first. Detection via `.svelte` files.

**Effort:** Small-medium — mostly preprocessing before delegating to the existing TypeScript extractor.
