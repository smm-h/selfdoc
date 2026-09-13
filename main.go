// Command selfdoc is the single binary for the selfdoc documentation
// generator: it builds documentation sites from Markdown templates and source
// code, and publishes them.
//
// The entry point is the module root, so the binary installs with
// "go install github.com/smm-h/selfdoc@v0" and takes its name from the
// module's last path element. Every engine package lives under internal/, and
// the command tree -- with the language extractors every code directive is
// resolved through -- is registered by internal/cli.
package main

import (
	"github.com/smm-h/selfdoc/internal/cli"
)

func main() {
	cli.New(cli.Options{Version: Version}).Run()
}
