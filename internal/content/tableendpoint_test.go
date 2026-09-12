package content

import (
	"path/filepath"
	"strings"
	"testing"
)

// sampleOpenAPI is the specification the rendering tests read: two collection
// operations, two item operations, a health check, and component schemas
// reached through $ref.
const sampleOpenAPI = `{
  "openapi": "3.0.3",
  "info": {"title": "Sample API", "version": "1.0.0"},
  "paths": {
    "/users": {
      "get": {
        "summary": "List all users",
        "parameters": [
          {"name": "limit", "in": "query", "required": false,
           "schema": {"type": "integer"},
           "description": "Maximum number of users to return"},
          {"name": "offset", "in": "query", "required": false,
           "schema": {"type": "integer"}, "description": "Pagination offset"}
        ],
        "responses": {
          "200": {"description": "Successful response",
            "content": {"application/json": {"schema": {
              "type": "object",
              "properties": {
                "items": {"type": "array",
                          "items": {"$ref": "#/components/schemas/User"},
                          "description": "List of users"},
                "total": {"type": "integer", "description": "Total count"}
              }}}}}
        }
      },
      "post": {
        "summary": "Create a new user",
        "requestBody": {"content": {"application/json": {
          "schema": {"$ref": "#/components/schemas/CreateUser"}}}},
        "responses": {
          "201": {"description": "User created",
            "content": {"application/json": {
              "schema": {"$ref": "#/components/schemas/User"}}}}
        }
      }
    },
    "/users/{id}": {
      "get": {
        "summary": "Get a user by ID",
        "description": "Retrieves a single user by their unique identifier.",
        "parameters": [
          {"name": "id", "in": "path", "required": true,
           "schema": {"type": "string"}, "description": "User identifier"}
        ],
        "responses": {
          "200": {"description": "Successful response",
            "content": {"application/json": {
              "schema": {"$ref": "#/components/schemas/User"}}}}
        }
      },
      "delete": {
        "summary": "Delete a user",
        "parameters": [
          {"name": "id", "in": "path", "required": true,
           "schema": {"type": "string"}, "description": "User identifier"}
        ],
        "responses": {"204": {"description": "User deleted"}}
      }
    },
    "/health": {
      "get": {
        "summary": "Health check",
        "responses": {
          "200": {"description": "OK",
            "content": {"application/json": {"schema": {
              "type": "object",
              "properties": {"status": {"type": "string",
                                        "description": "Service status"}}}}}}
        }
      }
    }
  },
  "components": {
    "schemas": {
      "User": {
        "type": "object",
        "required": ["id", "email"],
        "properties": {
          "email": {"type": "string", "description": "Email address"},
          "id": {"type": "string", "description": "Unique identifier"},
          "name": {"type": "string", "description": "Display name"}
        }
      },
      "CreateUser": {
        "type": "object",
        "required": ["email"],
        "properties": {
          "email": {"type": "string", "description": "Email address"},
          "name": {"type": "string", "description": "Display name"}
        }
      }
    }
  }
}`

// composedOpenAPI composes its response schema with allOf and declares an
// array of scalars.
const composedOpenAPI = `{
  "openapi": "3.0.3",
  "info": {"title": "Composed API", "version": "1.0.0"},
  "paths": {
    "/items": {
      "post": {
        "summary": "Create item",
        "requestBody": {"content": {"application/json": {
          "schema": {"$ref": "#/components/schemas/NewItem"}}}},
        "responses": {
          "201": {"description": "Created",
            "content": {"application/json": {
              "schema": {"$ref": "#/components/schemas/Item"}}}}
        }
      }
    }
  },
  "components": {
    "schemas": {
      "BaseItem": {"type": "object", "required": ["name"],
        "properties": {"name": {"type": "string", "description": "Item name"}}},
      "NewItem": {"type": "object", "required": ["name"],
        "properties": {
          "name": {"type": "string", "description": "Item name"},
          "tags": {"type": "array", "items": {"type": "string"},
                   "description": "Tags"}}},
      "Item": {"allOf": [
        {"$ref": "#/components/schemas/BaseItem"},
        {"type": "object", "required": ["id"],
         "properties": {"id": {"type": "string", "description": "Unique ID"}}}
      ]}
    }
  }
}`

// unionOpenAPI declares a property with oneOf alternatives.
const unionOpenAPI = `{
  "openapi": "3.0.3",
  "info": {"title": "Union API", "version": "1.0.0"},
  "paths": {
    "/events": {
      "get": {
        "summary": "List events",
        "responses": {
          "200": {"description": "OK",
            "content": {"application/json": {"schema": {
              "type": "object",
              "properties": {"payload": {
                "oneOf": [{"type": "string"}, {"type": "integer"}],
                "description": "Event payload"}}}}}}
        }
      }
    }
  }
}`

// specDir writes one specification and returns the directory holding it.
func specDir(t *testing.T, filename, spec string) string {
	t.Helper()
	base := t.TempDir()
	write(t, filepath.Join(base, filename), spec)
	return base
}

// endpoint renders the table-endpoint directive, failing on any error.
func endpoint(t *testing.T, base string, attrs map[string]string) string {
	t.Helper()
	rendered, err := ResolveTableEndpoint(attrs, base)
	if err != nil {
		t.Fatalf("ResolveTableEndpoint: %v", err)
	}
	return rendered
}

func TestTableEndpointRendering(t *testing.T) {
	isolate(t)
	base := specDir(t, "openapi.json", sampleOpenAPI)
	rendered := endpoint(t, base, map[string]string{"path": "openapi.json"})

	wants(t, rendered,
		"### `GET /health`", "Health check",
		"### `POST /users`", "Create a new user",
		"**Path Parameters**",
		"| `id` | string | yes | User identifier |",
		"**Query Parameters**",
		"| `limit` | integer | no | Maximum number of users to return |",
		"| `offset` | integer | no | Pagination offset |",
		"**Request Body**",
		"| `email` | string | yes | Email address |",
		"| `name` | string | no | Display name |",
		"**Response 200**", "**Response 201**",
		"Retrieves a single user by their unique identifier.",
	)
	// A response with no content has no table to render.
	rejects(t, rendered, "**Response 204**")
}

func TestTableEndpointOrdersByPathThenMethod(t *testing.T) {
	isolate(t)
	base := specDir(t, "openapi.json", sampleOpenAPI)
	rendered := endpoint(t, base, map[string]string{"path": "openapi.json"})

	var headings []string
	for _, line := range strings.Split(rendered, "\n") {
		if strings.HasPrefix(line, "### `") {
			headings = append(headings, line)
		}
	}
	want := []string{
		"### `GET /health`",
		"### `GET /users`",
		"### `POST /users`",
		"### `DELETE /users/{id}`",
		"### `GET /users/{id}`",
	}
	if strings.Join(headings, "\n") != strings.Join(want, "\n") {
		t.Fatalf("headings = %v, want %v", headings, want)
	}
}

func TestTableEndpointFiltering(t *testing.T) {
	isolate(t)
	base := specDir(t, "openapi.json", sampleOpenAPI)

	t.Run("by endpoint prefix", func(t *testing.T) {
		rendered := endpoint(t, base, map[string]string{
			"path": "openapi.json", "endpoint": "/users",
		})
		wants(t, rendered,
			"### `GET /users`", "### `POST /users`",
			"### `GET /users/{id}`", "### `DELETE /users/{id}`",
		)
		rejects(t, rendered, "/health")
	})

	t.Run("by method", func(t *testing.T) {
		rendered := endpoint(t, base, map[string]string{
			"path": "openapi.json", "method": "GET",
		})
		wants(t, rendered, "### `GET /health`", "### `GET /users`",
			"### `GET /users/{id}`")
		rejects(t, rendered, "### `POST", "### `DELETE")
	})

	t.Run("the method filter is case-insensitive", func(t *testing.T) {
		rendered := endpoint(t, base, map[string]string{
			"path": "openapi.json", "method": "get",
		})
		wants(t, rendered, "### `GET /health`")
	})

	t.Run("both filters at once", func(t *testing.T) {
		rendered := endpoint(t, base, map[string]string{
			"path": "openapi.json", "endpoint": "/users", "method": "post",
		})
		wants(t, rendered, "### `POST /users`")
		rejects(t, rendered, "### `GET", "/health")
	})

	t.Run("no matches", func(t *testing.T) {
		rendered := endpoint(t, base, map[string]string{
			"path": "openapi.json", "endpoint": "/nonexistent",
		})
		wants(t, rendered, "no matching endpoints")
	})
}

func TestTableEndpointResolvesRefs(t *testing.T) {
	isolate(t)

	t.Run("a response schema reached through a ref", func(t *testing.T) {
		base := specDir(t, "openapi.json", sampleOpenAPI)
		rendered := endpoint(t, base, map[string]string{
			"path": "openapi.json", "endpoint": "/users/{id}", "method": "get",
		})
		wants(t, rendered, "| `id` | string |", "| `email` | string |",
			"| `name` | string |")
	})

	t.Run("a request body reached through a ref", func(t *testing.T) {
		base := specDir(t, "openapi.json", sampleOpenAPI)
		rendered := endpoint(t, base, map[string]string{
			"path": "openapi.json", "endpoint": "/users", "method": "post",
		})
		wants(t, rendered, "**Request Body**",
			"| `email` | string | yes | Email address |")
	})

	t.Run("allOf merges its members' properties", func(t *testing.T) {
		base := specDir(t, "api.json", composedOpenAPI)
		rendered := endpoint(t, base, map[string]string{"path": "api.json"})
		wants(t, rendered, "**Response 201**",
			"| `id` | string |", "| `name` | string |")
	})

	t.Run("oneOf renders as a union type", func(t *testing.T) {
		base := specDir(t, "events.json", unionOpenAPI)
		rendered := endpoint(t, base, map[string]string{"path": "events.json"})
		// The pipe is escaped, or it would end the table cell.
		wants(t, rendered, `string \| integer`)
	})
}

func TestTableEndpointTypes(t *testing.T) {
	isolate(t)

	t.Run("an array of objects", func(t *testing.T) {
		base := specDir(t, "openapi.json", sampleOpenAPI)
		rendered := endpoint(t, base, map[string]string{
			"path": "openapi.json", "endpoint": "/users", "method": "get",
		})
		wants(t, rendered, "array[object]")
	})

	t.Run("an array of scalars", func(t *testing.T) {
		base := specDir(t, "api.json", composedOpenAPI)
		rendered := endpoint(t, base, map[string]string{
			"path": "api.json", "endpoint": "/items", "method": "post",
		})
		wants(t, rendered, "array[string]")
	})

	t.Run("a scalar", func(t *testing.T) {
		base := specDir(t, "openapi.json", sampleOpenAPI)
		rendered := endpoint(t, base, map[string]string{
			"path": "openapi.json", "endpoint": "/health",
		})
		wants(t, rendered, "| `status` | string |")
	})
}

func TestTableEndpointPrefersJSONThenTheFirstMediaType(t *testing.T) {
	// A specification that declares no application/json is documented from
	// the media type it declares FIRST, so the page reports the document
	// rather than whichever entry a map happened to yield.
	isolate(t)
	base := specDir(t, "xml.json", `{
	  "openapi": "3.0.3", "info": {"title": "X", "version": "1.0.0"},
	  "paths": {"/items": {"post": {"summary": "Create",
	    "requestBody": {"content": {
	      "application/xml": {"schema": {"type": "object",
	        "properties": {"first": {"type": "string", "description": "From XML"}}}},
	      "text/plain": {"schema": {"type": "object",
	        "properties": {"second": {"type": "string", "description": "From text"}}}}
	    }},
	    "responses": {}}}}
	}`)
	rendered := endpoint(t, base, map[string]string{"path": "xml.json"})
	wants(t, rendered, "| `first` | string | no | From XML |")
	rejects(t, rendered, "From text")
}

func TestTableEndpointErrors(t *testing.T) {
	isolate(t)

	t.Run("a missing file", func(t *testing.T) {
		rendered := endpoint(t, t.TempDir(), map[string]string{"path": "nonexistent.json"})
		wants(t, rendered, "> *[selfdoc:", "not found")
	})

	t.Run("a malformed document", func(t *testing.T) {
		base := specDir(t, "bad.json", "{ not valid json }")
		rendered := endpoint(t, base, map[string]string{"path": "bad.json"})
		wants(t, rendered, "> *[selfdoc:", "invalid JSON")
	})

	t.Run("an empty paths object", func(t *testing.T) {
		base := specDir(t, "empty.json",
			`{"openapi": "3.0.0", "info": {"title": "Empty", "version": "1.0.0"}, "paths": {}}`)
		wants(t, endpoint(t, base, map[string]string{"path": "empty.json"}),
			"no paths found")
	})

	t.Run("no paths key at all", func(t *testing.T) {
		base := specDir(t, "nopaths.json",
			`{"openapi": "3.0.0", "info": {"title": "NoPaths", "version": "1.0.0"}}`)
		wants(t, endpoint(t, base, map[string]string{"path": "nopaths.json"}),
			"no paths found")
	})

	t.Run("a missing path attribute", func(t *testing.T) {
		wants(t, endpoint(t, t.TempDir(), nil), "requires a path")
	})
}

func TestTableEndpointDispatch(t *testing.T) {
	isolate(t)
	base := specDir(t, "openapi.json", sampleOpenAPI)
	rendered, ok := resolve(t, "table-endpoint",
		map[string]string{"path": "openapi.json"}, nil, base, nil)
	if !ok {
		t.Fatal("table-endpoint is a content directive")
	}
	wants(t, rendered, "### `GET /health`")
}
