"""Tests for the Go source extractor (selfdoc.extractors.go)."""

import json
import os

import pytest

from selfdoc.extractors.go import resolve_go


@pytest.fixture()
def go_project(tmp_path):
    """Create a sample Go project structure for testing."""
    # Create a package directory: internal/commit
    pkg_dir = os.path.join(tmp_path, "internal", "commit")
    os.makedirs(pkg_dir)

    # Main source file with package doc, types, funcs, consts
    commit_go = os.path.join(pkg_dir, "commit.go")
    with open(commit_go, "w", encoding="utf-8") as f:
        f.write("""\
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
""")

    # A second file in the same package (to test multi-file handling)
    types_go = os.path.join(pkg_dir, "types.go")
    with open(types_go, "w", encoding="utf-8") as f:
        f.write("""\
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
""")

    # Test file
    commit_test_go = os.path.join(pkg_dir, "commit_test.go")
    with open(commit_test_go, "w", encoding="utf-8") as f:
        f.write("""\
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
""")

    # CLI entry point file
    cmd_dir = os.path.join(tmp_path, "cmd", "myapp")
    os.makedirs(cmd_dir)

    main_go = os.path.join(cmd_dir, "main.go")
    with open(main_go, "w", encoding="utf-8") as f:
        f.write("""\
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
""")

    # Struct with tags for schema testing
    models_dir = os.path.join(tmp_path, "internal", "models")
    os.makedirs(models_dir)

    models_go = os.path.join(models_dir, "models.go")
    with open(models_go, "w", encoding="utf-8") as f:
        f.write("""\
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
""")

    # JSON config file
    config_json = os.path.join(tmp_path, "config.json")
    with open(config_json, "w", encoding="utf-8") as f:
        json.dump({"host": "localhost", "port": 3000, "debug": False}, f)

    return tmp_path


@pytest.fixture()
def source_paths():
    return []


# ---------------------------------------------------------------------------
# :::module tests
# ---------------------------------------------------------------------------


class TestModuleDirective:
    def test_extracts_package_doc(self, go_project, source_paths):
        result = resolve_go(
            "module", "internal/commit", [], source_paths, str(go_project)
        )
        assert "## internal/commit" in result
        assert "Package commit implements the two-phase commit pipeline." in result
        assert "Phase A is parallel-safe" in result

    def test_extracts_exported_func(self, go_project, source_paths):
        result = resolve_go(
            "module", "internal/commit", [], source_paths, str(go_project)
        )
        assert "### NewPipeline" in result
        assert "func NewPipeline(dir string) *Pipeline" in result
        assert "creates a new Pipeline with defaults" in result

    def test_extracts_exported_type(self, go_project, source_paths):
        result = resolve_go(
            "module", "internal/commit", [], source_paths, str(go_project)
        )
        assert "### CommitError" in result
        assert "type CommitError struct" in result
        assert "carries a structured exit code" in result

    def test_extracts_exported_const(self, go_project, source_paths):
        result = resolve_go(
            "module", "internal/commit", [], source_paths, str(go_project)
        )
        assert "### ExitCASExhausted" in result
        assert "Exit codes for commit-specific errors." in result

    def test_extracts_single_const(self, go_project, source_paths):
        result = resolve_go(
            "module", "internal/commit", [], source_paths, str(go_project)
        )
        assert "### DefaultTimeout" in result
        assert "const DefaultTimeout = 30" in result

    def test_extracts_method(self, go_project, source_paths):
        result = resolve_go(
            "module", "internal/commit", [], source_paths, str(go_project)
        )
        assert "### Pipeline.Execute" in result
        assert "runs the full two-phase commit pipeline" in result

    def test_skips_unexported(self, go_project, source_paths):
        result = resolve_go(
            "module", "internal/commit", [], source_paths, str(go_project)
        )
        assert "unexportedHelper" not in result

    def test_excludes_test_files(self, go_project, source_paths):
        """_test.go files should not be included in module extraction."""
        result = resolve_go(
            "module", "internal/commit", [], source_paths, str(go_project)
        )
        assert "TestNewPipeline" not in result
        assert "TestExecute" not in result

    def test_multi_file_types(self, go_project, source_paths):
        """Types from types.go should also appear."""
        result = resolve_go(
            "module", "internal/commit", [], source_paths, str(go_project)
        )
        assert "### Request" in result
        assert "### Result" in result

    def test_missing_package_error(self, go_project, source_paths):
        result = resolve_go(
            "module", "nonexistent/pkg", [], source_paths, str(go_project)
        )
        assert "not found" in result

    def test_empty_arg_error(self, go_project, source_paths):
        result = resolve_go(
            "module", "", [], source_paths, str(go_project)
        )
        assert "requires" in result


# ---------------------------------------------------------------------------
# :::test tests
# ---------------------------------------------------------------------------


class TestTestDirective:
    def test_extract_whole_file(self, go_project, source_paths):
        result = resolve_go(
            "test",
            "internal/commit/commit_test.go",
            [],
            source_paths,
            str(go_project),
        )
        assert "```go" in result
        assert "TestNewPipeline" in result
        assert "TestExecute" in result

    def test_extract_specific_function(self, go_project, source_paths):
        result = resolve_go(
            "test",
            "internal/commit/commit_test.go TestNewPipeline",
            [],
            source_paths,
            str(go_project),
        )
        assert "```go" in result
        assert "func TestNewPipeline" in result
        assert "NewPipeline" in result
        # Should not include TestExecute
        assert "TestExecute" not in result

    def test_includes_doc_comment(self, go_project, source_paths):
        result = resolve_go(
            "test",
            "internal/commit/commit_test.go TestNewPipeline",
            [],
            source_paths,
            str(go_project),
        )
        assert "verifies default construction" in result

    def test_missing_file_error(self, go_project, source_paths):
        result = resolve_go(
            "test",
            "nonexistent_test.go",
            [],
            source_paths,
            str(go_project),
        )
        assert "not found" in result

    def test_target_not_found_error(self, go_project, source_paths):
        result = resolve_go(
            "test",
            "internal/commit/commit_test.go NonExistentTest",
            [],
            source_paths,
            str(go_project),
        )
        assert "not found" in result
        assert "NonExistentTest" in result


# ---------------------------------------------------------------------------
# :::schema tests
# ---------------------------------------------------------------------------


class TestSchemaDirective:
    def test_extracts_struct_fields(self, go_project, source_paths):
        result = resolve_go(
            "schema",
            "internal/models/models.go Config",
            [],
            source_paths,
            str(go_project),
        )
        assert "| Field | Type | Tag | Description |" in result
        assert "| --- | --- | --- | --- |" in result
        assert "`Host`" in result
        assert "`string`" in result
        assert "Server hostname" in result

    def test_extracts_tags(self, go_project, source_paths):
        result = resolve_go(
            "schema",
            "internal/models/models.go Config",
            [],
            source_paths,
            str(go_project),
        )
        # Tags should be present
        assert "json:" in result

    def test_extracts_all_structs_when_no_name(self, go_project, source_paths):
        result = resolve_go(
            "schema",
            "internal/models/models.go",
            [],
            source_paths,
            str(go_project),
        )
        assert "Config" in result
        assert "Entry" in result
        assert "`Level`" in result
        assert "`Message`" in result

    def test_missing_struct_error(self, go_project, source_paths):
        result = resolve_go(
            "schema",
            "internal/models/models.go NonExistent",
            [],
            source_paths,
            str(go_project),
        )
        assert "not found" in result
        assert "NonExistent" in result

    def test_missing_file_error(self, go_project, source_paths):
        result = resolve_go(
            "schema",
            "nonexistent.go SomeType",
            [],
            source_paths,
            str(go_project),
        )
        assert "not found" in result

    def test_struct_with_json_tags(self, go_project, source_paths):
        """Result struct from types.go should have json tags extracted."""
        result = resolve_go(
            "schema",
            "internal/commit/types.go Result",
            [],
            source_paths,
            str(go_project),
        )
        assert "`SHA`" in result
        assert "`Ref`" in result
        assert "json:" in result


# ---------------------------------------------------------------------------
# :::cli tests
# ---------------------------------------------------------------------------


class TestCliDirective:
    def test_extracts_usage_function(self, go_project, source_paths):
        result = resolve_go(
            "cli",
            "cmd/myapp/main.go",
            [],
            source_paths,
            str(go_project),
        )
        assert "usageText()" in result
        assert "Usage: myapp <command> [options]" in result
        assert "```" in result

    def test_extracts_flag_definitions(self, go_project, source_paths):
        result = resolve_go(
            "cli",
            "cmd/myapp/main.go",
            [],
            source_paths,
            str(go_project),
        )
        assert "| Flag | Type | Default | Description |" in result
        assert "`verbose`" in result
        assert "`output`" in result
        assert "Enable verbose output" in result
        assert "Output file path" in result

    def test_missing_file_error(self, go_project, source_paths):
        result = resolve_go(
            "cli",
            "nonexistent.go",
            [],
            source_paths,
            str(go_project),
        )
        assert "not found" in result


# ---------------------------------------------------------------------------
# :::config tests
# ---------------------------------------------------------------------------


class TestConfigDirective:
    def test_json_config_table(self, go_project, source_paths):
        result = resolve_go(
            "config",
            "config.json",
            [],
            source_paths,
            str(go_project),
        )
        assert "| Key | Type | Value |" in result
        assert "`host`" in result
        assert "string" in result
        assert "`port`" in result
        assert "integer" in result

    def test_missing_file_error(self, go_project, source_paths):
        result = resolve_go(
            "config",
            "missing.json",
            [],
            source_paths,
            str(go_project),
        )
        assert "not found" in result


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_unknown_directive(self, go_project, source_paths):
        result = resolve_go(
            "unknown", "arg", [], source_paths, str(go_project)
        )
        assert "unknown directive" in result

    def test_empty_arg_for_test(self, go_project, source_paths):
        result = resolve_go(
            "test", "", [], source_paths, str(go_project)
        )
        assert "requires" in result

    def test_empty_arg_for_schema(self, go_project, source_paths):
        result = resolve_go(
            "schema", "", [], source_paths, str(go_project)
        )
        assert "requires" in result

    def test_empty_arg_for_cli(self, go_project, source_paths):
        result = resolve_go(
            "cli", "", [], source_paths, str(go_project)
        )
        assert "requires" in result

    def test_empty_arg_for_config(self, go_project, source_paths):
        result = resolve_go(
            "config", "", [], source_paths, str(go_project)
        )
        assert "requires" in result
