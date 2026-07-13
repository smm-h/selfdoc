# Version-embedding generated content is always one release stale

## Context

Projects that embed the project version in selfdoc-generated root files (via
custom directives like a version-reading directive, or any generated line of
the form "Current version: X") end up with the committed generated files
showing the PREVIOUS version after every release.

## Problem

The release pipeline runs `selfdoc gen` BEFORE the version bump (docs
freshness is checked pre-release, the bump happens later in the mutating
phase). So generation reads the pre-bump version, the bump lands afterward,
and the released tree carries root files stamped with the old version. Every
release repeats this: the generated version line is permanently one behind.

Observed concretely: a repo released N+1 while its generated CLAUDE.md still
reads "Current version: N" — and it will read N+1 only after the NEXT
release's gen pass, which will itself be stale for that release.

This is the same class as the CLI-schema version lag that rlsbl fixed for
strictcli schema dumps by patching the version into the dumped artifact
atomically AFTER the bump. Version-bearing selfdoc output has no equivalent
mechanism.

## Possible solutions

1. **Post-bump regeneration hook**: the release flow re-runs `selfdoc gen`
   (or a targeted regen of version-bearing pages only) after the version
   bump and includes the result in the release commit. Needs cooperation
   from the release orchestrator; selfdoc could expose a
   `selfdoc gen --only-version-bearing` fast path so the post-bump pass is
   cheap and safe.
2. **Late-binding version tokens**: version directives emit a placeholder
   that the release flow substitutes at finalize time (analogous to the
   schema-version patch). Keeps gen order unchanged; adds a substitution
   step.
3. **Next-version awareness**: gen accepts an explicit `--version-override`
   the release flow passes with the about-to-be-released version. Simple,
   but only correct when invoked from the release pipeline.

Whichever mechanism, staleness of version-bearing generated content should
be detectable — a check that the embedded version matches the current
version file would turn the silent lag into a visible failure.

## Effort

M — the mechanism itself is small; the work is the release-flow handshake
and tests across standalone + monorepo release shapes.
