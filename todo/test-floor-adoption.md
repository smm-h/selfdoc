# Test-floor adoption (stricttest plugin)

Successor carrying section 2 of `todo/.done/deploy-explicit-root-and-test-floor.md`
(section 1 — the deploy_github_pages explicit-target requirement — shipped). Provenance:
the adoption ruling was `[%%]` (adopted from a recommendation, freely reversible).

## Current state

No isolation floor: the shared `tests/conftest.py` sets only git identity; HOME is real,
so ambient stored `gh` auth is live for the entire suite, and safety rests on each test
remembering to mock `subprocess.run` around the real-write surfaces
(repository_dispatch, Git Trees API commits, `gh repo create`/`gh secret set`, wrangler).
One forgotten mock = a real authenticated write.

## Work (when the stricttest plugin is published)

Adopt the plugin as a dev dependency + required config: throwaway HOME (kills ambient gh
auth), network-off with a loopback allowance (the demo-panel server + chromium tests need
loopback only), TMPDIR refusal, push guard. Keep the existing factory fixtures; the local
`_GIT_ENV` identity injection becomes redundant once the floor's throwaway git config
covers it (optional cleanup). Note, not a defect: `test_git.py` intentionally exercises
the real installed commit-tool chain in tmp repos (no push exists in that chain) — keep,
but the sandbox must bind those binaries.

## Effort

Small once the plugin is published: dev dep + required config keys + one adoption pass
over fixtures.
