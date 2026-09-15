# A custom directive's script runs under a `Read` effect declaration

## Context

A subprocess inventory across the fleet's Go tools on 2026-09-15 classified
every production child process by what its argv is built from and what
effect class it was declared under. One of selfdoc's came out mismatched.
Line references are as of that date; verify before acting.

## Problem

`internal/resolver/resolver.go`, in the custom-directive runner (the
`r.handle.Run(argv, effects.Read(), ...)` call near line 378), executes a
user-supplied script — the path comes from the project's directive
configuration, and for a `.py` file the embedded driver loads and calls it —
under `effects.Read()`. A script the consumer wrote can do anything: write
files, reach the network, run further programs. Declaring it a read tells
the effects handle, the would-do log and every consumer of the dry-run
preview that nothing is written, which is not a fact selfdoc can know.

The Python driver path makes the point sharper: the argv is
`python3 -c <driver> <script>`, an interpreter running arbitrary code.

## What the declaration should say

The effect class of a child is the child's, not the parent's intent.
selfdoc cannot prove the script is read-only, so it must not declare it so.
Two honest shapes:

- **Declare it mutating** (`effects.Mutating()` or the handle's equivalent),
  so that under `--dry-run` the script is not run and the would-do log
  names it. `selfdoc gen --dry-run` then cannot show the directive's output,
  which is the truth: the output comes from running foreign code.
- **Let the directive declaration carry the class.** The project's directive
  configuration gains a required field stating whether the script is pure
  (safe to run in a preview) or not, and selfdoc runs it under the class the
  consumer declared. This keeps previews useful for the common case (a
  formatter over a file) and puts the claim where the knowledge is.

The second is the design that matches the rest of the fleet: the consumer
declares, the tool enforces, nothing is inferred. It is also the one that
needs a red-green test for the refusal: a directive whose declaration says
pure and whose script writes a file must be reported, not trusted — the
runner can compare the world before and after (the scripts run inside the
project tree, which selfdoc already knows).

## Affected

`internal/resolver/resolver.go` (the runner), the directive configuration
schema and its docs page, the would-do log fixture for `gen --dry-run`, and
the directive test suite.

## Effort

Small for the first shape; medium for the second (a new required
configuration field, a migration step for existing consumers, and the
before-and-after check).
