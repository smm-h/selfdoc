package identity

import (
	"errors"
	"reflect"
	"testing"
)

// declaredAuthor is the block the Python suite drove these cases with.
func declaredAuthor() map[string]any {
	return map[string]any{
		"name": "Jane Doe",
		"url":  "https://jane.example",
		"same_as": []any{
			"https://github.com/jane",
			"https://example.org/@jane",
		},
	}
}

// TestPersonEntity drives the builder with the documents the Python
// implementation was probed on; every property list below is the order and
// the values python3 emitted for the same input.
func TestPersonEntity(t *testing.T) {
	t.Parallel()
	tests := []struct {
		name        string
		author      map[string]any
		withContext bool
		extra       Entity
		want        Entity
	}{
		{
			name:   "the declared person, nested in another document",
			author: declaredAuthor(),
			want: Entity{
				{"@type", "Person"},
				{"name", "Jane Doe"},
				{"url", "https://jane.example"},
				{"sameAs", []string{"https://github.com/jane", "https://example.org/@jane"}},
			},
		},
		{
			name:        "as its own document, the context comes first",
			author:      declaredAuthor(),
			withContext: true,
			want: Entity{
				{"@context", "https://schema.org"},
				{"@type", "Person"},
				{"name", "Jane Doe"},
				{"url", "https://jane.example"},
				{"sameAs", []string{"https://github.com/jane", "https://example.org/@jane"}},
			},
		},
		{
			name:   "no same_as means no sameAs property",
			author: map[string]any{"name": "J", "url": "https://j.dev"},
			want: Entity{
				{"@type", "Person"},
				{"name", "J"},
				{"url", "https://j.dev"},
			},
		},
		{
			name: "a blank same_as entry is dropped",
			author: map[string]any{
				"name": "J", "url": "https://j.dev",
				"same_as": []any{"  ", "", "https://x"},
			},
			want: Entity{
				{"@type", "Person"},
				{"name", "J"},
				{"url", "https://j.dev"},
				{"sameAs", []string{"https://x"}},
			},
		},
		{
			name:   "extras append in order, empty ones are skipped, and a collision replaces in place",
			author: declaredAuthor(),
			extra: Entity{
				{"jobTitle", "Dev"},
				{"description", ""},
				{"alumniOf", []any{}},
				{"name", "Override"},
				{"address", map[string]any{"@type": "PostalAddress"}},
			},
			want: Entity{
				{"@type", "Person"},
				{"name", "Override"},
				{"url", "https://jane.example"},
				{"sameAs", []string{"https://github.com/jane", "https://example.org/@jane"}},
				{"jobTitle", "Dev"},
				{"address", map[string]any{"@type": "PostalAddress"}},
			},
		},
		{
			name:   "a same_as declared as a Go string slice reads the same",
			author: map[string]any{"name": "J", "url": "https://j.dev", "same_as": []string{"https://x"}},
			want: Entity{
				{"@type", "Person"},
				{"name", "J"},
				{"url", "https://j.dev"},
				{"sameAs", []string{"https://x"}},
			},
		},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			got, err := PersonEntity(tc.author, tc.withContext, tc.extra)
			if err != nil {
				t.Fatalf("PersonEntity: %v", err)
			}
			if !reflect.DeepEqual(got, tc.want) {
				t.Fatalf("entity =\n %#v\nwant\n %#v", got, tc.want)
			}
		})
	}
}

// TestPersonEntityRefusesAnUndeclaredAuthor covers every block the Python
// refused rather than inventing an entity for.
func TestPersonEntityRefusesAnUndeclaredAuthor(t *testing.T) {
	t.Parallel()
	tests := []struct {
		name   string
		author map[string]any
	}{
		{"no author at all", nil},
		{"an empty block", map[string]any{}},
		{"a name with no url", map[string]any{"name": "J"}},
		{"a url with no name", map[string]any{"url": "https://j.dev"}},
		{"an empty name", map[string]any{"name": "", "url": "https://j.dev"}},
		{"an empty url", map[string]any{"name": "J", "url": ""}},
	}
	for _, tc := range tests {
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			entity, err := PersonEntity(tc.author, false, nil)
			if !errors.Is(err, ErrNoDeclaredAuthor) {
				t.Fatalf("expected ErrNoDeclaredAuthor, got %v", err)
			}
			if entity != nil {
				t.Fatalf("expected no entity, got %#v", entity)
			}
		})
	}
}

// TestRefusalNamesTheConfigKeyAndNoOrganisation pins the refusal's wording:
// it has to say what to declare, and it must not offer an organisation as an
// alternative, because minting one is the defect the required block removed.
func TestRefusalNamesTheConfigKeyAndNoOrganisation(t *testing.T) {
	t.Parallel()
	want := "structured data needs the declared author, and this build has " +
		"none with both 'name' and 'url'. selfdoc.json requires " +
		`"author": {"name": ..., "url": ...}; there is no inferred ` +
		"author and no organisation is minted from the project name."
	if ErrNoDeclaredAuthor.Error() != want {
		t.Fatalf("refusal\n got: %s\nwant: %s", ErrNoDeclaredAuthor.Error(), want)
	}
}

func TestAuthorKeysMirrorTheConfigSchema(t *testing.T) {
	t.Parallel()
	if !reflect.DeepEqual(AuthorKeys, []string{"name", "url", "same_as"}) {
		t.Fatalf("AuthorKeys = %#v", AuthorKeys)
	}
}

func TestEntityAccessors(t *testing.T) {
	t.Parallel()
	entity := Entity{{"@type", "Person"}, {"name", "J"}}
	if value, ok := entity.Get("name"); !ok || value != "J" {
		t.Fatalf("Get(name) = %#v, %v", value, ok)
	}
	if _, ok := entity.Get("sameAs"); ok {
		t.Fatal("Get reported a property the entity does not carry")
	}
	entity.Set("url", "https://j.dev")
	entity.Set("name", "Jane")
	if !reflect.DeepEqual(entity.Keys(), []string{"@type", "name", "url"}) {
		t.Fatalf("Keys() = %#v", entity.Keys())
	}
	if value, _ := entity.Get("name"); value != "Jane" {
		t.Fatalf("Set did not replace in place: %#v", entity)
	}
}
