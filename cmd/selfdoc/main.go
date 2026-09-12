// Command selfdoc is the single binary for the selfdoc documentation
// generator: it builds documentation sites from Markdown templates and source
// code, and publishes them.
//
// The command tree, and the language extractors every code directive is
// resolved through, are registered by internal/cli.
package main

import (
	"github.com/smm-h/selfdoc/internal/cli"
)

func main() {
	cli.New(cli.Options{}).Run()
}
