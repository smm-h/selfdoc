package cli

import (
	"strings"
	"testing"
)

// What `assembly preview` declares at registration.
//
// The declarations are the contract: which inputs have no default, that the
// command refuses to pretend it can preview itself, and that it is classified
// as the mutation it is. The tree it assembles and the server it runs have
// their own package.

func TestPreviewIsMutatingAndNotConsequential(t *testing.T) {
	entry := walk(t)["assembly.preview"]
	if entry["effect"] != "mutating" {
		t.Errorf("preview is classified %v", entry["effect"])
	}
	if _, declared := entry["consequential"]; declared {
		t.Error("preview declares itself consequential; nothing it writes reaches the world")
	}
}

func TestPreviewRefusesDryRunWithAReason(t *testing.T) {
	entry := walk(t)["assembly.preview"]
	if entry["dry_run_supported"] != false {
		t.Error("preview does not refuse a preview of itself")
	}
	reason, _ := entry["dry_run_unsupported_reason"].(string)
	if !strings.Contains(reason, "look at") {
		t.Errorf("the refusal reason is %q", reason)
	}
}

func TestEveryPreviewInputThatDecidesTheOutputIsRequired(t *testing.T) {
	// Presence is declared, never derived: an absent default no longer means
	// anything on its own.
	flags := flagsOf(t, "assembly.preview")
	for _, name := range []string{"home", "out", "port", "canonical-base", "build"} {
		flag, ok := flags[name]
		if !ok {
			t.Errorf("preview declares no --%s", name)
			continue
		}
		if flag["presence"] != "required" {
			t.Errorf("--%s presence is %v, want required", name, flag["presence"])
		}
	}
}

func TestThePreviewBuildChoiceIsNegatableRatherThanDefaulted(t *testing.T) {
	build := flagsOf(t, "assembly.preview")["build"]
	schema, _ := build["value_schema"].(map[string]any)
	if schema["type"] != "boolean" {
		t.Errorf("--build type is %v", schema["type"])
	}
	if negatable, declared := build["negatable"]; declared && negatable == false {
		t.Error("--build is not negatable")
	}
	isolate(t)
	// The negated spelling parses: a refusal here would come from the missing
	// required flags, never from --no-build being unknown.
	result := run(t, t.TempDir(), "assembly", "preview", "--no-build")
	if strings.Contains(result.Stderr, "--no-build") &&
		strings.Contains(result.Stderr, "unknown") {
		t.Errorf("--no-build is not recognized: %s", result.Stderr)
	}
}

func TestThePreviewRepoFlagIsRepeatableAndDeduplicated(t *testing.T) {
	// Arity is part of the value's shape, so a repeatable scalar flag
	// publishes the array fragment; deduplication is its own declaration.
	repo := flagsOf(t, "assembly.preview")["repo"]
	if repo["unique"] != true {
		t.Errorf("--repo is not deduplicated: %v", repo)
	}
	schema, _ := repo["value_schema"].(map[string]any)
	if schema["type"] != "array" {
		t.Errorf("--repo value schema is %v", schema)
	}
	items, _ := schema["items"].(map[string]any)
	if items["type"] != "string" {
		t.Errorf("--repo item schema is %v", items)
	}

	// And it really accumulates: a second occurrence is not "already given".
	isolate(t)
	result := run(t, t.TempDir(), "assembly", "preview",
		"--repo", "one", "--repo", "two")
	if strings.Contains(result.Stderr, "--repo") &&
		strings.Contains(result.Stderr, "more than once") {
		t.Errorf("a second --repo was refused: %s", result.Stderr)
	}
}
