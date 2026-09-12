#!/usr/bin/env python3
"""Print the Go extractor's output for the fixtures the Go port pins.

The Go port of ``selfdoc_core.extractors.go`` asserts against exact strings.
Rather than hand-transcribing them, this prints what the Python implementation
actually produces for each fixture, so a test expectation is always a recorded
observation.

Run from the repository root:

    UV_NO_SYNC=1 uv run python scripts/probe_go_extractor.py
"""

import json
import os
import sys
import tempfile

from selfdoc_core.extractors.go import GoExtractor

COMMIT_GO = """\
// Package commit implements the two-phase commit pipeline.
// Phase A is parallel-safe, Phase B is serialized.
package commit

import "context"

// Exit codes for commit-specific errors.
const (
\tExitCASExhausted  = 7
\tExitWriteTree     = 9
)

// DefaultTimeout is the default lock timeout in seconds.
const DefaultTimeout = 30

// CommitError carries a structured exit code alongside the error message.
type CommitError struct {
\tCode    int
\tMessage string
}

// Error implements the error interface.
func (e *CommitError) Error() string { return e.Message }

// Pipeline orchestrates the full commit flow.
type Pipeline struct {
\tSafegitDir string
\tConfig     Config
}

// Execute runs the full two-phase commit pipeline.
// On CAS miss it retries up to MaxAttempts times.
func (p *Pipeline) Execute(ctx context.Context, req Request) (*Result, error) {
\treturn nil, nil
}

// unexportedHelper is private and should be skipped.
func unexportedHelper() {}

// NewPipeline creates a new Pipeline with defaults.
func NewPipeline(dir string) *Pipeline {
\treturn &Pipeline{SafegitDir: dir}
}
"""

TYPES_GO = """\
package commit

// Request holds all inputs for a single commit operation.
type Request struct {
\tMessage string
\tFiles   []string
}

// Result is the JSON-serializable output of a successful commit.
type Result struct {
\tSHA      string `json:"sha"`
\tRef      string `json:"ref"`
\tParent   string `json:"parent"`
\tAttempts int    `json:"attempts"`
}
"""

COMMIT_TEST_GO = """\
package commit

import "testing"

// TestNewPipeline verifies default construction.
func TestNewPipeline(t *testing.T) {
\tp := NewPipeline("/tmp/test")
\tif p.SafegitDir != "/tmp/test" {
\t\tt.Errorf("got %q, want /tmp/test", p.SafegitDir)
\t}
}

func TestExecute(t *testing.T) {
\t// placeholder
}
"""

MAIN_GO = """\
package main

import (
\t"flag"
\t"fmt"
)

func usageText() string {
\treturn `Usage: myapp <command> [options]

Commands:
  run     Run the processor
  check   Check configuration

Global flags:
  --verbose   Verbose output
  --quiet     Suppress output
`
}

var verbose bool
var outputFile string

func main() {
\tflag.BoolVar(&verbose, "verbose", false, "Enable verbose output")
\tflag.StringVar(&outputFile, "output", "out.txt", "Output file path")
\tflag.Parse()
\tfmt.Println("hello")
}
"""

COMMANDS_GO = """\
package main

func registerCommands(app *App) {
\tapp.Command("run", "Run the processor")
\tapp.Command("check", "Check configuration")
}
"""

MODELS_GO = """\
package models

// Config holds application configuration.
type Config struct {
\tHost    string `json:"host" yaml:"host"` // Server hostname
\tPort    int    `json:"port"`             // Listen port
\tDebug   bool   `json:"debug"`
\tinternal string // unexported, should appear but lowercase
}

// Entry represents a log entry.
type Entry struct {
\tLevel   string `json:"level"`
\tMessage string `json:"message"` // Log message text
}
"""

SERVER_GO = """\
package server

// Merge combines two values with a separator.
// The a and b values are concatenated using sep.
func Merge(a, b int, sep string) string {
    return ""
}

// Handle processes an HTTP request.
// Returns the response status code.
func (s *Server) Handle(req *http.Request) (int, error) {
    return 200, nil
}

// Printf formats and prints.
func Printf(format string, args ...interface{}) {
}

// NoDoc has no documentation.
func NoDoc(x int) {
}
"""

DOC_GO = "// Package mypkg provides utilities.\npackage mypkg\n"
MYPKG_MAIN_GO = 'package mypkg\n\nfunc Hello() string { return "hello" }\n'

SYMBOLS_GO = """\
package main

func Hello() {}
func hello() {}
type Config struct {}
type config struct {}
var MaxRetries int
const DefaultTimeout = 30
"""

CONSTS_GO = """\
package exitcodes

const (
\tExitSuccess = 0
\tExitGeneral = 1
)
"""

IOTA_GO = """\
package main

const (
\t_ = iota
\tExitSuccess
\tExitGeneral
\t_reserved
)
"""

MULTI_GO = """\
package main

type Server struct{}
func (s *Server) Run() {}

type Client struct{}
func (c *Client) Run() {}
"""


def main():
    base = tempfile.mkdtemp()
    files = {
        "internal/commit/commit.go": COMMIT_GO,
        "internal/commit/types.go": TYPES_GO,
        "internal/commit/commit_test.go": COMMIT_TEST_GO,
        "cmd/myapp/main.go": MAIN_GO,
        "cmd/myapp/commands.go": COMMANDS_GO,
        "internal/models/models.go": MODELS_GO,
        "pkg/server.go": SERVER_GO,
        "mypkg/doc.go": DOC_GO,
        "mypkg/main.go": MYPKG_MAIN_GO,
        "symbols.go": SYMBOLS_GO,
        "consts.go": CONSTS_GO,
        "iota.go": IOTA_GO,
        "multi.go": MULTI_GO,
        "config.json": json.dumps({"host": "localhost", "port": 3000, "debug": False}),
    }
    for name, content in files.items():
        full = os.path.join(base, name)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8") as handle:
            handle.write(content)

    extractor = GoExtractor()

    probes = [
        ("ref internal/commit", "ref", {"path": "internal/commit"}),
        ("ref target NewPipeline", "ref", {"path": "internal/commit", "target": "NewPipeline"}),
        ("ref target Pipeline.Execute", "ref", {"path": "internal/commit", "target": "Pipeline.Execute"}),
        ("prose-desc internal/commit", "prose-desc", {"path": "internal/commit"}),
        ("table-schema models Config", "table-schema", {"path": "internal/models/models.go", "target": "Config"}),
        ("table-schema models all", "table-schema", {"path": "internal/models/models.go"}),
        ("table-schema types Result", "table-schema", {"path": "internal/commit/types.go", "target": "Result"}),
        ("code-test whole", "code-test", {"path": "internal/commit/commit_test.go"}),
        ("code-test target", "code-test", {"path": "internal/commit/commit_test.go", "target": "TestNewPipeline"}),
        ("code-help main.go", "code-help", {"path": "cmd/myapp/main.go"}),
        ("code-help commands.go", "code-help", {"path": "cmd/myapp/commands.go"}),
        ("table-config config.json", "table-config", {"path": "config.json"}),
        ("table-schema config.json with target", "table-schema", {"path": "config.json", "target": "SomeType"}),
        ("table-schema config.json exclude", "table-schema", {"path": "config.json", "exclude": "debug"}),
    ]

    for label, directive, attrs in probes:
        print("=== " + label)
        print(repr(extractor.extract(directive, attrs, [], [], base)))

    print("=== public_symbols symbols.go")
    print(repr(extractor.public_symbols(os.path.join(base, "symbols.go"))))
    print("=== public_symbols consts.go")
    print(repr(extractor.public_symbols(os.path.join(base, "consts.go"))))
    print("=== public_symbols iota.go")
    print(repr(extractor.public_symbols(os.path.join(base, "iota.go"))))
    print("=== public_symbols multi.go")
    print(repr(extractor.public_symbols(os.path.join(base, "multi.go"))))
    print("=== public_symbols commit.go")
    print(repr(extractor.public_symbols(os.path.join(base, "internal/commit/commit.go"))))
    print("=== module_docstring mypkg")
    print(repr(extractor.module_docstring(os.path.join(base, "mypkg"))))
    print("=== module_docstring commit dir")
    print(repr(extractor.module_docstring(os.path.join(base, "internal/commit"))))

    pkg = os.path.join(base, "pkg")
    for symbol in ["Merge", "Handle", "Printf", "NoDoc", "DoesNotExist", "Server.Handle", "WrongType.Handle"]:
        print("=== symbol_details " + symbol)
        print(repr(extractor.symbol_details(pkg, symbol)))

    print("base=" + base, file=sys.stderr)


main()
