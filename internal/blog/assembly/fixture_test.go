package assembly

import (
	"encoding/base64"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"testing"

	"github.com/smm-h/selfdoc/internal/blog/site"
	"github.com/smm-h/stricttest/go/hygiene"
)

// fakeGHStateEnv names the directory the fake gh keeps its state in. Its
// presence in the environment is what turns this test binary into the fake gh
// rather than a test run -- see [TestMain].
const fakeGHStateEnv = "SELFDOC_ASSEMBLY_FAKE_GH_STATE"

// TestMain is the fake gh's entry point as well as the suite's.
//
// Every operation in this package that reaches GitHub does it by running "gh
// api", so the seam a test replaces is the executable rather than a function:
// a script at the front of PATH shadows the real gh, and that script re-runs
// this binary with [fakeGHStateEnv] set. The fake is therefore ordinary Go
// code with the whole Git Data API's bookkeeping in it -- persistent blobs, a
// real git blob hash per path, base64 payloads -- rather than a shell script
// pretending to be one, and the call the code under test makes is a real
// subprocess through the real effects handle.
func TestMain(m *testing.M) {
	if dir := os.Getenv(fakeGHStateEnv); dir != "" {
		os.Exit(runFakeGH(dir, os.Args[1:]))
	}
	os.Exit(m.Run())
}

// ghCallRecord is one recorded invocation of the fake gh.
type ghCallRecord struct {
	// Argv is everything after the program name.
	Argv []string `json:"argv"`
	// Input is the request body the call wrote to standard input.
	Input string `json:"input"`
}

// Joined renders the argv the way an assertion reads it.
func (r ghCallRecord) Joined() string { return strings.Join(r.Argv, " ") }

// ghResponse is one scripted answer.
type ghResponse struct {
	// Code is the exit status.
	Code int `json:"code"`
	// Stdout and Stderr are the streams the call writes.
	Stdout string `json:"stdout"`
	Stderr string `json:"stderr"`
}

// ghFailure injects a failure into repo mode for every call whose argv
// contains Match.
type ghFailure struct {
	// Match is the substring of the joined argv this failure applies to.
	Match string `json:"match"`
	// Code is the exit status to answer with.
	Code int `json:"code"`
	// Stderr is what the call writes to standard error.
	Stderr string `json:"stderr"`
}

// fakeGH is a fake gh at the front of PATH, with the state the fake keeps.
type fakeGH struct {
	t   *testing.T
	dir string
}

// newFakeGH installs a fake gh in a directory at the front of PATH and returns
// the handle a test drives it through.
//
// It binds the environment isolation floor first: a throwaway HOME, an empty
// global git config with a throwaway identity, only the file:// git transport,
// and no ambient credentials. Nothing here calls t.Parallel, because hygiene
// mutates process-wide variables.
func newFakeGH(t *testing.T) *fakeGH {
	t.Helper()
	bin := isolate(t)
	state := t.TempDir()
	binary, err := os.Executable()
	if err != nil {
		t.Fatalf("locating the test binary: %v", err)
	}
	script := fmt.Sprintf(
		"#!/bin/sh\nexport %s=%s\nexec %s \"$@\"\n",
		fakeGHStateEnv, shellQuote(state), shellQuote(binary),
	)
	if err := os.WriteFile(filepath.Join(bin, "gh"), []byte(script), 0o755); err != nil {
		t.Fatalf("writing the fake gh: %v", err)
	}
	return &fakeGH{t: t, dir: state}
}

// isolate binds the environment isolation floor -- a throwaway HOME, an empty
// global git config with a throwaway identity, only the file:// git transport,
// no ambient credentials -- and returns a directory at the FRONT of PATH, so a
// fake tool written there shadows any real one. The system directories stay
// behind it, so git stays reachable.
//
// Nothing that calls this may call t.Parallel: hygiene mutates process-wide
// variables.
func isolate(t *testing.T) string {
	t.Helper()
	hygiene.Isolate(t)
	bin := t.TempDir()
	t.Setenv("PATH", bin+":/usr/bin:/bin")
	return bin
}

// shellQuote single-quotes a token for the fake gh's shell wrapper.
func shellQuote(token string) string {
	return "'" + strings.ReplaceAll(token, "'", `'\''`) + "'"
}

// path is a file inside the fake's state directory.
func (f *fakeGH) path(name string) string { return filepath.Join(f.dir, name) }

// writeJSON writes a state file.
func (f *fakeGH) writeJSON(name string, value any) {
	f.t.Helper()
	data, err := json.Marshal(value)
	if err != nil {
		f.t.Fatalf("encoding %s: %v", name, err)
	}
	if err := os.WriteFile(f.path(name), data, 0o644); err != nil {
		f.t.Fatalf("writing %s: %v", name, err)
	}
}

// Script puts the fake in scripted mode: it answers each call from responses
// in order, whatever the call asked for, and fails the run when a call arrives
// with no answer left.
func (f *fakeGH) Script(responses ...ghResponse) {
	f.t.Helper()
	f.writeJSON("script.json", responses)
}

// Blobs seeds repo mode with the files the branch already holds.
func (f *fakeGH) Blobs(blobs map[string][]byte) {
	f.t.Helper()
	encoded := map[string]string{}
	for path, data := range blobs {
		encoded[path] = base64.StdEncoding.EncodeToString(data)
	}
	f.writeJSON("blobs.json", encoded)
}

// Truncate makes the Trees API report a tree too large to return, which is the
// one answer that cannot be read as an empty repository.
func (f *fakeGH) Truncate() {
	f.t.Helper()
	f.writeJSON("truncated.json", true)
}

// Fail injects a failure for every call whose joined argv contains match.
func (f *fakeGH) Fail(match string, code int, stderr string) {
	f.t.Helper()
	failures := f.failures()
	failures = append(failures, ghFailure{Match: match, Code: code, Stderr: stderr})
	f.writeJSON("failures.json", failures)
}

// failures is the injected failure list.
func (f *fakeGH) failures() []ghFailure {
	data, err := os.ReadFile(f.path("failures.json"))
	if err != nil {
		return nil
	}
	var failures []ghFailure
	if err := json.Unmarshal(data, &failures); err != nil {
		f.t.Fatalf("decoding failures.json: %v", err)
	}
	return failures
}

// Calls is every invocation the fake recorded, in order.
func (f *fakeGH) Calls() []ghCallRecord {
	f.t.Helper()
	data, err := os.ReadFile(f.path("calls.jsonl"))
	if os.IsNotExist(err) {
		return nil
	}
	if err != nil {
		f.t.Fatalf("reading the call log: %v", err)
	}
	var calls []ghCallRecord
	for _, line := range strings.Split(strings.TrimSuffix(string(data), "\n"), "\n") {
		if line == "" {
			continue
		}
		var call ghCallRecord
		if err := json.Unmarshal([]byte(line), &call); err != nil {
			f.t.Fatalf("decoding a call log line: %v", err)
		}
		calls = append(calls, call)
	}
	return calls
}

// Content is the bytes repo mode holds at a path, and whether it holds it.
func (f *fakeGH) Content(path string) ([]byte, bool) {
	f.t.Helper()
	blobs := f.storedBlobs()
	encoded, ok := blobs[path]
	if !ok {
		return nil, false
	}
	data, err := base64.StdEncoding.DecodeString(encoded)
	if err != nil {
		f.t.Fatalf("decoding the stored blob at %s: %v", path, err)
	}
	return data, true
}

// Text is the text repo mode holds at a path, failing the test when it holds
// nothing there.
func (f *fakeGH) Text(path string) string {
	f.t.Helper()
	data, ok := f.Content(path)
	if !ok {
		f.t.Fatalf("the fake remote holds nothing at %s; it holds %v",
			path, f.Paths())
	}
	return string(data)
}

// Paths is every path repo mode holds, sorted.
func (f *fakeGH) Paths() []string {
	f.t.Helper()
	blobs := f.storedBlobs()
	paths := make([]string, 0, len(blobs))
	for path := range blobs {
		paths = append(paths, path)
	}
	sort.Strings(paths)
	return paths
}

// storedBlobs is repo mode's file table.
func (f *fakeGH) storedBlobs() map[string]string {
	f.t.Helper()
	data, err := os.ReadFile(f.path("blobs.json"))
	if os.IsNotExist(err) {
		return map[string]string{}
	}
	if err != nil {
		f.t.Fatalf("reading the fake remote's blobs: %v", err)
	}
	blobs := map[string]string{}
	if err := json.Unmarshal(data, &blobs); err != nil {
		f.t.Fatalf("decoding the fake remote's blobs: %v", err)
	}
	return blobs
}

// Commits is how many commits repo mode created.
func (f *fakeGH) Commits() int { return f.counter("commits") }

// Uploads is how many blobs repo mode accepted.
func (f *fakeGH) Uploads() int { return f.counter("uploads") }

// counter reads one of repo mode's counters.
func (f *fakeGH) counter(name string) int {
	f.t.Helper()
	data, err := os.ReadFile(f.path(name + ".count"))
	if os.IsNotExist(err) {
		return 0
	}
	if err != nil {
		f.t.Fatalf("reading the %s counter: %v", name, err)
	}
	count := 0
	if _, err := fmt.Sscanf(strings.TrimSpace(string(data)), "%d", &count); err != nil {
		f.t.Fatalf("decoding the %s counter: %v", name, err)
	}
	return count
}

// -- the fake gh itself ------------------------------------------------------

// runFakeGH answers one gh invocation and returns its exit status.
//
// Two modes, chosen by what the state directory holds. A "script.json" answers
// each call from a list in order, which is how a test asserts the exact
// sequence of API calls a push makes and how it injects a failure at one step.
// Otherwise the fake is a repository: it holds blobs, reports their real git
// blob hashes to the Trees API, applies a tree the way the API does -- an
// uploaded blob per entry, a null sha as a deletion -- and answers the
// Contents API from the same table. That is what makes an idempotence
// assertion mean anything: the second run reads back the bytes the first one
// wrote.
func runFakeGH(dir string, argv []string) int {
	input := readAllStdinIfRequested(argv)
	recordCall(dir, argv, input)
	joined := strings.Join(argv, " ")

	if responses, ok := loadScript(dir); ok {
		index := bumpCounter(dir, "script")
		if index > len(responses) {
			fmt.Fprintf(os.Stderr,
				"fake gh: call %d has no scripted answer: %s\n", index, joined)
			return 99
		}
		answer := responses[index-1]
		os.Stdout.WriteString(answer.Stdout)
		os.Stderr.WriteString(answer.Stderr)
		return answer.Code
	}

	for _, failure := range loadFailures(dir) {
		if strings.Contains(joined, failure.Match) {
			os.Stderr.WriteString(failure.Stderr)
			return failure.Code
		}
	}
	return repoModeAnswer(dir, argv, joined, input)
}

// repoModeAnswer answers one call against the fake repository's own state.
func repoModeAnswer(dir string, argv []string, joined, input string) int {
	switch {
	case strings.Contains(joined, "/git/ref/heads/"):
		fmt.Print("headsha")
		return 0
	case strings.Contains(joined, "/git/commits/headsha"):
		fmt.Print("basetree")
		return 0
	case strings.Contains(joined, "/git/trees/basetree"):
		return answerTree(dir)
	case strings.Contains(joined, "/git/blobs"):
		return acceptBlob(dir, input)
	case strings.Contains(joined, "/git/trees"):
		return applyTree(dir, input)
	case strings.Contains(joined, "/git/commits"):
		bumpCounter(dir, "commits")
		fmt.Print("newcommit")
		return 0
	case strings.Contains(joined, "/git/refs/heads/"):
		fmt.Print("newcommit")
		return 0
	case strings.Contains(joined, "/contents/"):
		return answerContents(dir, argv)
	case strings.Contains(joined, "/actions/runs"):
		fmt.Print("{\"status\":\"completed\"}")
		return 0
	case strings.Contains(joined, "/dispatches"):
		return 0
	}
	fmt.Fprintf(os.Stderr, "fake gh: unrouted call: %s\n", joined)
	return 98
}

// answerTree reports every blob the branch holds, with its real git hash.
func answerTree(dir string) int {
	type entry struct {
		Path string `json:"path"`
		Type string `json:"type"`
		Mode string `json:"mode"`
		SHA  string `json:"sha"`
	}
	blobs := readBlobs(dir)
	paths := make([]string, 0, len(blobs))
	for path := range blobs {
		paths = append(paths, path)
	}
	sort.Strings(paths)
	entries := make([]entry, 0, len(paths))
	for _, path := range paths {
		data, _ := base64.StdEncoding.DecodeString(blobs[path])
		entries = append(entries, entry{
			Path: path, Type: "blob", Mode: "100644",
			SHA: site.GitBlobSHA1(data),
		})
	}
	document := map[string]any{
		"truncated": readFlag(dir, "truncated.json"),
		"tree":      entries,
	}
	encoded, err := json.Marshal(document)
	if err != nil {
		fmt.Fprintf(os.Stderr, "fake gh: %v\n", err)
		return 97
	}
	os.Stdout.Write(encoded)
	return 0
}

// acceptBlob stores one uploaded blob under a fresh sha and answers with it.
func acceptBlob(dir, input string) int {
	var payload struct {
		Content  string `json:"content"`
		Encoding string `json:"encoding"`
	}
	if err := json.Unmarshal([]byte(input), &payload); err != nil {
		fmt.Fprintf(os.Stderr, "fake gh: unreadable blob payload: %v\n", err)
		return 96
	}
	index := bumpCounter(dir, "uploads")
	sha := fmt.Sprintf("newblob%d", index)
	pending := readTable(dir, "pending.json")
	pending[sha] = payload.Content
	writeTable(dir, "pending.json", pending)
	fmt.Print(sha)
	return 0
}

// applyTree applies a tree request to the fake repository: an entry naming an
// uploaded blob writes it, and an entry with a null sha deletes the path.
func applyTree(dir, input string) int {
	var payload struct {
		BaseTree string `json:"base_tree"`
		Tree     []struct {
			Path string  `json:"path"`
			SHA  *string `json:"sha"`
		} `json:"tree"`
	}
	if err := json.Unmarshal([]byte(input), &payload); err != nil {
		fmt.Fprintf(os.Stderr, "fake gh: unreadable tree payload: %v\n", err)
		return 95
	}
	blobs := readBlobs(dir)
	pending := readTable(dir, "pending.json")
	for _, item := range payload.Tree {
		if item.SHA == nil {
			delete(blobs, item.Path)
			continue
		}
		content, ok := pending[*item.SHA]
		if !ok {
			fmt.Fprintf(os.Stderr,
				"fake gh: tree names blob %s, which was never uploaded\n", *item.SHA)
			return 94
		}
		blobs[item.Path] = content
	}
	writeTable(dir, "blobs.json", blobs)
	fmt.Print("newtree")
	return 0
}

// answerContents answers the Contents API from the same file table, with an
// absent path reported the way gh reports one.
func answerContents(dir string, argv []string) int {
	path := ""
	for _, arg := range argv {
		if index := strings.Index(arg, "/contents/"); index >= 0 {
			path = arg[index+len("/contents/"):]
		}
	}
	blobs := readBlobs(dir)
	encoded, ok := blobs[path]
	if !ok {
		fmt.Fprintf(os.Stderr, "gh: Not Found (HTTP 404)\n")
		return 1
	}
	fmt.Print(encoded)
	return 0
}

// readAllStdinIfRequested reads the request body, but only for a call that
// declared one: a call with no "--input -" has no body, and reading an
// inherited standard input would block.
func readAllStdinIfRequested(argv []string) string {
	wants := false
	for _, arg := range argv {
		if arg == "--input" {
			wants = true
		}
	}
	if !wants {
		return ""
	}
	var builder strings.Builder
	buffer := make([]byte, 4096)
	for {
		read, err := os.Stdin.Read(buffer)
		builder.Write(buffer[:read])
		if err != nil {
			break
		}
	}
	return builder.String()
}

// recordCall appends one invocation to the call log.
func recordCall(dir string, argv []string, input string) {
	encoded, err := json.Marshal(ghCallRecord{Argv: argv, Input: input})
	if err != nil {
		return
	}
	file, err := os.OpenFile(
		filepath.Join(dir, "calls.jsonl"),
		os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0o644,
	)
	if err != nil {
		return
	}
	defer file.Close()
	file.Write(append(encoded, '\n'))
}

// loadScript reads the scripted answers, reporting whether the fake is in
// scripted mode at all.
func loadScript(dir string) ([]ghResponse, bool) {
	data, err := os.ReadFile(filepath.Join(dir, "script.json"))
	if err != nil {
		return nil, false
	}
	var responses []ghResponse
	if err := json.Unmarshal(data, &responses); err != nil {
		return nil, false
	}
	return responses, true
}

// loadFailures reads the injected failures.
func loadFailures(dir string) []ghFailure {
	data, err := os.ReadFile(filepath.Join(dir, "failures.json"))
	if err != nil {
		return nil
	}
	var failures []ghFailure
	json.Unmarshal(data, &failures)
	return failures
}

// readBlobs is the fake repository's file table, path -> base64 content.
func readBlobs(dir string) map[string]string {
	return readTable(dir, "blobs.json")
}

// readTable reads one string-to-string state file.
func readTable(dir, name string) map[string]string {
	table := map[string]string{}
	data, err := os.ReadFile(filepath.Join(dir, name))
	if err != nil {
		return table
	}
	json.Unmarshal(data, &table)
	return table
}

// writeTable writes one string-to-string state file.
func writeTable(dir, name string, table map[string]string) {
	data, err := json.Marshal(table)
	if err != nil {
		return
	}
	os.WriteFile(filepath.Join(dir, name), data, 0o644)
}

// readFlag reads a boolean state file.
func readFlag(dir, name string) bool {
	data, err := os.ReadFile(filepath.Join(dir, name))
	if err != nil {
		return false
	}
	return strings.TrimSpace(string(data)) == "true"
}

// bumpCounter increments a counter file and returns its new value.
func bumpCounter(dir, name string) int {
	path := filepath.Join(dir, name+".count")
	count := 0
	if data, err := os.ReadFile(path); err == nil {
		fmt.Sscanf(strings.TrimSpace(string(data)), "%d", &count)
	}
	count++
	os.WriteFile(path, []byte(fmt.Sprintf("%d", count)), 0o644)
	return count
}
