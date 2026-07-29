---
title: selfdoc.cli
description: "CLI interface for selfdoc -- defines the command-line entry point, argument parsing via strictcli, and subcommand dispatch for all commands."
nav_group: "API Reference"
nav_order: 6
---

# selfdoc.cli

The cli module defines selfdoc's command-line interface using strictcli. It registers the top-level `selfdoc` app and all subcommands: `init`, `build`, `serve`, `check`, `gen`, `gen-data`, `deploy`, and `quality`, plus command groups for `post`, `assembly`, and `baseline`. Each command function parses flags, loads config via `selfdoc.config`, and delegates to the corresponding implementation module. The `serve` command starts an HTTP server with live-reload for local development.

Several commands that previously lived in selfdoc (`post new`, `post list`, `post generate`, `post publish`, and the `assembly` subcommands) have been migrated to the standalone `selfblog` CLI. Their registrations remain as stubs that emit a directed error message, so old invocations fail cleanly instead of producing an unknown-command error. Developers typically interact with this module indirectly by running `selfdoc <command>` on the command line; the `run()` function at the bottom is the entry point called by `python -m selfdoc` and the npm wrapper.

:-: ref path="selfdoc.cli" lang="python"
