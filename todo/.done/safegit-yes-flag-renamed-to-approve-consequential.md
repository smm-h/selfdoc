# safegit's `--yes` is gone; `selfdoc gen`'s auto-commit is broken

Filed 2026-08-04, immediately after safegit adopted go-strictcli 0.29.0's redesigned
confirm protocol. This is a **live breakage**: a bare `selfdoc gen` regenerates the docs
and then silently fails to commit them, leaving the working tree dirty.

## What changed upstream

strictcli replaced the inferred "mutating command ⇒ prompt" rule. Commands now declare
themselves `consequential`, the framework prompts only for those, and the skip flag was
renamed `--yes` → `--approve-consequential`. **`yes` is now a banned flag name**: passing
`--yes` to a strictcli 0.29.0+ app is a hard error (`error: unknown flag '--yes'`), not a
no-op.

`safegit commit` is **not** consequential — it never prompts, from any caller, with no flag
at all. The four safegit commands that still prompt (`scrub file`, `scrub match`,
`scrub run`, `author rewrite`) are ones selfdoc does not invoke.

## Where selfdoc breaks

`selfdoc_core/git.py`, the commit helper:

```python
if shutil.which("rlsbl"):
    cmd = ["rlsbl", "commit", "--yes", "-m", message, "--"] + committable
elif shutil.which("safegit"):
    cmd = ["safegit", "commit", "--yes", "-m", message, "--"] + committable
```

The `safegit` branch fails with `error: unknown flag '--yes'`. Fix: drop `--yes` from that
branch entirely.

The `rlsbl` branch fails too, but for a different reason and needs a different fix: `rlsbl`
has *not* migrated, so `rlsbl commit` still wants `--yes` for its own confirm protocol —
and then internally shells out to `safegit commit --yes`, which now hard-errors. So the
rlsbl branch is broken from the inside until rlsbl migrates, regardless of what selfdoc
passes. A todo covering that has been filed in rlsbl. Until it lands, `selfdoc gen`'s
auto-commit fails on both branches wherever both tools are installed.

The comment block above those lines explains the reasoning for passing `--yes`
(non-interactive callers; the confirmation was already taken by selfdoc's own mutating
command). That reasoning is now moot for `safegit commit` — there is no gate to satisfy —
and the comment should be rewritten rather than reworded, because it describes a protocol
that no longer exists.

## How it surfaces

Silently, which is the dangerous part. `selfdoc gen` prints its normal per-file generation
output and exits 0; only `git status` afterwards reveals the uncommitted regenerated files.
A release pipeline that regenerates and expects a clean tree will fail later, somewhere
less obvious. Worth considering whether a failed auto-commit should be a hard error rather
than a silent skip.

Also worth a look while in there: `saferm` made the same move. Only `saferm purge` is
consequential now; `saferm delete` and `saferm undelete` run bare.

## Effort

Ten minutes for the safegit branch plus a test that pins the argv. The rlsbl branch is
blocked on rlsbl's own migration; deciding whether a failed auto-commit should be fatal is
a separate, larger question.
