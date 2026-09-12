package cli

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"

	"github.com/smm-h/selfdoc/internal/testproject"
	"github.com/smm-h/strictcli/go/strictcli"
	"github.com/smm-h/stricttest/go/hygiene"
)

// fakeToolStateEnv names the directory the fake external tools keep their
// state in. Its presence in the environment is what turns this test binary
// into the fake tool rather than a test run -- see TestMain.
const fakeToolStateEnv = "SELFDOC_CLI_FAKE_TOOL_STATE"

// TestMain is the fake tools' entry point as well as the suite's.
//
// Every command that reaches GitHub or Cloudflare does it by running "gh" or
// "npx", so the seam a test replaces is the executable rather than a function:
// a script at the front of PATH shadows the real tool and re-runs this binary
// with fakeToolStateEnv set. The call the command makes is therefore a real
// subprocess through the real effects handle.
func TestMain(m *testing.M) {
	if dir := os.Getenv(fakeToolStateEnv); dir != "" {
		os.Exit(runFakeTool(dir, os.Args[0], os.Args[1:]))
	}
	if os.Getenv(runAsCLIEnv) != "" {
		New(Options{}).Run()
		return
	}
	os.Exit(m.Run())
}

// runAsCLIEnv turns this test binary into the real command-line application,
// which is how the two properties that only exist outside App.Test are
// asserted: the confirmation a consequential command demands at a terminal
// (App.Test behaves as if consent were given and never prompts), and the
// schema --dump-schema writes to the working directory.
const runAsCLIEnv = "SELFDOC_CLI_RUN_AS_CLI"

// cliProcess is one real invocation of the application as a subprocess.
type cliProcess struct {
	Stdout   string
	Stderr   string
	ExitCode int
}

// runCLI runs the application as a real subprocess with dir as its working
// directory and a non-interactive standard input.
func runCLI(t *testing.T, dir string, argv ...string) cliProcess {
	t.Helper()
	binary, err := os.Executable()
	if err != nil {
		t.Fatalf("locating the test binary: %v", err)
	}
	devnull, err := os.Open(os.DevNull)
	if err != nil {
		t.Fatalf("opening %s: %v", os.DevNull, err)
	}
	defer devnull.Close()

	command := exec.Command(binary, argv...)
	command.Dir = dir
	command.Stdin = devnull
	command.Env = append(os.Environ(), runAsCLIEnv+"=1")
	var stdout, stderr bytes.Buffer
	command.Stdout = &stdout
	command.Stderr = &stderr
	err = command.Run()
	code := 0
	if err != nil {
		exitErr, ok := err.(*exec.ExitError)
		if !ok {
			t.Fatalf("running the application: %v", err)
		}
		code = exitErr.ExitCode()
	}
	return cliProcess{Stdout: stdout.String(), Stderr: stderr.String(), ExitCode: code}
}

// toolReply is one scripted answer. Match is a substring of the joined argv;
// an empty Match answers anything.
type toolReply struct {
	Match  string `json:"match"`
	Code   int    `json:"code"`
	Stdout string `json:"stdout"`
	Stderr string `json:"stderr"`
}

// toolCall is one recorded invocation of a fake tool.
type toolCall struct {
	Tool  string   `json:"tool"`
	Argv  []string `json:"argv"`
	Input string   `json:"input"`
}

// Joined renders the argv the way an assertion reads it.
func (c toolCall) Joined() string { return c.Tool + " " + strings.Join(c.Argv, " ") }

// fakeTools is a set of fake executables at the front of PATH, plus the state
// they record into.
type fakeTools struct {
	t   *testing.T
	dir string
}

// newFakeTools installs fakes for the named executables and returns the handle
// a test drives them through.
func newFakeTools(t *testing.T, names ...string) *fakeTools {
	t.Helper()
	bin := isolate(t)
	state := t.TempDir()
	binary, err := os.Executable()
	if err != nil {
		t.Fatalf("locating the test binary: %v", err)
	}
	for _, name := range names {
		script := fmt.Sprintf("#!/bin/sh\nexport %s=%s\nexec %s \"$@\"\n",
			fakeToolStateEnv, shellQuote(state), shellQuote(binary))
		if err := os.WriteFile(filepath.Join(bin, name), []byte(script), 0o755); err != nil {
			t.Fatalf("writing the fake %s: %v", name, err)
		}
	}
	return &fakeTools{t: t, dir: state}
}

// Reply scripts the answers, matched against each call's joined argv in order.
func (f *fakeTools) Reply(replies ...toolReply) {
	f.t.Helper()
	data, err := json.Marshal(replies)
	if err != nil {
		f.t.Fatalf("encoding the replies: %v", err)
	}
	if err := os.WriteFile(filepath.Join(f.dir, "replies.json"), data, 0o644); err != nil {
		f.t.Fatalf("writing the replies: %v", err)
	}
}

// Calls returns every invocation recorded so far, in order.
func (f *fakeTools) Calls() []toolCall {
	f.t.Helper()
	data, err := os.ReadFile(filepath.Join(f.dir, "calls.jsonl"))
	if err != nil {
		if os.IsNotExist(err) {
			return nil
		}
		f.t.Fatalf("reading the recorded calls: %v", err)
	}
	var calls []toolCall
	for _, line := range strings.Split(strings.TrimSpace(string(data)), "\n") {
		if line == "" {
			continue
		}
		var call toolCall
		if err := json.Unmarshal([]byte(line), &call); err != nil {
			f.t.Fatalf("decoding a recorded call: %v", err)
		}
		calls = append(calls, call)
	}
	return calls
}

// Matching returns every recorded call whose joined argv contains needle.
func (f *fakeTools) Matching(needle string) []toolCall {
	f.t.Helper()
	var found []toolCall
	for _, call := range f.Calls() {
		if strings.Contains(call.Joined(), needle) {
			found = append(found, call)
		}
	}
	return found
}

// runFakeTool is the fake executable's whole body: record the call, then
// answer from the scripted replies.
func runFakeTool(dir, program string, argv []string) int {
	input := ""
	for _, arg := range argv {
		if arg == "-" {
			data, _ := io.ReadAll(os.Stdin)
			input = string(data)
			break
		}
	}
	tool := filepath.Base(program)
	record := toolCall{Tool: tool, Argv: argv, Input: input}
	if data, err := json.Marshal(record); err == nil {
		if file, err := os.OpenFile(filepath.Join(dir, "calls.jsonl"),
			os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0o644); err == nil {
			_, _ = file.Write(append(data, '\n'))
			_ = file.Close()
		}
	}

	var replies []toolReply
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

// isolate binds the environment isolation floor and returns a directory at the
// FRONT of PATH, so a fake tool written there shadows any real one. The
// inherited PATH stays behind it, so git and python3 stay reachable.
//
// Nothing that calls this may call t.Parallel: hygiene mutates process-wide
// variables.
func isolate(t *testing.T) string {
	t.Helper()
	hygiene.Isolate(t)
	bin := t.TempDir()
	t.Setenv("PATH", bin+":"+os.Getenv("PATH"))
	return bin
}

// shellQuote single-quotes a token for a fake tool's shell wrapper.
func shellQuote(token string) string {
	return "'" + strings.ReplaceAll(token, "'", `'\''`) + "'"
}

// newApp builds the application under test, pointed at dir.
func newApp(t *testing.T, dir string) *strictcli.App {
	t.Helper()
	return New(Options{Dir: dir})
}

// run invokes the application with argv and returns the framework's result.
func run(t *testing.T, dir string, argv ...string) strictcli.Result {
	t.Helper()
	return newApp(t, dir).Test(argv)
}

// runWith invokes the application built from the given options, which is how
// a test states the stubbed registries a toolchain-pin check reads.
func runWith(t *testing.T, opts Options, argv ...string) strictcli.Result {
	t.Helper()
	return New(opts).Test(argv)
}

// payloadOf decodes the envelope a --json run wrote and returns its payload.
func payloadOf(t *testing.T, result strictcli.Result) map[string]any {
	t.Helper()
	var envelope map[string]any
	if err := json.Unmarshal([]byte(result.Stdout), &envelope); err != nil {
		t.Fatalf("decoding the envelope: %v\nstdout: %s\nstderr: %s",
			err, result.Stdout, result.Stderr)
	}
	payload, ok := envelope["payload"].(map[string]any)
	if !ok {
		t.Fatalf("the envelope carries no object payload: %s", result.Stdout)
	}
	return payload
}

// writeText writes a file, creating its parents.
func writeText(t *testing.T, path, content string) {
	t.Helper()
	testproject.WriteText(t, path, content)
}

// readText reads a file's whole contents.
func readText(t *testing.T, path string) string {
	t.Helper()
	return testproject.ReadText(t, path)
}

// readJSON decodes a JSON file into a generic tree.
func readJSON(t *testing.T, path string) map[string]any {
	t.Helper()
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("reading %s: %v", path, err)
	}
	var value map[string]any
	if err := json.Unmarshal(data, &value); err != nil {
		t.Fatalf("decoding %s: %v", path, err)
	}
	return value
}

// exists reports whether path names an existing file or directory.
func exists(path string) bool {
	_, err := os.Stat(path)
	return err == nil
}
