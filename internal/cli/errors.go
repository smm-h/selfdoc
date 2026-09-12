package cli

import (
	"errors"
	"strconv"
)

// asError is errors.As under a name that reads as a question at the call site.
func asError(err error, target any) bool { return errors.As(err, target) }

// itoa is strconv.Itoa under a shorter name, for the message fragments that
// splice a count into the middle of a sentence.
func itoa(n int) string { return strconv.Itoa(n) }
