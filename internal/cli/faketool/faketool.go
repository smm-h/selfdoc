// Package faketool is the fake external tool the cli suite puts at the front
// of PATH under whatever names a test asks for -- "gh", "npx", and so on.
//
// It lives in its own package, outside the test binary, so the suite can build
// it ONCE into a plain uninstrumented executable. A fake implemented by
// re-running the suite's own race-instrumented binary paid the race runtime's
// start-up cost on every single call a command made.
//
// The protocol is files in a state directory the test writes and the fake
// appends to: "replies.json" holds the scripted answers, matched against each
// call's joined argv, and "calls.jsonl" is the log a test reads its assertions
// from.
package faketool

import (
	"encoding/json"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"
)

// StateEnv names the directory the fakes keep their state in. The test sets it
// in its own environment, and each fake inherits it through the subprocess the
// code under test starts.
const StateEnv = "SELFDOC_CLI_FAKE_TOOL_STATE"

// Reply is one scripted answer. Match is a substring of the joined argv; an
// empty Match answers anything.
type Reply struct {
	Match  string `json:"match"`
	Code   int    `json:"code"`
	Stdout string `json:"stdout"`
	Stderr string `json:"stderr"`
}

// Call is one recorded invocation of a fake tool.
type Call struct {
	Tool  string   `json:"tool"`
	Argv  []string `json:"argv"`
	Input string   `json:"input"`
}

// Joined renders the argv the way an assertion reads it.
func (c Call) Joined() string { return c.Tool + " " + strings.Join(c.Argv, " ") }

// Run is the fake executable's whole body: record the call, then answer from
// the scripted replies.
func Run(dir, program string, argv []string) int {
	input := ""
	for _, arg := range argv {
		if arg == "-" {
			data, _ := io.ReadAll(os.Stdin)
			input = string(data)
			break
		}
	}
	tool := filepath.Base(program)
	record := Call{Tool: tool, Argv: argv, Input: input}
	if data, err := json.Marshal(record); err == nil {
		if file, err := os.OpenFile(filepath.Join(dir, "calls.jsonl"),
			os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0o644); err == nil {
			_, _ = file.Write(append(data, '\n'))
			_ = file.Close()
		}
	}

	var replies []Reply
	if data, err := os.ReadFile(filepath.Join(dir, "replies.json")); err == nil {
		_ = json.Unmarshal(data, &replies)
	}
	joined := record.Joined()
	for _, reply := range replies {
		if reply.Match == "" || strings.Contains(joined, reply.Match) {
			fmt.Fprint(os.Stdout, reply.Stdout)
			fmt.Fprint(os.Stderr, reply.Stderr)
			return reply.Code
		}
	}
	return 0
}
