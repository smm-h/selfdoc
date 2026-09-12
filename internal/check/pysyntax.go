package check

import (
	"encoding/json"
	"fmt"
	"strings"
	"time"

	"github.com/smm-h/selfdoc/internal/effects"
)

// pythonSyntaxDriver is the program that answers whether a fenced Python block
// parses.
//
// The answer has to be Python's own: EXAMPLE001 reports the interpreter's
// message verbatim, and no Go parser produces those strings. The driver reads
// the snippet on standard input and prints one JSON object -- the same shape
// the Python extractor's driver uses, for the same reason.
//
// An IndentationError is reported as its own status rather than as a syntax
// error, because a documentation snippet is routinely a fragment lifted out of
// a function and its indentation is not a defect. TabError is a subclass of
// it and is caught by the same clause, which is what the except-order
// guarantees.
const pythonSyntaxDriver = `
import ast, json, sys

source = sys.stdin.read()
try:
    ast.parse(source)
except IndentationError:
    sys.stdout.write(json.dumps({"status": "indentation"}))
except SyntaxError as exc:
    sys.stdout.write(json.dumps({
        "status": "syntax",
        "msg": exc.msg,
        "lineno": exc.lineno if exc.lineno is not None else 0,
    }))
else:
    sys.stdout.write(json.dumps({"status": "ok"}))
`

// pythonSyntaxTimeout bounds the driver run. Parsing a documentation snippet
// is instant; the deadline is there so a broken interpreter cannot hang a
// check.
const pythonSyntaxTimeout = 30 * time.Second

// pythonSyntaxVerdict is what the driver answered.
type pythonSyntaxVerdict struct {
	// Status is "ok", "indentation" or "syntax".
	Status string `json:"status"`
	// Message is the interpreter's own SyntaxError message, set only for
	// the "syntax" status.
	Message string `json:"msg"`
	// Line is the 1-based line within the snippet the error sits on, 0
	// when the interpreter reported none.
	Line int `json:"lineno"`
}

// checkPythonSyntax parses source through python3's own ast module.
//
// A missing or broken interpreter is an error rather than a pass: EXAMPLE001
// would otherwise silently stop reporting, and a rule that reports nothing is
// indistinguishable from a rule that found nothing.
func checkPythonSyntax(source string, handle *effects.Handle) (pythonSyntaxVerdict, error) {
	result, err := handle.Run(
		[]string{"python3", "-c", pythonSyntaxDriver},
		effects.Read(),
		effects.CaptureOutput(),
		effects.Stdin([]byte(source)),
		effects.Timeout(pythonSyntaxTimeout),
	)
	if err != nil {
		return pythonSyntaxVerdict{}, fmt.Errorf(
			"checking a Python example needs python3: %w", err,
		)
	}
	if result.ExitCode != 0 {
		return pythonSyntaxVerdict{}, fmt.Errorf(
			"python3 refused to parse a Python example (exit %d): %s",
			result.ExitCode, strings.TrimSpace(string(result.Stderr)),
		)
	}
	var verdict pythonSyntaxVerdict
	if err := json.Unmarshal(result.Stdout, &verdict); err != nil {
		return pythonSyntaxVerdict{}, fmt.Errorf(
			"python3 answered a Python example with something other than the "+
				"expected report: %w", err,
		)
	}
	return verdict, nil
}
