// Package chrome is the assembly's one set of page-chrome assets.
//
// Every project's build emits its own "style.css" at its own output root, and
// a standalone deploy of that project needs it -- a project published on its
// own is a whole site and carries its own presentation. Inside the assembly
// that same file is one copy per subtree of the same stylesheet, which makes a
// presentation fix a republish of every project rather than a deploy.
//
// This package is the assembly's answer: the shared generator writes one
// site-level asset per theme actually in use, sourced from the theme files of
// the toolchain running the deploy, and re-points every emitted page at it.
// The pass runs on every deploy of any project, so a toolchain upgrade reaches
// the whole site on the next deploy instead of waiting for each project to
// publish again.
//
// What this does not touch is a project's own build: a constraint by design.
// "selfdoc build" keeps writing a self-contained "style.css" beside the pages
// that reference it, because a standalone deploy has no assembly to serve a
// site-level asset. The re-pointing is assembly-mount behaviour and belongs
// here, on the assembly side of the line.
//
// Names are content-hashed rather than version-stamped. A toolchain version
// changes on releases that do not touch the CSS, and the CSS changes during
// development without a version change; the hash is the only name that is as
// stable as the bytes it addresses, which is what a cache needs. Identical
// content also produces an identical name, so a deploy that changes nothing
// about the chrome writes nothing about it either.
//
// Themes are per project, so the asset set is theme-keyed: one asset per
// distinct theme the roster's manifests declare, and a page references the one
// its own project uses. A page that is the site's rather than any project's --
// the shared pages, the home project's pages at the root, the site-level blog
// -- references the home project's. A manifest naming no theme is every
// manifest published so far, and means [DefaultTheme], which is what
// "selfdoc build" itself uses when a project's config names none.
//
// # Migrating an already-published site
//
// Nothing has to be republished, and nothing breaks in between. The subtrees
// on a live site reference their own "style.css", which is still there -- the
// re-pointing rewrites the reference in the emitted HTML and leaves the file
// alone, because the file is in each project's published-file record and
// deleting it out from under that record is the prune's business, not this
// pass's. On the first deploy after this ships, of any project, the shared
// generator runs over the whole tree and every page in it moves to the
// site-level asset in one pass. Until that deploy the site is as it was.
package chrome
