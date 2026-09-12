// Package identity holds the site's declared author, as the one Person its
// structured data names.
//
// A selfdoc site has one author, declared in selfdoc.json under "author" and
// required there. Every emitter that needs an identity -- the per-page
// article's author and publisher, the front page's standalone entity, the CV
// page's profile -- reads it through this package, so a site states the same
// Person everywhere and states it once.
//
// What used to happen instead is why the block is required: with no author
// declared, the emitters minted {"@type": "Organization", "name":
// <project_name>}, inventing an organisation out of a directory name and
// publishing it as fact. That path is gone. A caller that reaches these
// functions without a declared author gets a refusal naming the config key.
package identity

import (
	"errors"
	"fmt"
	"strings"
)

// AuthorKeys is every key an "author" block may carry, mirroring the config
// schema.
var AuthorKeys = []string{"name", "url", "same_as"}

// ErrNoDeclaredAuthor is the refusal every entry point returns when the build
// has no author with both a name and a URL. It names the config key rather
// than falling back to anything: there is no inferred author.
var ErrNoDeclaredAuthor = errors.New(
	"structured data needs the declared author, and this build has " +
		"none with both 'name' and 'url'. selfdoc.json requires " +
		`"author": {"name": ..., "url": ...}; there is no inferred ` +
		"author and no organisation is minted from the project name.")

// Property is one property of a JSON-LD entity: its name and its value.
type Property struct {
	Key   string
	Value any
}

// Entity is a JSON-LD entity as an ordered property list.
//
// The order is part of the output, not an implementation detail: the emitted
// structured data is rendered by walking the entity, and a Person reads
// "@context" (when it stands as its own document), then "@type", "name",
// "url", "sameAs", then whatever the page contributed. A Go map carries no
// order, so the entity is a slice.
type Entity []Property

// Get returns the value of key and whether the entity carries it.
func (e Entity) Get(key string) (any, bool) {
	for _, property := range e {
		if property.Key == key {
			return property.Value, true
		}
	}
	return nil, false
}

// Set assigns key, replacing the value in place when the entity already
// carries that key and appending it at the end otherwise -- the behavior of
// assigning into a Python dict, which is what the callers of [PersonEntity]
// were written against.
func (e *Entity) Set(key string, value any) {
	for i := range *e {
		if (*e)[i].Key == key {
			(*e)[i].Value = value
			return
		}
	}
	*e = append(*e, Property{Key: key, Value: value})
}

// Keys returns the entity's property names in order.
func (e Entity) Keys() []string {
	keys := make([]string, len(e))
	for i, property := range e {
		keys[i] = property.Key
	}
	return keys
}

// PersonEntity returns the declared author as a schema.org Person.
//
// withContext adds "@context" for an entity emitted as its own JSON-LD
// document rather than nested inside one. extra carries the properties only a
// particular page knows -- a CV's occupation, languages and schools -- and is
// merged after the identity properties, each entry skipped when its value is
// empty. An extra whose key is one of the identity properties replaces that
// property where it already stands, so the property order does not change.
//
// It returns [ErrNoDeclaredAuthor] when no author is declared.
func PersonEntity(author map[string]any, withContext bool, extra Entity) (Entity, error) {
	declared, err := requireAuthor(author)
	if err != nil {
		return nil, err
	}
	var entity Entity
	if withContext {
		entity = append(entity, Property{Key: "@context", Value: "https://schema.org"})
	}
	entity = append(entity,
		Property{Key: "@type", Value: "Person"},
		Property{Key: "name", Value: declared["name"]},
		Property{Key: "url", Value: declared["url"]},
	)
	if sameAs := sameAsURLs(declared["same_as"]); len(sameAs) > 0 {
		entity = append(entity, Property{Key: "sameAs", Value: sameAs})
	}
	for _, property := range extra {
		if truthy(property.Value) {
			entity.Set(property.Key, property.Value)
		}
	}
	return entity, nil
}

// requireAuthor returns the author block, or the refusal naming what is
// missing.
func requireAuthor(author map[string]any) (map[string]any, error) {
	if author == nil || !truthy(author["name"]) || !truthy(author["url"]) {
		return nil, ErrNoDeclaredAuthor
	}
	return author, nil
}

// sameAsURLs renders a declared same_as list as the strings the Person's
// sameAs carries: every entry stringified, and an entry that is blank once
// trimmed dropped -- while a kept entry keeps its original spelling,
// untrimmed.
func sameAsURLs(declared any) []string {
	var entries []any
	switch typed := declared.(type) {
	case nil:
		return nil
	case []any:
		entries = typed
	case []string:
		for _, entry := range typed {
			entries = append(entries, entry)
		}
	default:
		entries = []any{declared}
	}
	var urls []string
	for _, entry := range entries {
		text := stringify(entry)
		if strings.TrimSpace(text) == "" {
			continue
		}
		urls = append(urls, text)
	}
	return urls
}

// stringify renders a value the way Python's str() would for the values a
// same_as list can hold.
func stringify(value any) string {
	if text, ok := value.(string); ok {
		return text
	}
	return fmt.Sprint(value)
}

// truthy reports whether value is truthy under Python's rules, which is what
// decides both whether an author block is declared and whether an extra
// property is carried: nil, false, zero, an empty string and an empty
// collection are all empty.
func truthy(value any) bool {
	switch typed := value.(type) {
	case nil:
		return false
	case bool:
		return typed
	case string:
		return typed != ""
	case int:
		return typed != 0
	case int64:
		return typed != 0
	case float64:
		return typed != 0
	case []any:
		return len(typed) > 0
	case []string:
		return len(typed) > 0
	case map[string]any:
		return len(typed) > 0
	case Entity:
		return len(typed) > 0
	default:
		return true
	}
}
