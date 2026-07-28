# deploy_github_pages explicit target (now) + test-floor adoption (later)

Provenance: `[%%]`-marked decisions were adopted from recommendations; unmarked were
deliberate user rulings.

## 1 — Kill the force-push landmine (now)

`selfdoc_core/deploy.py` (`deploy_github_pages`, ~:106-150) reads the `origin` remote from the
**process cwd** (no `cwd=` argument) and then runs `git push --force <remote> gh-pages`. Zero
tests call it today, so it is a dormant trap: one future unmocked call from a repo root
force-pushes that repo's real gh-pages. Fix: a required explicit repo-root/target parameter
threaded through (the established cwd-required pattern); calling without an explicit target is
a hard error. Red-green.

## 2 — Test-floor adoption `[%%]` (when the fleet floor package is published)

Current state: no isolation floor — the shared `tests/conftest.py` sets only git identity;
HOME is real, so the ambient `gh` stored auth is live for the entire suite, and safety rests
solely on each test remembering to mock `subprocess.run` around the real-write surfaces
(repository_dispatch, Git Trees API commits, `gh repo create`/`gh secret set`, wrangler). One
forgotten mock = a real authenticated write.

Adopt the floor package as a dev dependency + required config: throwaway HOME (kills ambient
gh auth), network-off with loopback allowance (the demo-panel server + chromium tests need
loopback only), TMPDIR refusal, push guard. Keep the existing factory fixtures; the local
`_GIT_ENV` identity injection becomes redundant once the floor's throwaway git config covers
it (optional cleanup). Note, not a defect: `test_git.py` intentionally exercises the real
installed commit-tool chain in tmp repos (no push exists in that chain) — keep, but the
sandbox must bind those binaries.
