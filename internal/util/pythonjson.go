package util

import (
	"bytes"
	"fmt"
	"math"
	"reflect"
	"sort"
	"strconv"
	"strings"
)

// PythonJSON encodes v the way Python's
// json.dumps(v, sort_keys=True, separators=(",", ":")) does, byte for byte.
//
// That exact spelling is the hash-store's schema-hash input, so a divergence
// here silently invalidates every stored hash. The reproduced rules are:
//
//   - No whitespace anywhere: "," between items, ":" between a key and its
//     value.
//   - Object keys sorted by code point. Only string keys are accepted, because
//     Python's sort_keys refuses a mixed-type key set.
//   - ensure_ascii: every character outside printable ASCII is escaped as
//     \uXXXX in lowercase hex, with a surrogate pair above the Basic
//     Multilingual Plane. "<", ">" and "&" are NOT escaped -- Python's encoder
//     does no HTML escaping, unlike Go's encoding/json.
//   - Floats render as Python's repr does: shortest round-trip digits, a
//     trailing ".0" on an integral value, and exponential notation only when
//     the decimal point sits at or below position -4 or above position 16.
//     Infinities and NaN render as Python's non-standard Infinity, -Infinity
//     and NaN literals, which json.dumps emits by default.
//
// A nil slice encodes as "[]" and a nil map as "{}" -- Python has no nil
// collection, so a Go port's unset slice stands for the empty list the Python
// it replaces would have built. Only a nil interface or nil pointer is "null".
func PythonJSON(v any) ([]byte, error) {
	var buf bytes.Buffer
	if err := encodePythonJSON(&buf, reflect.ValueOf(v), "", ""); err != nil {
		return nil, err
	}
	return buf.Bytes(), nil
}

// PythonJSONIndent2 encodes v the way Python's
// json.dumps(v, indent=2, sort_keys=True) does, byte for byte -- the spelling
// the hash store's own file is written with.
//
// Every rule of [PythonJSON] holds, except that an indent switches Python's
// separators to "," plus a newline and ": " between a key and its value. An
// empty object and an empty array still render as "{}" and "[]".
func PythonJSONIndent2(v any) ([]byte, error) {
	var buf bytes.Buffer
	if err := encodePythonJSON(&buf, reflect.ValueOf(v), "", "  "); err != nil {
		return nil, err
	}
	return buf.Bytes(), nil
}

// encodePythonJSON writes one value. indent is the current line's leading
// whitespace and step is the per-level increment ("" for the compact form).
func encodePythonJSON(buf *bytes.Buffer, v reflect.Value, indent, step string) error {
	if !v.IsValid() {
		buf.WriteString("null")
		return nil
	}
	switch v.Kind() {
	case reflect.Interface, reflect.Pointer:
		if v.IsNil() {
			buf.WriteString("null")
			return nil
		}
		return encodePythonJSON(buf, v.Elem(), indent, step)
	case reflect.Bool:
		if v.Bool() {
			buf.WriteString("true")
		} else {
			buf.WriteString("false")
		}
		return nil
	case reflect.String:
		buf.WriteString(PythonJSONString(v.String()))
		return nil
	case reflect.Int, reflect.Int8, reflect.Int16, reflect.Int32, reflect.Int64:
		buf.WriteString(strconv.FormatInt(v.Int(), 10))
		return nil
	case reflect.Uint, reflect.Uint8, reflect.Uint16, reflect.Uint32, reflect.Uint64:
		buf.WriteString(strconv.FormatUint(v.Uint(), 10))
		return nil
	case reflect.Float32, reflect.Float64:
		buf.WriteString(PythonFloatRepr(v.Float()))
		return nil
	case reflect.Slice, reflect.Array:
		return encodePythonList(buf, v, indent, step)
	case reflect.Map:
		return encodePythonMap(buf, v, indent, step)
	default:
		return fmt.Errorf("util: PythonJSON cannot encode %s", v.Type())
	}
}

func encodePythonList(buf *bytes.Buffer, v reflect.Value, indent, step string) error {
	n := v.Len()
	if n == 0 {
		buf.WriteString("[]")
		return nil
	}
	inner := indent + step
	buf.WriteByte('[')
	for i := 0; i < n; i++ {
		if i > 0 {
			buf.WriteByte(',')
		}
		if step != "" {
			buf.WriteByte('\n')
			buf.WriteString(inner)
		}
		if err := encodePythonJSON(buf, v.Index(i), inner, step); err != nil {
			return err
		}
	}
	if step != "" {
		buf.WriteByte('\n')
		buf.WriteString(indent)
	}
	buf.WriteByte(']')
	return nil
}

func encodePythonMap(buf *bytes.Buffer, v reflect.Value, indent, step string) error {
	if v.Type().Key().Kind() != reflect.String {
		return fmt.Errorf("util: PythonJSON requires string object keys, got %s", v.Type().Key())
	}
	keys := make([]string, 0, v.Len())
	for _, key := range v.MapKeys() {
		keys = append(keys, key.String())
	}
	if len(keys) == 0 {
		buf.WriteString("{}")
		return nil
	}
	// Python's sorted() on str keys compares by code point, which is the same
	// order as Go's byte-wise comparison of their UTF-8 encodings.
	sort.Strings(keys)

	inner := indent + step
	colon := ":"
	if step != "" {
		colon = ": "
	}
	buf.WriteByte('{')
	for i, key := range keys {
		if i > 0 {
			buf.WriteByte(',')
		}
		if step != "" {
			buf.WriteByte('\n')
			buf.WriteString(inner)
		}
		buf.WriteString(PythonJSONString(key))
		buf.WriteString(colon)
		value := v.MapIndex(reflect.ValueOf(key).Convert(v.Type().Key()))
		if err := encodePythonJSON(buf, value, inner, step); err != nil {
			return err
		}
	}
	if step != "" {
		buf.WriteByte('\n')
		buf.WriteString(indent)
	}
	buf.WriteByte('}')
	return nil
}

// PythonJSONString quotes s the way Python's json encoder does under
// ensure_ascii: the short escapes for backslash, quote, backspace, form feed,
// newline, carriage return and tab, a \uXXXX escape for every other character
// outside the printable ASCII range 0x20-0x7E, and a surrogate pair for a code
// point above the Basic Multilingual Plane.
func PythonJSONString(s string) string {
	var b strings.Builder
	b.Grow(len(s) + 2)
	b.WriteByte('"')
	for _, r := range s {
		switch r {
		case '\\':
			b.WriteString(`\\`)
		case '"':
			b.WriteString(`\"`)
		case '\b':
			b.WriteString(`\b`)
		case '\f':
			b.WriteString(`\f`)
		case '\n':
			b.WriteString(`\n`)
		case '\r':
			b.WriteString(`\r`)
		case '\t':
			b.WriteString(`\t`)
		default:
			switch {
			case r >= 0x20 && r <= 0x7E:
				b.WriteRune(r)
			case r < 0x10000:
				fmt.Fprintf(&b, `\u%04x`, r)
			default:
				// Python emits the UTF-16 surrogate pair.
				c := r - 0x10000
				fmt.Fprintf(&b, `\u%04x\u%04x`, 0xD800|((c>>10)&0x3FF), 0xDC00|(c&0x3FF))
			}
		}
	}
	b.WriteByte('"')
	return b.String()
}

// PythonFloatRepr renders f the way Python's repr(float) does, which is also
// what json.dumps writes for a float.
//
// The digits are the shortest decimal string that round-trips. Notation is
// chosen from the decimal point's position: exponential when it sits at or
// below -4 or above 16, fixed otherwise, and a fixed rendering always carries
// a fractional part (so 1.0 is "1.0", never "1"). Infinities and NaN render as
// json.dumps's non-standard Infinity, -Infinity and NaN literals.
func PythonFloatRepr(f float64) string {
	switch {
	case math.IsNaN(f):
		return "NaN"
	case math.IsInf(f, 1):
		return "Infinity"
	case math.IsInf(f, -1):
		return "-Infinity"
	}
	sign := ""
	if math.Signbit(f) {
		sign = "-"
		f = -f
	}
	// Shortest round-trip digits, read back out of the scientific form.
	sci := strconv.FormatFloat(f, 'e', -1, 64)
	e := strings.IndexByte(sci, 'e')
	mantissa, exponent := sci[:e], sci[e+1:]
	digits := strings.Replace(mantissa, ".", "", 1)
	exp, err := strconv.Atoi(exponent)
	if err != nil {
		// Unreachable for a finite float: FormatFloat's 'e' form always
		// carries a signed decimal exponent.
		return sign + sci
	}
	// decpt is the decimal point's position relative to the digit string:
	// the value is 0.<digits> * 10^decpt.
	decpt := exp + 1

	if decpt <= -4 || decpt > 16 {
		out := digits[:1]
		if len(digits) > 1 {
			out += "." + digits[1:]
		}
		expSign := "+"
		if decpt-1 < 0 {
			expSign = "-"
		}
		magnitude := decpt - 1
		if magnitude < 0 {
			magnitude = -magnitude
		}
		return fmt.Sprintf("%s%se%s%02d", sign, out, expSign, magnitude)
	}
	switch {
	case decpt <= 0:
		return sign + "0." + strings.Repeat("0", -decpt) + digits
	case decpt >= len(digits):
		return sign + digits + strings.Repeat("0", decpt-len(digits)) + ".0"
	default:
		return sign + digits[:decpt] + "." + digits[decpt:]
	}
}
