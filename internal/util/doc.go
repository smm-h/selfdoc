// Package util holds the small shared helpers the rest of selfdoc builds on:
// frontmatter parsing, project manifest and version detection, HTML escaping,
// path joining, date formatting, title casing, and the Python-compatible
// string, number and JSON spellings the emitted documents are pinned to.
//
// Nothing here knows about a build, a page or a directive. A helper earns its
// place here by being needed in more than one package and by having no
// dependency on any other package of this module.
package util
