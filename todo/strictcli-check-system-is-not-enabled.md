# The strictcli check system is not enabled, so the effects lints never run

Filed 2026-08-05, found while re-sweeping both CLIs onto strictcli's redesigned
confirmation protocol.

## Problem

Neither `selfdoc/cli.py` nor `selfblog/cli.py` passes `checks_path=` to
`strictcli.App(...)`. The check system is therefore off in both apps, and with
it the three checks strictcli ships as a built-in provider:

| Check | Severity | What it would catch |
|-------|----------|---------------------|
| `effects-bypass` | error | any direct subprocess launch, filesystem mutation or network call reachable from a registered command handler that does not route through `ctx.effects` |
| `observe-allowlist-breadth` | warn | single-token prefixes on the app's `proc_observe_allowlist` |
| `consequential-grant-agreement` | warn | a command declaring a `proc_mutate` / `net_mutate` grant without declaring itself `consequential` |

The first one matters most. strictcli's effects contract names the bypass lint
as the **sole stated mitigation** for its accepted no-sandbox ceiling: nothing
at runtime stops a handler from calling `subprocess.run` directly, so a dry run
that silently performs a real effect is caught by static analysis or not at all.
selfdoc and selfblog route everything through `selfdoc_core.effects` today, and
the existing `tests/test_effects_binding.py` pins that every *handler* carries
`@effects.handler` -- but nothing checks the bodies, or the helpers those bodies
call, which is exactly the scope rule the lint implements.

The third one is directly relevant to the consequential sweep: `assembly push`
and `assembly rebuild` deliberately carry escaping `PROC_MUTATE` grants without
being consequential, and that disagreement is precisely what the check is
designed to surface for review. Today the decision is recorded only as source
comments and a table in `tests/test_effects_binding.py`.

## Work

1. Add a `checks.toml` for each app (top-level `app` field must match the app
   name; the `[checks]` section may be empty -- the built-in provider registers
   its own checks through the provider hook, not through the TOML).
2. Pass `checks_path=` on both `strictcli.App(...)` constructions.
3. Note the collision risk: strictcli auto-registers a `check` command when
   checks are enabled, and **both apps already define their own `check`
   command** (`selfdoc check` validates docs; `selfblog check` validates posts).
   Resolve this before wiring anything -- it is the reason the system was
   probably never enabled. Options worth weighing: rename the framework's
   command, expose the checks under a different path, or run the lints from a
   test rather than the CLI.
4. Once enabled, run the lints and triage findings. Expect two
   `consequential-grant-agreement` warnings (`assembly push`,
   `assembly rebuild`) that are correct as-is and want `--ignore-warnings` or a
   recorded exclusion rather than a code change.
5. Wire the resulting gate into the release preflight via `external_checks` in
   the releasable config.

## Effort

Half a day, most of it on step 3 -- the `check` name collision is a real design
decision, not a mechanical wiring task.
