# Assembly subdirectory support, and directive failures must fail the build

## Background

selfdoc builds docs from the directory containing `selfdoc.json` and has no
repo-root concept of its own — everything is base-dir-relative, and the docs
source directory is already a config key. The unified assembly transport,
however, assumes the published project is the checkout root: the dispatch
payload carries no subdirectory field, the generated assembly workflow checks
the repo out and integrates the checkout root, the membership record cannot
replay a subdirectory, and GitHub "Edit this page" links are built from a
repo-root-relative docs path. `assembly integrate` already has a
`--source-dir` flag; nothing upstream ever supplies the value.

Separately: when a custom docs directive fails at build time (for example a
table generator that cannot import its host package), the error is rendered
into the page as an inline error string and the build still reports success.
A published page can silently lose an entire generated table this way — this
has been observed in a local build where every generated support table had
degraded to an error string.

## What to consider doing

- Make a failed directive a hard build error. A build that cannot render a
  declared directive should not succeed.
- Add member-subdirectory support to the assembly transport: carry the
  subdirectory in the dispatch payload, pass it through the generated
  workflow as `--source-dir`, and persist it in the membership record so
  `assembly rebuild` replays the right tree. These three must ship together —
  a half-state (subdir reaching integrate but not the membership record)
  makes the next rebuild silently publish the repo root under the project's
  slug. A past incident of the neighboring kind shipped a 404 stub to the
  live site.
- Fix edit links to carry a repo-root-relative prefix when the docs source
  is below the repo root (derivable from `git rev-parse --show-prefix`).
- Note the ordering constraint: the assembly workflow installs pinned
  selfblog/selfdoc versions, so a payload field is only understood after a
  selfblog release. Ship the feature, release, then let consumers adopt.

## Why

The directive behavior is silent degradation: published documentation can
lose generated content while the pipeline reports green. The subdirectory
support unblocks monorepo members keeping member-scoped docs — the code
already half-expects this (per-member `selfdoc.json` discovery exists in the
unified-site validator) but no transport path can deliver it.
