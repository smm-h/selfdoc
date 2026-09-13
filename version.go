package main

import (
	_ "embed"
	"strings"
)

//go:embed VERSION
var versionFile string

// Version is the project's release version, read from the repository's
// VERSION file at build time with surrounding whitespace removed. It is what
// "selfdoc --version" prints, and what an unpinned toolchain pin resolves to.
//
// The binary is the only place the version is read from a file: every package
// that needs it is handed it, so nothing under internal/ depends on the
// repository's own layout.
var Version = strings.TrimSpace(versionFile)
