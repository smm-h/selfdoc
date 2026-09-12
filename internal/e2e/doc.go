// Package e2e is the rendered-reality suite: the built site, in a real
// browser, asserted as painted.
//
// Everything in it sits behind the "e2e" build tag, so "go test ./..." skips
// it and "go test -tags e2e ./internal/e2e/" runs it. This file carries no tag
// so the directory always holds one buildable file.
//
// # One-time setup
//
// The suite drives Chromium through playwright-go, which needs its Node driver
// and a matching Chromium build in the user cache. Install both once with the
// binding's own installer, at the playwright-go version go.mod pins:
//
//	go run github.com/playwright-community/playwright-go/cmd/playwright@<version> install chromium
//
// A skip that fires because the browser is missing prints that command with
// the version filled in.
//
// When the Playwright CDN refuses the download -- it has answered 400 for
// every driver and browser build from this machine's network -- the same two
// pieces can be assembled by hand. The driver is the playwright-core npm
// package of the version the binding names (playwright-go's playwrightCliVersion)
// plus a node binary:
//
//	D=~/.cache/ms-playwright-go/<driver-version>
//	npm pack playwright-core@<driver-version> && tar xzf playwright-core-<driver-version>.tgz
//	mkdir -p "$D" && mv package "$D/package" && ln -s "$(command -v node)" "$D/node"
//	"$D/node" "$D/package/cli.js" --version   # must print the driver version
//
// The browser is a Chromium build under ~/.cache/ms-playwright/chromium-<revision>/,
// where <revision> is what that playwright-core's browsers.json names.
//
// The suite also needs Pagefind (the search index every fixture tree carries)
// and python3 (the Python extractor the versioned fixture project is built
// through). Each missing dependency skips the tests that need it, naming what
// to install.
//
// # What it asserts
//
// The pipeline is never mocked. Every page asserted against was produced by
// the production build, the production graft, the production shared-file
// generation and a real Pagefind index, grafted into a real assembly tree and
// served by the production preview server. A suite that rendered through a
// second implementation would be a picture of something that is not going to
// be published, which is worse than no picture at all.
//
// Two trees are built and served per theme, because a project has two
// published shapes: the assembled site, where every project mounts under its
// slug and only its current version is published, and the standalone site a
// project deploys on its own, which is where the archive under v/<version>/
// is.
package e2e
