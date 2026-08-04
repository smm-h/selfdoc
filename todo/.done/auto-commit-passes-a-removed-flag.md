# Auto-commit passes `--yes`, which the commit tools no longer accept

Filed 2026-08-05, found while running `selfdoc check` from a consumer repo.
This is a live breakage, not a future concern.

## Symptom

Every auto-commit path prints, and does not commit:

```
error: unknown flag '--yes'
```

`selfdoc gen` and `selfdoc check` still succeed at their real work (pages and
the content-hash baseline are written), so the failure is easy to miss: the
generated files are simply left uncommitted in the consumer's working tree,
which then trips that repo's clean-tree gate later.

## Cause

`selfdoc_core/git.py` builds the commit argv with `--yes`:

```
line 133:  cmd = ["rlsbl", "commit", "--yes", "-m", message, "--"] + committable
line 136:  cmd = ["safegit", "commit", "--yes", "-m", message, "--"] + committable
```

The CLI framework both of those tools are built on replaced the inferred
"mutating command ⇒ prompt" rule with a declared `consequential`, renamed the
confirmation-skip flag `--yes` → `--approve-consequential`, and put `yes` on
the banned-flag-names list. Neither commit command is `consequential` (a commit
is ordinary, undoable work), so neither prompts and neither takes any
confirmation flag at all.

## Fix

Drop `--yes` from both branches. The bare invocations are correct:

```
["rlsbl", "commit", "-m", message, "--"] + committable
["safegit", "commit", "-m", message, "--"] + committable
```

Do NOT substitute `--approve-consequential` here: those two commands do not
declare themselves consequential, so the flag would be accepted (it is
framework-global) but would be stating a decision nobody asked for, and it
would reappear in every argv assertion in the suite as noise.

## Worth sweeping while in there

Any other subprocess invocation of a framework-based tool. The failure mode is
a hard non-zero exit with an opaque `unknown flag` line, so it surfaces as
whatever wraps the call — and where the call site tolerates failure (as this
one does), it surfaces as nothing at all until something downstream notices the
dirty tree.

A regression test that runs the REAL commit binary in a throwaway git repo and
asserts the commit landed would catch the next rename in the suite instead of
in a consumer's release. An argv-pinning mock cannot: it asserts the flag the
code passes, not the flag the callee accepts.

## Effort

Two lines plus the sweep and one real-binary regression test.
