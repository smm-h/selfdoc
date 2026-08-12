# Two publish-path gaps: CI-unreachable accept list, home project docs publish

## 1. Full-scope CI builds cannot reach the spelling accept list

`ACCEPT_LIST_PATH` is hardcoded to `~/Projects/ark/spelling-accept.txt`
(selfdoc_core/spelling.py:74) — no env var, no config key, no assembly-local
fallback, and `check.py` calls `load_accept_list()` with no argument. On a
GitHub runner the list is unreachable, so any full-scope project build in the
assembly workflow fails with SPELL001 on every genuine term (measured: 1548
errors vs 1 with the list). The shared-only and home-build paths never touch
spelling, so the current deploys work — but `selfblog assembly push` from
post-release hooks dispatches full-scope builds that will always fail CI-side.

Shape to decide: the source of truth stays the single local file; the sync or
publish path pushes a derived copy into the assembly repo as a build input
(like manifests), and the resolution order becomes explicit — an
assembly-local copy when present, else the local path, never silence. A
missing list where spelling runs should be a hard error naming both locations,
not 1548 misleading errors.

## 2. `docs publish` cannot publish the home project

`cli.py:534` calls `build_source_project(".", "full")` without `home=True`, so
the home project builds as an ordinary project: site directives hard-error
(correctly), and even with them resolved it would land in `site/<slug>/`
instead of the site root. The working route today is pushing the home repo's
main and dispatching `project-updated` with full scope — the deploy-side
integrate handles home correctly. The local `docs publish` path should either
detect the home slug from the roster and route through the home build, or
refuse loudly naming the dispatch route. Silent wrong-mount publishing is the
one outcome it must never have (today it is blocked only by the directive
hard-error, which is accidental protection).

## Effort

Both small-medium; (1) needs a design call on the derived-copy refresh points,
(2) is routing plus a red-green fixture.
