# pagefind is required but has no durable install path

## Context

`selfdoc check` (and the build) hard-errors when `selfdoc.json` declares
`"search_engine": "pagefind"` and pagefind is not installed — an
unconditional SEARCH001 error. The probe looks for `sys.executable -m
pagefind`, then `pagefind` on PATH.

## Problem

There is no durable way to satisfy the requirement on an operator machine:

- the `pagefind` wheel ships NO console script, so `uv tool install
  'pagefind[bin]'` fails with "No executables are provided" — it cannot
  exist as a standalone tool on PATH;
- the working install is `uv pip install --python <selfdoc tool venv
  python> 'pagefind[bin]'` — injecting it into selfdoc's own tool venv so
  the `sys.executable -m pagefind` probe finds it. This was done by hand on
  this machine to unblock a consumer project's release preflight.

That injection is FRAGILE: any `uv tool install --force` / `uv tool
upgrade` of selfdoc rebuilds the venv and silently drops pagefind, and the
next release preflight in any pagefind-declaring consumer fails again with
SEARCH001. A machine-wide tool-venv rebuild (which happens — one such sweep
rebuilt every tool venv on this machine recently) wipes it too.

## Solutions

1. **Declare pagefind as an optional extra of selfdoc itself** (e.g.
   `selfdoc[search]` depending on `pagefind[bin]`), and document installing
   the tool as `uv tool install 'selfdoc[search]'`. The dependency then
   survives every venv rebuild by construction. Pros: durable, declared,
   zero hand-injection. Cons: heavier default install for users who never
   build search; choose whether the extra or the base carries it.
2. **Make the SEARCH001 error's remediation text state the working
   install command** (the venv-injection form, naming the caveat that
   upgrades drop it) so the operator at least gets the correct incantation
   instead of discovering the no-console-script dead end themselves.
   Complements option 1; insufficient alone (still fragile).
3. **Vendor/download pagefind's binary on demand** like other toolchain
   launchers do. Most machinery; probably unwarranted.

Option 1 plus the improved message (2) removes the recurrence.

## Affected files

- selfdoc's pyproject (extras) and install docs
- the SEARCH001 error text

## Effort

Small.
