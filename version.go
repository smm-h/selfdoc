// Package selfdoc holds the module-level build metadata for the selfdoc
// binary. The version string is embedded from the repository's VERSION file,
// which is also the file rlsbl's release flow writes.
//
// Only build metadata belongs here: every engine package lives under
// internal/, and the command-line entry point under cmd/selfdoc.
package selfdoc

import (
	_ "embed"
	"strings"
)

//go:embed VERSION
var versionFile string

// Version is the project's release version, read from the repository's
// VERSION file at build time with surrounding whitespace removed.
var Version = strings.TrimSpace(versionFile)
