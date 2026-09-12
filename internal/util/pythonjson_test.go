package util

import "testing"

// TestPythonJSON compares the encoder against the bytes
// json.dumps(obj, sort_keys=True, separators=(",", ":")) produced for the same
// value. Every want below was captured from a python3 run.
func TestPythonJSON(t *testing.T) {
	t.Parallel()
	tests := []struct {
		name  string
		value any
		want  string
	}{
		{"nil", nil, "null"},
		{"bool true", true, "true"},
		{"bool false", false, "false"},
		{"int", 42, "42"},
		{"negative int", -7, "-7"},
		{"string", "hello", `"hello"`},
		{"empty object", map[string]any{}, "{}"},
		{"empty array", []any{}, "[]"},
		{"nil slice is the empty array", []string(nil), "[]"},
		{"nil map is the empty object", map[string]any(nil), "{}"},
		{
			"keys sorted by code point",
			map[string]any{"b": 1, "a": 2, "C": 3, "_": 4},
			`{"C":3,"_":4,"a":2,"b":1}`,
		},
		{
			"nested",
			map[string]any{"outer": map[string]any{"z": []any{1, 2, map[string]any{"k": "v"}}, "a": nil}},
			`{"outer":{"a":null,"z":[1,2,{"k":"v"}]}}`,
		},
		{
			"quote and backslash",
			map[string]any{"k": `a"b\c`},
			`{"k":"a\"b\\c"}`,
		},
		{
			"control characters",
			map[string]any{"k": "\b\f\n\r\t\x00\x1f\x7f"},
			`{"k":"\b\f\n\r\t\u0000\u001f\u007f"}`,
		},
		{
			"html characters are not escaped",
			map[string]any{"k": `<a href="x">&amp;</a>`},
			`{"k":"<a href=\"x\">&amp;</a>"}`,
		},
		{
			"non-ascii in the basic multilingual plane",
			map[string]any{"k": "café 中文 —"},
			`{"k":"caf\u00e9 \u4e2d\u6587 \u2014"}`,
		},
		{
			"astral plane becomes a surrogate pair",
			map[string]any{"k": "\U0001F600 \U0001F4A9"},
			`{"k":"\ud83d\ude00 \ud83d\udca9"}`,
		},
		{"float integral", 1.0, "1.0"},
		{"float simple", 0.5, "0.5"},
		{"float long", 123.456, "123.456"},
		{"float at the fixed-notation lower edge", 0.0001, "0.0001"},
		{"float past the fixed-notation lower edge", 0.00001, "1e-05"},
		{"float at the fixed-notation upper edge", 1e15, "1000000000000000.0"},
		{"float past the fixed-notation upper edge", 1e16, "1e+16"},
		{"float with a three-digit exponent", 1e300, "1e+300"},
		{"float negative", -2.5, "-2.5"},
		{"float repeating", 0.1, "0.1"},
		{"float one third", 1.0 / 3.0, "0.3333333333333333"},
		{"float negative zero", math0(), "-0.0"},
		{"float sixteen digits", 1234567890123456.0, "1234567890123456.0"},
		{"float list", []any{1.0, 2.5, 1e22, 1e-7}, "[1.0,2.5,1e+22,1e-07]"},
		{
			"unicode keys sort by code point",
			map[string]any{"é": 1, "z": 2, "a": 3},
			`{"a":3,"z":2,"\u00e9":1}`,
		},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			t.Parallel()
			got, err := PythonJSON(tt.value)
			if err != nil {
				t.Fatalf("PythonJSON: %v", err)
			}
			if string(got) != tt.want {
				t.Errorf("PythonJSON = %s, want %s", got, tt.want)
			}
		})
	}
}

// math0 returns negative zero without a constant expression, which Go folds to
// a positive zero.
func math0() float64 {
	zero := 0.0
	return -zero
}

// TestPythonJSONIndent2 compares the indented encoder against the bytes
// json.dumps(obj, indent=2, sort_keys=True) produced for the same value.
func TestPythonJSONIndent2(t *testing.T) {
	t.Parallel()
	tests := []struct {
		name  string
		value any
		want  string
	}{
		{"empty object", map[string]any{}, "{}"},
		{"empty array", []any{}, "[]"},
		{"scalar", 5, "5"},
		{
			"flat",
			map[string]any{"b": 1, "a": "x"},
			"{\n  \"a\": \"x\",\n  \"b\": 1\n}",
		},
		{
			"nested with empty collections",
			map[string]any{
				"outer": map[string]any{"z": []any{1, 2, map[string]any{"k": "v"}}, "a": nil},
				"list":  []any{},
				"obj":   map[string]any{},
			},
			"{\n  \"list\": [],\n  \"obj\": {},\n  \"outer\": {\n    \"a\": null,\n" +
				"    \"z\": [\n      1,\n      2,\n      {\n        \"k\": \"v\"\n      }\n    ]\n  }\n}",
		},
		{
			"non-ascii",
			map[string]any{"k": "café"},
			"{\n  \"k\": \"caf\\u00e9\"\n}",
		},
		{
			"floats",
			map[string]any{"f": 1.0, "g": 1e16},
			"{\n  \"f\": 1.0,\n  \"g\": 1e+16\n}",
		},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			t.Parallel()
			got, err := PythonJSONIndent2(tt.value)
			if err != nil {
				t.Fatalf("PythonJSONIndent2: %v", err)
			}
			if string(got) != tt.want {
				t.Errorf("PythonJSONIndent2 =\n%s\nwant\n%s", got, tt.want)
			}
		})
	}
}

func TestPythonJSONRejectsNonStringKeys(t *testing.T) {
	t.Parallel()
	if _, err := PythonJSON(map[int]string{1: "a"}); err == nil {
		t.Error("PythonJSON accepted an integer-keyed map")
	}
}

func TestPythonJSONRejectsUnsupportedKinds(t *testing.T) {
	t.Parallel()
	if _, err := PythonJSON(struct{ A int }{1}); err == nil {
		t.Error("PythonJSON accepted a struct")
	}
}

func TestPythonFloatReprSpecials(t *testing.T) {
	t.Parallel()
	tests := []struct {
		name string
		in   float64
		want string
	}{
		{"nan", nan(), "NaN"},
		{"positive infinity", inf(1), "Infinity"},
		{"negative infinity", inf(-1), "-Infinity"},
		{"zero", 0, "0.0"},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			t.Parallel()
			if got := PythonFloatRepr(tt.in); got != tt.want {
				t.Errorf("PythonFloatRepr = %q, want %q", got, tt.want)
			}
		})
	}
}

func nan() float64 { zero := 0.0; return zero / zero }
func inf(s int) float64 {
	zero, one := 0.0, 1.0
	if s < 0 {
		return -one / zero
	}
	return one / zero
}
