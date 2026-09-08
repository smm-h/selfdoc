# Migrate the assembly site off Cloudflare Pages to Workers static assets

## Context

The unified docs assembly site is deployed to Cloudflare Pages. Two code paths
do it:

- The GitHub Actions workflow that `selfblog assembly` generates ends with a
  "Deploy to Cloudflare Pages" step running `npx wrangler pages deploy site/
  --project-name <project>`, authenticated with the `CF_ACCOUNT_ID` and
  `CF_PAGES_API_TOKEN` repository secrets (`selfblog/assembly.py`, the
  workflow template string).
- `selfdoc_core/deploy.py` wraps the same `wrangler pages deploy` command for
  local deploys and bridges the `CF_*` environment variables to the
  `CLOUDFLARE_*` names wrangler expects.

The retired per-project docs subdomains 301 into the assembly site through a
`_redirects` file in the built output.

## Problem

Cloudflare has put Pages into maintenance. The Pages documentation now carries
the notice "Workers supports most Pages use cases and offers a broader feature
set. It is Cloudflare's primary platform for building applications. Start new
projects with Workers." Static asset hosting on Workers is generally available,
framework and Vite support ship for Workers only, an official Pages-to-Workers
migration guide exists, and the older Workers Sites feature is already
deprecated in wrangler. No end-of-life date for Pages has been announced, but
new capability no longer reaches it, and a deploy path built on
`wrangler pages deploy` is a deploy path Cloudflare has stopped investing in.

## Solutions

### A. Migrate to Workers static assets (recommended)

Replace the Pages project with a Worker whose configuration points
`assets.directory` at the built `site/` output, with no Worker script for a
purely static site. The generated workflow step becomes `npx wrangler deploy`
with a committed `wrangler.toml` or `wrangler.jsonc` in the assembly
repository, and `selfdoc_core/deploy.py` runs the same command. The
`_redirects` and `_headers` files are honored unchanged by Workers static
assets. The API token needs Workers Scripts edit scope instead of Pages edit
scope, so the secret is rotated to a token with the new scope and its name
should stop saying Pages. The custom domain moves from the Pages project to a
Workers custom domain or route on the same zone.

Pros: the platform Cloudflare is investing in; identical output directory,
redirects and headers; one-step deploy stays one step; the Pages project can be
deleted afterwards.

Cons: a one-time cutover of the custom domain with a short window where the
old Pages project and the new Worker both exist; every consumer's post-release
dispatch keeps working only if the assembly repository's workflow is
regenerated, so the change ships as a selfblog release plus one regeneration.
One community measurement found Workers static assets a few milliseconds
slower than Pages under parallel fetches, which does not affect a docs site.

### B. Stay on Pages until Cloudflare announces an end date

Pros: no work now.

Cons: the cutover then happens on Cloudflare's schedule rather than ours, and
any Pages-only breakage between now and then has no fix path.

### C. Move the assembly site to a different static host

Pros: removes the Cloudflare dependency entirely.

Cons: the retired-subdomain redirects, the custom domain, and the account
secrets all live at Cloudflare; a different host means rebuilding the redirect
layer and the DNS wiring, for a site whose only requirement is serving static
files.

## Affected files

- `selfblog/assembly.py`: the generated workflow's deploy step and the secret
  names it references.
- `selfdoc_core/deploy.py`: `deploy_cloudflare_pages` and the environment
  bridging; rename to reflect Workers.
- `docs/deployment.md` and `docs/rlsbl-integration.md`: describe the Pages
  deploy path.
- The assembly repository's committed workflow and a new wrangler
  configuration file, regenerated after the selfblog release.
- The repository secret holding the Cloudflare token: new scope, new name.

## Effort

Small in code, one template string and one function. The cutover itself is an
operator step: create the Worker, attach the domain, rotate the token, delete
the Pages project.
