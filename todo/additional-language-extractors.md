# Additional language extractors

## Swift

incantino has real iOS source (ContentView, ActionDispatcher, ConfigProvider) — 10 files with application logic. Swift has `public`/`open` visibility, `///` doc comments, `struct`/`class`/`enum`/`protocol` types. Detection via `Package.swift`. Very similar to the Zig extractor patterns. Small effort.

## Kotlin

Currently zero `.kt` application source across ~/Projects — all 27 `.kts` files are Gradle build scripts. File a placeholder for when real Kotlin source appears. Kotlin has `public`/`internal` visibility, `/** */` KDoc comments, `class`/`data class`/`object`/`fun` declarations. Detection via `build.gradle.kts` or `src/main/kotlin/`. Medium effort.

## Dart

Covered separately in `dart-extractor.md` (detailed todo already exists). Motivated by a 41-package Flutter monorepo.

## SQL (schema extraction)

46 SQL files across projects — schema definitions, migrations, generated DDL. SQL doesn't fit the traditional public-API extraction model (no functions/classes), but `CREATE TABLE` definitions are documentation-worthy (table name, column types, constraints, comments). This would be a different kind of directive — `table-schema` reading from `.sql` files rather than source structs. Detection via `.sql` files in a declared path. Medium effort, novel concept.

## Svelte

10 Svelte files across PixelWeaver, ClaudeTimeline, ProductEngine, gamehome. Svelte components have `<script>` blocks containing TypeScript/JavaScript. The TypeScript extractor could theoretically parse the script section if it learned to strip the template/style markup first. Detection via `.svelte` files. Small-medium effort — mostly preprocessing before delegating to the existing TypeScript extractor.
