package util

import (
	"reflect"
	"testing"
	"time"
)

// tomlSample exercises every construct whose decoded shape a hand-written
// validation elsewhere in this module asserts on.
const tomlSample = `title = "x"
count = 3
ratio = 1.5
enabled = true
moment = 1979-05-27T07:32:00Z
day = 1979-05-27
arr = [1, 2]
inline = {a = 1, b = {c = 2}}
dotted.x.y = 5

[server]
host = "y"

[[items]]
k = 1

[[items]]
k = 2

[deep.nest]
z = 9
`

// TestDecodeTOMLShapes pins the Go type every decoded TOML value arrives as.
// Each one is read back by a type assertion somewhere in this module, and a
// refusal message names what it found, so a changed shape is a changed
// refusal.
func TestDecodeTOMLShapes(t *testing.T) {
	t.Parallel()
	values, err := DecodeTOML([]byte(tomlSample))
	if err != nil {
		t.Fatalf("DecodeTOML: %v", err)
	}

	assertShape := func(key string, want any) {
		t.Helper()
		got, present := values[key]
		if !present {
			t.Fatalf("%s is missing", key)
		}
		if reflect.TypeOf(got) != reflect.TypeOf(want) {
			t.Fatalf("%s is %T, want %T", key, got, want)
		}
		if !reflect.DeepEqual(got, want) {
			t.Fatalf("%s = %#v, want %#v", key, got, want)
		}
	}

	assertShape("title", "x")
	assertShape("count", int64(3))
	assertShape("ratio", 1.5)
	assertShape("enabled", true)
	assertShape("moment", time.Date(1979, time.May, 27, 7, 32, 0, 0, time.UTC))
	assertShape("day", time.Date(1979, time.May, 27, 0, 0, 0, 0, time.Local))
	assertShape("arr", []any{int64(1), int64(2)})
	assertShape("inline", map[string]any{
		"a": int64(1), "b": map[string]any{"c": int64(2)},
	})
	assertShape("dotted", map[string]any{"x": map[string]any{"y": int64(5)}})
	assertShape("server", map[string]any{"host": "y"})
	assertShape("deep", map[string]any{"nest": map[string]any{"z": int64(9)}})

	assertShape("items", []map[string]any{{"k": int64(1)}, {"k": int64(2)}})
}

// TestDecodeTOMLNestedArrayOfTables pins the shape a [[category]] block
// carrying [[category.project]] blocks decodes into: each outer element keeps
// its own inner array, which is what the curated listing reads.
func TestDecodeTOMLNestedArrayOfTables(t *testing.T) {
	t.Parallel()
	values, err := DecodeTOML([]byte(
		"[[category]]\nname = \"A\"\n\n[[category.project]]\nslug = \"a\"\n\n" +
			"[[category.project]]\nslug = \"b\"\n\n[[category]]\nname = \"B\"\n\n" +
			"[[category.project]]\nslug = \"c\"\n"))
	if err != nil {
		t.Fatalf("DecodeTOML: %v", err)
	}
	want := []map[string]any{
		{"name": "A", "project": []map[string]any{{"slug": "a"}, {"slug": "b"}}},
		{"name": "B", "project": []map[string]any{{"slug": "c"}}},
	}
	if !reflect.DeepEqual(values["category"], want) {
		t.Fatalf("category = %#v, want %#v", values["category"], want)
	}
}

// TestDecodeTOMLOrderedKeys pins the replayable key order a renderer whose row
// order is document order reads: a table header before the keys written under
// it, one entry per array-of-tables element, and an inline table's own keys
// under the key it is bound to.
func TestDecodeTOMLOrderedKeys(t *testing.T) {
	t.Parallel()
	_, keys, err := DecodeTOMLOrdered([]byte(tomlSample))
	if err != nil {
		t.Fatalf("DecodeTOMLOrdered: %v", err)
	}
	want := [][]string{
		{"title"}, {"count"}, {"ratio"}, {"enabled"}, {"moment"}, {"day"},
		{"arr"},
		{"inline"}, {"inline", "a"}, {"inline", "b"}, {"inline", "b", "c"},
		{"dotted", "x", "y"},
		{"server"}, {"server", "host"},
		{"items"}, {"items", "k"},
		{"items"}, {"items", "k"},
		{"deep", "nest"}, {"deep", "nest", "z"},
	}
	if !reflect.DeepEqual(keys, want) {
		t.Fatalf("keys = %#v, want %#v", keys, want)
	}
}

// TestDecodeTOMLRefusesASyntaxError pins that a malformed document is an
// error rather than an empty decode: every caller turns it into a refusal
// naming the file.
func TestDecodeTOMLRefusesASyntaxError(t *testing.T) {
	t.Parallel()
	if _, err := DecodeTOML([]byte("format_version = ")); err == nil {
		t.Fatal("a syntax error decoded without an error")
	}
	if _, err := DecodeTOML([]byte("[[project]\n")); err == nil {
		t.Fatal("an unterminated table header decoded without an error")
	}
}

// TestDecodeTOMLEmptyDocument answers an empty map rather than a nil one, so a
// caller may read a key off it without a nil check.
func TestDecodeTOMLEmptyDocument(t *testing.T) {
	t.Parallel()
	values, err := DecodeTOML(nil)
	if err != nil {
		t.Fatalf("DecodeTOML: %v", err)
	}
	if values == nil || len(values) != 0 {
		t.Fatalf("values = %#v, want an empty map", values)
	}
}
