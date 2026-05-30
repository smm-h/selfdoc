# gen doesn't validate schema app_name

## Problem

`selfdoc gen` reads `.strictcli/schema.json` and generates CLI docs from it without checking that the schema's app name matches the project. If the schema is corrupted (wrong app), selfdoc silently generates docs for the wrong CLI tool.

## Affected code

`selfdoc/strictcli_support.py` -- `extract_cli_structure` reads `schema.get("name")` but never validates it against the project.

## Fix

Compare schema `name` against the project name (from `selfdoc.json` or the source directory name). Hard error if mismatch.
