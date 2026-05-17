# code-help: package path resolution + strictcli support

## Problem 1: path="." fails in code-help but works in ref

`selfdoc check` on saferm:

```
index.md:12  code-help path="."  FAILED: file '.' not found
index.md:16  ref path="internal/archive"  OK
```

The `ref` directive resolves `"."` to the root package directory via `_resolve_package_dir`. The `code-help` directive treats the argument as a literal file path instead of a package path, so `"."` fails. `selfdoc build` handles it fine -- only `check` fails.

## Problem 2: code-help only supports stdlib flag

`code-help` extracts:
- Constants/vars named "usage"/"help" with backtick-quoted strings
- `flag.StringVar`, `flag.BoolVar`, etc. calls

Projects using other CLI frameworks (strictcli, cobra, urfave/cli) get no extraction. saferm uses strictcli, so `code-help` produces nothing even when the path resolves.

## Suggested fixes

1. Make `code-help` use `_resolve_package_dir` like `ref` does, so `path="."` and package paths work.
2. For Go CLI framework support, consider extracting from:
   - strictcli: `BoolFlag("name", "help")`, `StringFlag("name", "help")`, `app.Command("name", "help", ...)`
   - cobra: `&cobra.Command{Use: "name", Short: "help"}`, `cmd.Flags().StringVar()`
   - Or: a generic approach that extracts from `--help` output by running the built binary

## Reproduction

```
cd ~/Projects/saferm
selfdoc check
# code-help path="."  FAILED: file '.' not found
```
