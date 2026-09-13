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
	"github.com/smm-h/strictcli/go/strictcli"
)

func main() {
	// The application's type is named rather than inferred, so this file says
	// on its face that the process is handed to strictcli. The suites compile
	// two more main packages -- the fake external tools they put on PATH --
	// and a strictcli import is what tells a reader, and the release flow's
	// schema dump, which of the three is the CLI.
	var app *strictcli.App = cli.New(cli.Options{Version: Version})
	app.Run()
}
