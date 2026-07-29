---
title: selfdoc.build
description: "Build pipeline for selfdoc -- scans docs/ templates, resolves directives against source code, and generates static HTML output."
nav_group: "API Reference"
nav_order: 4
---

# selfdoc.build

The build module is the central pipeline that turns Markdown templates and source code into a complete documentation site. It loads `selfdoc.json`, scans the `docs/` directory for templates, resolves all directives against the project's source files, converts the resolved Markdown to HTML via `selfdoc.html`, and writes the output to disk. A single invocation handles multi-version builds (checking out tagged versions from git), multi-locale builds (iterating locale directories), and the generation of auxiliary files such as sitemaps, Atom feeds, OpenGraph images, `robots.txt`, `llms.txt`, and search indexes.

The outer entry point is `build()`, which loops over locale/version combinations and delegates to `build_single()` for each one. `build_single()` is a pure computation that returns a `BuildResult` dataclass without writing to disk -- the caller handles all I/O. After all versions are built, `_generate_auxiliary_files()` produces the cross-version assets (sitemap index, combined search index, compressed output). Developers interact with this module through `selfdoc build` on the CLI; it is also invoked by `selfdoc check` to validate directive resolution and by `rlsbl release run` as part of the release pipeline.

:-: ref path="selfdoc.build" lang="python"
