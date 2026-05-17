---
title: Deployment
description: "Deploy your selfdoc site to Cloudflare Pages or GitHub Pages. Covers configuration, credentials, security headers, and CI integration."
order: 50
---

# Deployment

selfdoc generates a fully static site that can be deployed anywhere. Two providers have built-in support with `selfdoc deploy`: **Cloudflare Pages** and **GitHub Pages**.

## Configuration

Add a `deploy` section to your `selfdoc.json`:

```json
{
  "language": "python",
  "source": ["mypackage/"],
  "base_url": "https://myproject.pages.dev",
  "deploy": {
    "provider": "cloudflare-pages",
    "project": "myproject"
  }
}
```

| Field | Required | Description |
| ----- | -------- | ----------- |
| `deploy.provider` | yes | Either `cloudflare-pages` or `github-pages` |
| `deploy.project` | Cloudflare only | The Cloudflare Pages project name |

The `provider` field determines which deployment strategy `selfdoc deploy` uses. The `project` field is only required for Cloudflare Pages (it identifies which Pages project to upload to).

## Cloudflare Pages

### Setup

1. Create a Cloudflare Pages project in the Cloudflare dashboard (or let the first deploy create it).
2. Install the Wrangler CLI:

```bash
npm install -g wrangler
```

3. Authenticate wrangler (interactive login or API token):

```bash
wrangler login
```

4. Configure `selfdoc.json`:

```json
{
  "deploy": {
    "provider": "cloudflare-pages",
    "project": "myproject"
  }
}
```

5. Build and deploy:

```bash
selfdoc build
selfdoc deploy
```

### Environment Variables

For non-interactive environments (CI, post-release hooks), provide credentials via environment variables instead of `wrangler login`:

| Variable | Description |
| -------- | ----------- |
| `CF_PAGES_API_TOKEN` | Cloudflare API token with Pages edit permission |
| `CF_ACCOUNT_ID` | Your Cloudflare account ID |

selfdoc bridges these to the `CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ACCOUNT_ID` names that wrangler expects internally, so you only need to set the `CF_*` variants.

### Security Headers

When the deploy provider is `cloudflare-pages`, the build automatically generates a `_headers` file in the output directory. This file instructs Cloudflare's edge to serve the following headers on every response:

- `Strict-Transport-Security: max-age=31536000; includeSubDomains; preload`
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `Referrer-Policy: strict-origin-when-cross-origin`
- `Permissions-Policy: camera=(), microphone=(), geolocation=()`
- `X-XSS-Protection: 0`

Static assets (`style.css`, SVG files) also get aggressive cache headers (`Cache-Control: public, max-age=31536000, immutable`).

No manual configuration is needed -- these are generated as part of `selfdoc build`.

## GitHub Pages

### Setup

1. Enable GitHub Pages in your repository settings, selecting "Deploy from a branch" with the `gh-pages` branch.
2. Configure `selfdoc.json`:

```json
{
  "deploy": {
    "provider": "github-pages",
    "project": "myproject"
  }
}
```

3. Build and deploy:

```bash
selfdoc build
selfdoc deploy
```

### How It Works

`selfdoc deploy` for GitHub Pages:

1. Reads the `origin` remote URL from your local git config.
2. Creates a fresh temporary directory with a new git repo.
3. Copies the entire build output into it.
4. Adds a `.nojekyll` file (prevents GitHub from running Jekyll processing).
5. Commits everything and force-pushes to the `gh-pages` branch on your remote.

This approach keeps the `gh-pages` branch clean (a single commit with the latest build), avoids touching your working tree, and works from any branch.

### Security Headers

GitHub Pages does not support custom HTTP headers via a config file. Instead, selfdoc injects `<meta http-equiv>` tags into every HTML page when the deploy target is `github-pages`:

- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `Content-Security-Policy` with a restrictive policy (self-hosted scripts and styles, limited external CDN allowlist)

HTTPS and HSTS are handled by the GitHub Pages platform itself -- no configuration is needed on your side.

## Directory-Index URLs

selfdoc generates directory-index URLs for all pages. For example, a page at `docs/guide.md` becomes `guide/index.html` in the output, which is served as `/guide/` by the web server.

This approach:

- Works on all hosting platforms without custom redirect rules
- Produces clean URLs without file extensions
- Avoids trailing-slash redirect chains (no `_redirects` file needed)

No configuration is required. All internal navigation links already use the directory form.

## CI Integration

The recommended approach is to use an rlsbl post-release hook that builds and deploys docs automatically after each release.

### Post-release hook example

In `.rlsbl/hooks/post-release.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

echo "Post-release: v$RLSBL_VERSION"

if command -v selfdoc &>/dev/null && [ -f selfdoc.json ]; then
  # Source environment variables for deploy credentials
  [ -f ~/Projects/.env ] && set -a && source ~/Projects/.env && set +a
  echo "Building and deploying docs..."
  selfdoc build && selfdoc deploy
fi
```

The `RLSBL_VERSION` variable is set by rlsbl to the version being released. The hook sources credentials from `~/Projects/.env` (where `CF_PAGES_API_TOKEN` and `CF_ACCOUNT_ID` live for Cloudflare deploys).

### Manual CI

If you are not using rlsbl, run these two commands in your CI pipeline after your tests pass:

```bash
selfdoc build
selfdoc deploy
```

For Cloudflare Pages, ensure `CF_PAGES_API_TOKEN` and `CF_ACCOUNT_ID` are set as secrets in your CI environment. For GitHub Pages, ensure the CI runner has push access to the repository (a `GITHUB_TOKEN` with `contents: write` scope, or a deploy key).

## Custom Domain

Both platforms support custom domains, but configuration is done on the platform side -- selfdoc does not manage DNS or domain settings.

- **Cloudflare Pages**: Add a custom domain in the Cloudflare dashboard under your Pages project settings. See [Cloudflare Pages custom domains](https://developers.cloudflare.com/pages/configuration/custom-domains/).
- **GitHub Pages**: Add a custom domain in your repository's Settings > Pages section. See [GitHub Pages custom domains](https://docs.github.com/en/pages/configuring-a-custom-domain-for-your-github-pages-site).

In both cases, set your `base_url` in `selfdoc.json` to match the custom domain so that canonical URLs, sitemaps, and OG tags resolve correctly:

```json
{
  "base_url": "https://docs.myproject.com"
}
```
