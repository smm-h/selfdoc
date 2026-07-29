---
title: selfdoc.config
description: "Config loader for selfdoc.json -- reads project settings, validates required fields, and resolves paths for the build pipeline."
nav_group: "API Reference"
nav_order: 7
---

# selfdoc.config

The config module loads and validates `selfdoc.json`, the project-level configuration file that controls every aspect of the documentation build. It defines a declarative schema (`CONFIG_SCHEMA`) of `FieldSpec` entries covering required fields like `source` (list of source paths with languages) and `base_url`, plus dozens of optional settings for theming, search engine selection, code block behavior, SEO metadata, deploy provider, versioning, localization, and more. The `load_config()` function reads the JSON file, rejects unknown keys, validates each field against its spec (type, pattern, choices, min/max constraints), applies defaults, and runs post-validation checks.

Configuration errors surface as `ConfigError` exceptions with actionable messages. The module also handles migration: legacy field names like a top-level `language` key produce clear errors directing users to the current format. Nearly every other module in selfdoc depends on this one -- `build`, `check`, `gen`, `deploy`, and `cli` all begin by calling `load_config()` to obtain the validated config dict that drives their behavior.

:-: ref path="selfdoc.config" lang="python"
