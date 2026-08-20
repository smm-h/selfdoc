# Reversibility gaps: commands whose inverse is missing

## Context

strictcli is gaining declared reversibility support: a mutating command will
declare which command undoes it (verified at registration in both
directions), a command with no recovery will declare irreversible with a
mandatory reason, a warn-severity check will flag destructive commands
declaring neither, and after a real run the framework will print a paste-able
recovery command and emit a machine-readable recovery member in the JSON
result document. When this repo adopts that support, every gap below needs
either a built inverse or an honest irreversible declaration.

## Problems

1. **`selfdoc deploy` has no rollback.** The hosting platform supports
   deployment rollback; the command is one-directional against a provider
   offering the return leg.
2. **`selfdoc init` has no uninit.**
3. **`docs publish` and `post publish` have no retract.** `assembly retire`
   retires a whole project, not a single post or docs version — there is no
   per-item return leg.

## Effort

Deploy rollback: small-medium (a thin command over the platform's rollback).
Uninit: small. Publish retract: medium (the assembly needs a per-item
removal path, not only whole-project retirement).
