# Validate minimum CLI help text length

## Problem

Short CLI help texts (under ~50 chars) cause SEO warnings when selfdoc generates documentation. Currently this is only caught at doc-generation time, not earlier.

## Proposed solution

selfdoc should validate help text length by reading the strictcli schema dump (`--dump-schema`). The schema includes all commands, flags, and their help text. selfdoc can check each entry against a configurable minimum length threshold and warn or error.

This belongs in selfdoc (not strictcli) because help text length is a documentation/SEO concern, not a CLI framework concern. strictcli validates that help text exists (non-empty) — whether it's long enough for documentation is selfdoc's policy.

## Effort

Small. Read schema JSON, iterate commands/flags, check help string length against threshold.
