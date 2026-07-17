# Assembly pipeline and docs inconsistencies

Findings from a 2026-07-17 investigation of the selfblog assembly design and the
publishing pipeline to Cloudflare Pages (smmh.dev). Several inconsistencies and
one docs regression were identified. None are release blockers, but each one is
a trap for the next agent or a future config change.

## Context

The assembly system publishes a unified multi-project site to the CF Pages
project `smmh` (serving docs.smmh.dev) from the private assembly repo
`smm-h/selfdoc-cache`. Two publish paths exist: the release path (post-release
hook -> `selfblog assembly push` -> repository_dispatch -> CI clone/build/deploy)
and the post-only path (`selfblog post publish` -> Git Data API commit ->
`shared-only` dispatch). Each project additionally still deploys a standalone
site (CF project `selfdoc` -> selfdoc.smmh.dev) via `selfdoc deploy`.

## Problem 1: `assembly init` creates a Pages project that is never used

`selfblog/cli.py` (~line 461): `assembly init` runs
`npx wrangler pages project create <repo-basename>` -- for the current config
that would be a project named `selfdoc-cache`. But the deploy workflow generated
by `assembly.py` (~line 186) hardcodes `wrangler pages deploy site/
--project-name smmh`. The project init creates is not the project deploys
target; the real `smmh` project must have been created manually. Anyone running
`assembly init` fresh gets a broken pipeline (deploy targets a project that
init never created) plus an orphan Pages project.

Solutions:

- **(a) Add a required Pages project name to config** (e.g.
  `assembly.pages_project` in `selfdoc.json`), used by BOTH `assembly init`
  (project create) and the generated workflow (deploy target). No default --
  hard error if missing, per the no-implicit-defaults rule.
  - Pros: single source of truth; init and deploy can no longer diverge; the
    most correct fix.
  - Cons: config schema change + regenerating the assembly repo's workflow
    file; needs a migration note for existing assembly repos.
- **(b) Derive both from the repo basename** (make the workflow use the
  basename too).
  - Pros: no new config key.
  - Cons: renaming/moving the assembly repo silently changes the deploy
    target; couples a CF resource name to a GitHub repo name; the existing
    `smmh` project does not match the current basename, so this breaks the
    live setup unless the repo is renamed.

Recommendation: (a). Also decide whether the orphan `selfdoc-cache` Pages
project (if it exists in CF) should be deleted -- verify in CF dashboard first.

## Problem 2: three different blog URLs coexist

- `selfdoc.json` `topology.posts_base` = `https://blog.smmh.dev`
- The actual unified blog index is served at `https://docs.smmh.dev/blog/`
- The generated `_worker.js` (`selfblog/cli.py` ~lines 818-830) hardcodes a 301
  from host `blog.smmh.dev` to `https://smmh.dev/blog<path>` (the apex -- a
  third location, which is not where the blog index lives unless the apex is
  also wired to the `smmh` Pages project)

At minimum one of these is wrong. If smmh.dev apex is NOT a custom domain on
the `smmh` Pages project, the `_worker.js` redirect sends visitors to a dead
URL.

Solutions:

- **(a) Make the redirect target derive from `topology.docs_base`** (redirect
  blog.smmh.dev -> `<docs_base>/blog<path>`) and reconcile `posts_base` to
  document what it actually controls (feed/post canonical URLs vs. blog index
  host). Audit every consumer of `posts_base` in `selfblog/` and
  `selfdoc_core/` and write down the intended semantics.
  - Pros: removes the hardcoded hostname; config becomes the source of truth.
  - Cons: requires deciding the intended canonical blog URL first (user
    decision, not an agent decision).
- **(b) Just fix the hardcoded target** to `docs.smmh.dev/blog`.
  - Pros: minimal.
  - Cons: leaves the hardcoding in place; posts_base stays misleading.

Recommendation: (a), preceded by an explicit user decision on the canonical
blog URL. Verify with curl what blog.smmh.dev and smmh.dev/blog actually serve
today before changing anything.

## Problem 3: hardcoded deploy target and redirect host in generated artifacts

Same root cause as problems 1-2, listed separately because the fix is
structural: the generated workflow yaml (`assembly.py`) and `_worker.js`
(`cli.py`) embed literal values (`smmh`, `blog.smmh.dev`, `smmh.dev/blog`)
instead of reading from `selfdoc.json` topology/assembly config at generation
time. Any user of selfblog other than this monorepo gets our hostnames baked
into their assembly repo.

Solution: template all generated artifacts from config (no defaults for
deploy-target values -- hard error when missing). This subsumes the mechanical
parts of problems 1-2; do it as one pass so the generated files are only
touched once (collapse multi-pass refactorings).

Affected: `selfblog/assembly.py` (generate_workflow_yaml, ~lines 27-190),
`selfblog/cli.py` (generate-shared `_worker.js` emission, assembly init),
`selfdoc_core/config.py` (schema, ~lines 680-705), the live
`smm-h/selfdoc-cache` workflow file (regenerate + push after the code change).

## Problem 4: README command table lost auto-sync (regression accepted 2026-07-17)

`docs/_README.md` previously used `:-: table-commands schema-dir="."` to render
the CLI command table from the live strictcli schema. Because the `post`/
`assembly` stubs (`_moved_to_selfblog`) are still REGISTERED in `selfdoc/cli.py`,
the schema still contains them, and the generated table advertised dead
commands. Fix applied in commit 42b2ddf: the directive was replaced with a
static hand-written table. That trades one staleness bug for a future one --
the table will silently rot when the command surface changes.

Two follow-ups:

- **(a) Add an exclusion attribute to `table-commands`** (e.g.
  `exclude="post,assembly"`) in `selfdoc_core/directives.py`, then restore the
  directive in `docs/_README.md` with the exclusion.
  - Pros: restores auto-sync now; generally useful directive feature.
  - Cons: small feature work + tests.
- **(b) Delete the `post`/`assembly` stubs entirely** once the migration grace
  period is over, then restore the bare directive.
  - Pros: no feature work; stubs are transitional by design and the
    no-backward-compat-shims rule says dead API surfaces get deleted.
  - Cons: users of old selfdoc versions lose the redirect error message; needs
    a user decision on when the grace period ends.

Recommendation: (b) is the end state; (a) is worth doing anyway if stubs must
live for a while. Ask the user when the stubs can die.

## Problem 5: dual-keyed assembly repo config

`selfblog/cli.py` (~lines 302-306) reads `assembly.repo` and falls back to
`topology.assembly`; `selfdoc.json` currently sets BOTH to
`smm-h/selfdoc-cache`. Two keys meaning the same thing is redundant state that
can drift, and the silent fallback is the kind of tolerant dual path the
no-silent-degradation rule exists to prevent.

Solution: pick ONE canonical key (likely `assembly.repo`, since `assembly.*`
now groups assembly settings), hard-error if the other is present (schema-level
rejection in `selfdoc_core/config.py`), update `selfdoc.json` and docs. This is
pre-1.0 (selfblog 0.1.1) -- no compatibility shim, just delete the fallback.

## Problem 6: standalone-site deploy model is legacy but still active

Each project deploys BOTH a standalone Pages site (`selfdoc deploy` -> project
`selfdoc` -> selfdoc.smmh.dev) AND into the unified assembly
(docs.smmh.dev/<slug>/). `assembly redirects` exists specifically to 301 the
standalone site into the assembly, implying standalone is being folded in --
but the post-release hook still runs `selfdoc deploy` on every release, so
both keep being published.

Decision needed (user): is the standalone site (a) legacy to be retired --
generate the `_redirects` file, deploy it once to the standalone project, drop
`selfdoc deploy` from the post-release hook -- or (b) intentionally
kept (e.g. as a per-project canonical URL)? If (b), document the two-model
design in docs/ so it stops looking like an accident.

## Affected files (summary)

- `selfblog/cli.py` -- assembly init project create, dual-key config read,
  `_worker.js` emission
- `selfblog/assembly.py` -- generated workflow yaml (hardcoded `smmh`)
- `selfdoc_core/config.py` -- topology/assembly schema
- `selfdoc_core/directives.py` -- table-commands exclusion (problem 4a)
- `selfdoc/cli.py` -- `_moved_to_selfblog` stubs (problem 4b)
- `docs/_README.md` -- static command table to be re-directived
- `selfdoc.json` -- posts_base semantics, dual keys, new pages_project key
- `smm-h/selfdoc-cache` (remote) -- regenerated workflow + `_worker.js`

## Effort estimate

- Problems 1+2+3 as one config-templating pass: ~half a day including tests
  and regenerating the assembly repo artifacts. Requires two user decisions
  first (canonical blog URL, Pages project key name).
- Problem 4: (a) small directive feature ~1-2 h; (b) trivial deletion once
  authorized.
- Problem 5: ~1 h including schema rejection test.
- Problem 6: no code until the user decides; then either ~1 h (retire) or
  docs-only (keep).
