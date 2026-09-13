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

// TestDecodeTOMLDeeplyNestedArraysOfTables pins that an array of tables nested
// inside an array of tables nested inside another one keeps every element, and
// that a plain table written under an element belongs to that element rather
// than to a later one.
func TestDecodeTOMLDeeplyNestedArraysOfTables(t *testing.T) {
	t.Parallel()
	values, err := DecodeTOML([]byte(
		"[[a]]\nn = 1\n\n[[a.b]]\nn = 2\n\n[[a.b.c]]\nn = 3\n\n" +
			"[[a.b.c]]\nn = 4\n\n[a.b.meta]\nflag = true\n\n" +
			"[[a.b]]\nn = 5\n\n[[a]]\nn = 6\n"))
	if err != nil {
		t.Fatalf("DecodeTOML: %v", err)
	}
	want := []map[string]any{
		{
			"n": int64(1),
			"b": []map[string]any{
				{
					"n":    int64(2),
					"c":    []map[string]any{{"n": int64(3)}, {"n": int64(4)}},
					"meta": map[string]any{"flag": true},
				},
				{"n": int64(5)},
			},
		},
		{"n": int64(6)},
	}
	if !reflect.DeepEqual(values["a"], want) {
		t.Fatalf("a = %#v, want %#v", values["a"], want)
	}
}

// TestDecodeTOMLInlineTablesInsideAnArray pins the shape an array of inline
// tables decodes into: a []any of map[string]any, not the []map[string]any an
// array-of-tables header produces, because a caller's type assertion tells the
// two apart. A dotted key inside such an inline table nests like any other.
func TestDecodeTOMLInlineTablesInsideAnArray(t *testing.T) {
	t.Parallel()
	values, err := DecodeTOML([]byte("rows = [{a = 1}, {b.c = 2}]\n"))
	if err != nil {
		t.Fatalf("DecodeTOML: %v", err)
	}
	want := []any{
		map[string]any{"a": int64(1)},
		map[string]any{"b": map[string]any{"c": int64(2)}},
	}
	if !reflect.DeepEqual(values["rows"], want) {
		t.Fatalf("rows = %#v, want %#v", values["rows"], want)
	}
}

// TestDecodeTOMLLocalTimeShape pins the remaining date-time flavors the shapes
// comment names: a local date-time and a local time are read in the machine's
// zone, while an offset date-time keeps the offset it was written with.
func TestDecodeTOMLLocalTimeShape(t *testing.T) {
	t.Parallel()
	values, err := DecodeTOML([]byte(
		"stamp = 1979-05-27T07:32:00.5\nclock = 07:32:00\n"))
	if err != nil {
		t.Fatalf("DecodeTOML: %v", err)
	}
	wantStamp := time.Date(1979, time.May, 27, 7, 32, 0, 500000000, time.Local)
	if !reflect.DeepEqual(values["stamp"], wantStamp) {
		t.Fatalf("stamp = %#v, want %#v", values["stamp"], wantStamp)
	}
	wantClock := time.Date(0, time.January, 1, 7, 32, 0, 0, time.Local)
	if !reflect.DeepEqual(values["clock"], wantClock) {
		t.Fatalf("clock = %#v, want %#v", values["clock"], wantClock)
	}
}
