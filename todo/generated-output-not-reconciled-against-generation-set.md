# Generated output is never reconciled against the current generation set

## Background

selfdoc gen writes per-module API pages (and other derived files) into the
consuming project's docs tree, where they are committed. When a module is
later excluded from generation via the project's configuration — or
deleted, or renamed — the previously generated pages for it are not
removed, not flagged, and not detected by selfdoc check. They persist
indefinitely as committed files that look like current documentation but
are orphans of an earlier configuration. A consuming project was found
carrying exactly this: a generated API page for a module whose package had
since been excluded from generation, sitting stale with nothing anywhere
aware of it.

The structural gap: generation is add-and-overwrite only. selfdoc does not
own its output set — there is no record of which committed files the
current configuration produces, so nothing can notice a committed file
that the current configuration no longer explains.

## What to consider doing

- Make generation own its output set: record the files the current
  configuration generates (a manifest alongside the other selfdoc state),
  and on regeneration remove — or at minimum report — committed generated
  files that the current run did not produce.
- Teach selfdoc check to error on orphaned generated output (a committed
  file bearing the generated-by marker that the current configuration
  does not account for), so the stale state is caught even when nobody
  regenerates.
- Decide the removal mechanics deliberately: deletion of a committed file
  is destructive and should go through the consuming project's safe
  deletion tooling or at least be its own reviewable change, not a silent
  side effect of gen.

## Why

Stale generated documentation misrepresents the project while carrying
the full authority of generated output — a reader has no way to tell an
orphan from a current page. The failure is silent by construction today;
only an ownership record or a check can make it visible.
