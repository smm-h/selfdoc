// Package site carries the assembly's model: what the unified documentation
// site declares, what each project published into it, and where a build's
// output lands once it is grafted in.
//
// The assembly is one Cloudflare Pages site serving many projects. Every
// project deploys its own documentation into a subtree of it, one declared
// project is served at the site root, and posts from every project share a
// single site-level blog. Three questions follow from that arrangement, and
// this package answers all three:
//
//   - Which projects does the site serve? The roster ([Roster], [ParseRoster])
//     is the declaration, hand-edited in the assembly repository; the deploy
//     reconciles the tree to it ([ReconcileMembership]) and can never add to
//     it.
//   - Which files does each project own? The published-file record
//     ([ParseFilesManifest], [PrunePlan]) names them per publisher, so a
//     release prunes only what it published before and does not publish now.
//   - Where does a built file go? [SplitBuildOutput] decides: a post to the
//     site-level blog, a home project's page to the site root, everything else
//     under the project's slug.
//
// Nothing here touches the network or the GitHub API. The operations that do
// -- the dispatch, the integrate, the Git Data API publishers, the
// verification fetches -- import this package rather than the reverse, which
// is what keeps the model readable and testable without a remote.
package site

import "fmt"

// DeployArtifactNames are the files a per-project selfdoc build emits for its
// own standalone hosting.
//
// They are meaningless (and actively harmful) once the build is grafted into
// the assembly tree, which serves one set of headers, redirects, worker and
// not-found page for the whole site.
//
// "404.html" belongs here for a reason of its own: the provider answers an
// unmatched address from the root of what it serves, so a copy buried in a
// project's subtree is never reached by anything. A mounted project stops
// emitting one; this filter is what keeps the ones already published from
// surviving into the tree, where they are unreachable pages that still have to
// satisfy every assertion made about a page.
var DeployArtifactNames = []string{"_headers", "_redirects", "_worker.js", "404.html"}

// DeployArtifactSuffixes are the pre-compressed copies a standalone build
// writes beside every asset.
var DeployArtifactSuffixes = []string{".gz", ".br"}

// PublishOwners is who may have written a path inside a project's site
// subtree. Every publisher records the set of paths it produced, and prunes
// only paths it produced before and does not produce now -- see [PrunePlan].
//
//	release  the full-scope integrate the deploy workflow runs from a tag
//	docs     the documentation publish, a documentation update with no release
//	posts    the post publish and the posts-scope integrate
//
// The point of separating them is that a full build no longer knows how to
// destroy content it never produced: an out-of-band post or documentation page
// belongs to another owner, so a release that does not carry it leaves it
// alone.
var PublishOwners = []string{"release", "docs", "posts"}

// FilesRecordVersion is the published-file record's format.
//
// Version 2 addresses every path from site/ rather than from the project's own
// subtree, because posts stopped living inside it: they are site-level, at
// blog/<post-slug>/, so one record now names paths in two different places and
// a single namespace is the only way they cannot be confused. A version-1
// record is refused, never reinterpreted -- see [ParseFilesManifest].
const FilesRecordVersion = 2

// ManifestSidecarSuffixes are the files under manifests/ that are not project
// manifests and must not be loaded as one.
var ManifestSidecarSuffixes = []string{"-revisions.json", "-files.json", "-listing.json"}

// ChromeDir is the site-level directory holding the shared chrome assets --
// the stylesheet and scripts every project's pages address.
//
// It is declared here rather than in the chrome package because
// [SiteReservedDirs] needs it and this package sits below chrome in the import
// graph.
const ChromeDir = "_chrome"

// SiteReservedDirs are the directories under site/ that belong to the assembly
// itself rather than to any project, so membership reconciliation never
// mistakes one for a slug.
var SiteReservedDirs = []string{"blog", "projects", "pagefind", ChromeDir}

// IntegrateScopes are the scopes a dispatch may carry. "" from a client
// payload that omits the key means a full project build; the workflow always
// passes the flag.
var IntegrateScopes = []string{"full", "posts", "shared-only"}

// WorkflowPath is the one path in the assembly repo that holds the generated
// deploy workflow.
const WorkflowPath = ".github/workflows/deploy.yml"

// RosterPath is the hand-edited file in the assembly repo that declares which
// projects the unified site serves.
const RosterPath = "roster.toml"

// ProjectsPath is the derived record of what each declared project last
// deployed.
const ProjectsPath = "projects.json"

// MembershipFields is every field an assembly integrate run records for a
// project in projects.json. A rebuild replays that record, so all three have
// to be there.
var MembershipFields = []string{"repo", "ref", "version"}

// Error is the failure every operation in this package reports: a refused
// declaration, an unreadable record, a collision with an address the assembly
// owns, and every other hard error the Python surface raised as a RuntimeError
// or a ValueError.
//
// It is the one error type a caller needs to recognize with errors.As to
// render an assembly refusal distinctly from an unexpected internal failure.
type Error struct {
	// Message is the diagnostic, rendered verbatim by Error.
	Message string
}

// Error returns the diagnostic.
func (e *Error) Error() string { return e.Message }

// errorf builds an [Error] from a format string.
func errorf(format string, args ...any) *Error {
	return &Error{Message: fmt.Sprintf(format, args...)}
}

// GenerateRedirectsFile returns the content of a Cloudflare Pages _redirects
// file that sends every path of the old per-project site to the assembly site
// under the project's slug prefix.
//
// slug is the project's URL path segment (for example "selfdoc"); docsBase is
// the base URL of the assembly site (for example "https://docs.smmh.dev").
func GenerateRedirectsFile(slug, docsBase string) string {
	docsBase = trimRightSlashes(docsBase)
	return fmt.Sprintf("/* %s/%s/:splat 301\n", docsBase, slug)
}

// trimRightSlashes reproduces Python's str.rstrip("/").
func trimRightSlashes(s string) string {
	end := len(s)
	for end > 0 && s[end-1] == '/' {
		end--
	}
	return s[:end]
}
