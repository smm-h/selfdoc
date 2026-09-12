package util

import (
	"fmt"
	"os"
	"strings"
	"time"

	tomledit "github.com/smm-h/go-toml-edit"
)

// DecodeTOML decodes a TOML document into the generic Go value every caller in
// this module validates by hand.
//
// The shapes are the ones the hand-written validations and their pinned
// refusals were written against: a string, an int64, a float64, a bool, a
// time.Time for each of the four date-time flavors, a []any for an array, a
// map[string]any for a table, a []map[string]any for an array of tables, and
// nested maps for a dotted key. A caller reads them with a type assertion and
// refuses anything else by name, so a shape stated here is part of every one
// of those refusals.
func DecodeTOML(data []byte) (map[string]any, error) {
	values, _, err := DecodeTOMLOrdered(data)
	return values, err
}

// DecodeTOMLFile reads path and decodes it through [DecodeTOML].
func DecodeTOMLFile(path string) (map[string]any, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	return DecodeTOML(data)
}

// DecodeTOMLOrdered decodes like [DecodeTOML] and additionally answers every
// key the document declares, as its path from the root, in document order.
//
// A Go map has no order, so a renderer whose row order is document order reads
// the order from here instead. The list carries a table header before the keys
// written under it, one entry per array-of-tables element, and the keys of an
// inline table under the key it is bound to -- a sequence a caller replays over
// the decoded values to rebuild the document's own order.
func DecodeTOMLOrdered(data []byte) (map[string]any, [][]string, error) {
	document, err := tomledit.Parse(data)
	if err != nil {
		return nil, nil, err
	}
	values, err := tomlValues(document)
	if err != nil {
		return nil, nil, err
	}
	return values, tomlKeyOrder(document), nil
}

// tomlValues walks the parsed document and builds the decoded value tree.
//
// The walk is this package's own rather than the parser's decoder, because the
// decoder drops an array of tables nested inside another one -- the shape a
// [[category]] block carrying [[category.project]] blocks is written in.
func tomlValues(document *tomledit.DocumentNode) (map[string]any, error) {
	root := map[string]any{}
	for _, child := range document.Children {
		switch node := child.(type) {
		case *tomledit.KeyValueNode:
			if err := setTOMLPair(root, nil, node); err != nil {
				return nil, err
			}
		case *tomledit.TableNode:
			table, err := descendTOMLTable(root, node.KeyPath)
			if err != nil {
				return nil, err
			}
			if err := fillTOMLTable(table, node.KeyPath, node.Children); err != nil {
				return nil, err
			}
		case *tomledit.ArrayTableNode:
			table, err := appendTOMLArrayTable(root, node.KeyPath)
			if err != nil {
				return nil, err
			}
			if err := fillTOMLTable(table, node.KeyPath, node.Children); err != nil {
				return nil, err
			}
		}
	}
	return root, nil
}

// fillTOMLTable writes a table header's body into the table it opened.
func fillTOMLTable(table map[string]any, path []string, children []tomledit.Node) error {
	for _, child := range children {
		if pair, ok := child.(*tomledit.KeyValueNode); ok {
			if err := setTOMLPair(table, path, pair); err != nil {
				return err
			}
		}
	}
	return nil
}

// setTOMLPair binds one key-value pair inside table, creating the intermediate
// tables a dotted key names.
func setTOMLPair(table map[string]any, prefix []string, pair *tomledit.KeyValueNode) error {
	parts := pair.Key.Parts
	target, err := descendTOMLTable(table, parts[:len(parts)-1])
	if err != nil {
		return tomlPathError(append(clonePath(prefix), parts...))
	}
	value, err := tomlValue(pair.Val)
	if err != nil {
		return err
	}
	target[parts[len(parts)-1]] = value
	return nil
}

// descendTOMLTable walks path from table, creating a table for a segment that
// names nothing yet and entering the last element of an array of tables for a
// segment that names one.
func descendTOMLTable(table map[string]any, path []string) (map[string]any, error) {
	current := table
	for index, segment := range path {
		switch existing := current[segment].(type) {
		case nil:
			created := map[string]any{}
			current[segment] = created
			current = created
		case map[string]any:
			current = existing
		case []map[string]any:
			if len(existing) == 0 {
				return nil, tomlPathError(path[:index+1])
			}
			current = existing[len(existing)-1]
		default:
			return nil, tomlPathError(path[:index+1])
		}
	}
	return current, nil
}

// appendTOMLArrayTable adds one element to the array of tables path names and
// answers it.
func appendTOMLArrayTable(root map[string]any, path []string) (map[string]any, error) {
	parent, err := descendTOMLTable(root, path[:len(path)-1])
	if err != nil {
		return nil, err
	}
	key := path[len(path)-1]
	element := map[string]any{}
	switch existing := parent[key].(type) {
	case nil:
		parent[key] = []map[string]any{element}
	case []map[string]any:
		parent[key] = append(existing, element)
	default:
		return nil, tomlPathError(path)
	}
	return element, nil
}

// tomlValue converts one value node into the Go value the callers read.
//
// The parser answers a local date, a local time and a local date-time as its
// own three structs; every consumer here -- the Python type names, the
// rendered config tables -- reads a date-time as a time.Time. A local flavor
// carries no zone and is read in the machine's zone, which is the reading a
// value written without one asks for.
func tomlValue(node tomledit.Node) (any, error) {
	switch typed := node.(type) {
	case *tomledit.StringNode:
		return typed.Val, nil
	case *tomledit.IntegerNode:
		return typed.Val, nil
	case *tomledit.FloatNode:
		return typed.Val, nil
	case *tomledit.BooleanNode:
		return typed.Val, nil
	case *tomledit.DateTimeNode:
		return typed.Val, nil
	case *tomledit.LocalDateTimeNode:
		return time.Date(
			typed.Val.Year, time.Month(typed.Val.Month), typed.Val.Day,
			typed.Val.Hour, typed.Val.Minute, typed.Val.Second,
			typed.Val.Nanosecond, time.Local,
		), nil
	case *tomledit.LocalDateNode:
		return time.Date(
			typed.Val.Year, time.Month(typed.Val.Month), typed.Val.Day,
			0, 0, 0, 0, time.Local,
		), nil
	case *tomledit.LocalTimeNode:
		return time.Date(
			0, time.January, 1,
			typed.Val.Hour, typed.Val.Minute, typed.Val.Second,
			typed.Val.Nanosecond, time.Local,
		), nil
	case *tomledit.ArrayNode:
		items := make([]any, 0, len(typed.Elements))
		for _, element := range typed.Elements {
			item, err := tomlValue(element)
			if err != nil {
				return nil, err
			}
			items = append(items, item)
		}
		return items, nil
	case *tomledit.InlineTableNode:
		table := map[string]any{}
		for _, child := range typed.Children {
			pair, ok := child.(*tomledit.KeyValueNode)
			if !ok {
				continue
			}
			if err := setTOMLPair(table, nil, pair); err != nil {
				return nil, err
			}
		}
		return table, nil
	default:
		return nil, fmt.Errorf("unsupported TOML value of kind %s", node.Type())
	}
}

// tomlPathError reports a key whose path runs through something that is not a
// table -- a document the parser accepted but whose keys contradict each other.
func tomlPathError(path []string) error {
	return fmt.Errorf("key %q is declared under a value that is not a table",
		strings.Join(path, "."))
}

// tomlKeyOrder lists every key the document declares, as its path from the
// root, in the order the document writes them.
func tomlKeyOrder(document *tomledit.DocumentNode) [][]string {
	var keys [][]string
	for _, child := range document.Children {
		switch node := child.(type) {
		case *tomledit.KeyValueNode:
			keys = appendTOMLKeys(keys, nil, node)
		case *tomledit.TableNode:
			keys = append(keys, clonePath(node.KeyPath))
			keys = appendTOMLTableKeys(keys, node.KeyPath, node.Children)
		case *tomledit.ArrayTableNode:
			keys = append(keys, clonePath(node.KeyPath))
			keys = appendTOMLTableKeys(keys, node.KeyPath, node.Children)
		}
	}
	return keys
}

// appendTOMLTableKeys appends the keys a table body declares, each under the
// path of the header it was written below.
func appendTOMLTableKeys(keys [][]string, prefix []string, children []tomledit.Node) [][]string {
	for _, child := range children {
		if pair, ok := child.(*tomledit.KeyValueNode); ok {
			keys = appendTOMLKeys(keys, prefix, pair)
		}
	}
	return keys
}

// appendTOMLKeys appends one key-value pair's own key, then the keys of the
// inline table it binds, if that is what it binds.
func appendTOMLKeys(keys [][]string, prefix []string, pair *tomledit.KeyValueNode) [][]string {
	path := append(clonePath(prefix), pair.Key.Parts...)
	keys = append(keys, path)
	if inline, ok := pair.Val.(*tomledit.InlineTableNode); ok {
		for _, child := range inline.Children {
			if nested, ok := child.(*tomledit.KeyValueNode); ok {
				keys = appendTOMLKeys(keys, path, nested)
			}
		}
	}
	return keys
}

// clonePath copies a key path, so an appended segment never writes into the
// AST's own slice or into a path already recorded.
func clonePath(path []string) []string {
	return append(make([]string, 0, len(path)), path...)
}
