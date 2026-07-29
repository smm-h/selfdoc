---
title: selfdoc.check
description: "Check command -- validates directive resolution, measures documentation coverage, runs SEO lint rules, and detects stale or drifted descriptions."
nav_group: "API Reference"
nav_order: 5
---

# selfdoc.check

The check module validates documentation quality across multiple dimensions. Its main entry point, `check_docs()`, scans every Markdown template in `docs/`, parses directives, and attempts to resolve each one against the project's source code -- reporting per-directive OK/FAILED status. It then computes coverage: what fraction of public symbols in the source are referenced by at least one directive. Beyond directives, the module runs a suite of SEO lint rules (heading structure, title length, missing descriptions, alt text quality, link targets, color contrast) and detects stale or drifted descriptions via content hashing against stored baselines.

Results are returned as a `CheckResult` dataclass containing `DirectiveResult` entries, optional `CoverageStats`, and a list of `LintResult` diagnostics. Each lint has a code (e.g., `SEO001`, `STALE001`, `DRIFT001`), severity, file, and line number. The `accept_baselines()` function allows advancing the stored content hash for pages where a human has confirmed the description is still accurate despite source changes. Developers interact with this module through `selfdoc check` on the CLI; it also runs automatically during `rlsbl release run` as a pre-release gate.

:-: ref path="selfdoc.check" lang="python"
