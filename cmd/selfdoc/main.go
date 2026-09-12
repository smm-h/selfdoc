// Command selfdoc is the single binary for the selfdoc documentation
// generator: it builds documentation sites from Markdown templates and source
// code, and publishes them.
//
// The command tree is registered by internal/cli; until that package exists
// this entry point builds the bare application so the framework-owned surface
// (--help, --version, --dump-schema and the reserved quartet) is reachable.
package main

import (
	"github.com/smm-h/selfdoc"
	"github.com/smm-h/strictcli/go/strictcli"
)

// appHelp is the one-line description shown by selfdoc --help.
const appHelp = "Code-aware static site generator with directive-based content extraction"

func main() {
	app := strictcli.NewApp("selfdoc", selfdoc.Version, appHelp)
	app.Run()
}
