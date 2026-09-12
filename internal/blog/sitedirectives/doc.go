// Package sitedirectives carries the site-level directives: the generated
// parts of the home project's authored pages.
//
// The front page is authored -- prose, structure and design belong to whoever
// writes it -- but two of its parts are mechanical: the curated project cards
// with each project's live version, and the recent posts. Those arrive through
// directives so the authored page can never go stale.
//
// # Where resolution happens
//
// Two moments, and both are the same code:
//
//   - Build time, when the home project is built for the assembly. The build
//     needs the assembly's manifests to know any project's live version, so it
//     is run as "selfblog build --target home --site-manifests <dir>", which
//     is [BuildHomeProject]. Without that context the command refuses to build
//     at all, naming what is missing. A plain build of the home project refuses
//     too: the catalog has no "projects-cards", so it stops at an unknown
//     directive. Neither path ever emits an empty region.
//
//   - Assembly time, on every deploy, inside the shared-file generator. Each
//     resolved region is left in the emitted HTML inside a wrapper element,
//     so the assembly can re-render it from the manifests it holds without
//     going back to the source. This is what keeps the front page's version
//     badges current when another project deploys: the home project's own
//     build may be months old, the region is not.
//
// Both moments render a region's links against the rendering page's hop back
// to the site root, never against the site's base URL. A region on the front
// page and the same region on a page one level down need different hrefs, and
// an absolute one would need neither -- it would work on the deployed host and
// walk a reader off any preview or mirror. Directive resolution never learns
// which page it is writing into, so the build resolves regions first and then
// re-addresses them per page; [PageContext] is the one place that turns a page
// path into that hop.
//
// # The region wrapper
//
// The region wrapper is the whole mechanism. It is a custom element,
// "<selfblog-region data-directive=...>", and not an HTML comment: the build
// minifies its output and strips every comment, so a comment-delimited region
// would survive the markdown conversion and then vanish on the way to disk. A
// custom element survives both, carries its directive's attributes as data
// attributes so a re-render uses the same ones, and is nothing a browser has
// to be told about. A region that opens and never closes is a hard error,
// never a half-rendered page.
//
// # How a build reaches this package
//
// The Python shipped one shim script per directive and handed them to the
// build under the "directives" config key, with the live context passed
// through the same config document. One binary needs neither: both directives
// are compiled in, and [Directives] hands the build a
// [resolver.BuiltinDirective] per name, each bound to the [SiteContext] the
// command assembled. The context reaches the resolver inside those functions
// rather than as a value in the config map, which stays a document.
package sitedirectives
