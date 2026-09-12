package assembly

import "fmt"

// Error is the failure most operations here report: a refused pin, an
// incomplete membership record, a step that exited non-zero, a tree that
// failed verification, and every other hard error the Python surface raised as
// a RuntimeError or a ValueError.
//
// It is the one error type a caller needs to recognize with errors.As to
// render an assembly refusal distinctly from an unexpected internal failure.
// The one failure kept separate is [RemoteReadError], because a read that did
// not succeed and did not 404 must never be mistaken for an absent file.
type Error struct {
	// Message is the diagnostic, rendered verbatim by Error.
	Message string
}

// Error returns the diagnostic.
func (e *Error) Error() string { return e.Message }

// errorf builds an [Error] from a format string.
func errorf(format string, args ...any) error {
	return &Error{Message: fmt.Sprintf(format, args...)}
}
