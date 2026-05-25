"""Tests for the table-endpoint content directive."""

import json
import os

import pytest

from selfdoc.content import resolve_content, resolve_table_endpoint


# -- Fixtures -----------------------------------------------------------------


SAMPLE_OPENAPI_SPEC = {
    "openapi": "3.0.3",
    "info": {"title": "Sample API", "version": "1.0.0"},
    "paths": {
        "/users": {
            "get": {
                "summary": "List all users",
                "parameters": [
                    {
                        "name": "limit",
                        "in": "query",
                        "required": False,
                        "schema": {"type": "integer"},
                        "description": "Maximum number of users to return",
                    },
                    {
                        "name": "offset",
                        "in": "query",
                        "required": False,
                        "schema": {"type": "integer"},
                        "description": "Pagination offset",
                    },
                ],
                "responses": {
                    "200": {
                        "description": "Successful response",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "items": {
                                            "type": "array",
                                            "items": {"$ref": "#/components/schemas/User"},
                                            "description": "List of users",
                                        },
                                        "total": {
                                            "type": "integer",
                                            "description": "Total count",
                                        },
                                    },
                                }
                            }
                        },
                    }
                },
            },
            "post": {
                "summary": "Create a new user",
                "requestBody": {
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/CreateUser"}
                        }
                    }
                },
                "responses": {
                    "201": {
                        "description": "User created",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/User"}
                            }
                        },
                    }
                },
            },
        },
        "/users/{id}": {
            "get": {
                "summary": "Get a user by ID",
                "description": "Retrieves a single user by their unique identifier.",
                "parameters": [
                    {
                        "name": "id",
                        "in": "path",
                        "required": True,
                        "schema": {"type": "string"},
                        "description": "User identifier",
                    }
                ],
                "responses": {
                    "200": {
                        "description": "Successful response",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/User"}
                            }
                        },
                    }
                },
            },
            "delete": {
                "summary": "Delete a user",
                "parameters": [
                    {
                        "name": "id",
                        "in": "path",
                        "required": True,
                        "schema": {"type": "string"},
                        "description": "User identifier",
                    }
                ],
                "responses": {
                    "204": {"description": "User deleted"},
                },
            },
        },
        "/health": {
            "get": {
                "summary": "Health check",
                "responses": {
                    "200": {
                        "description": "OK",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "status": {
                                            "type": "string",
                                            "description": "Service status",
                                        }
                                    },
                                }
                            }
                        },
                    }
                },
            }
        },
    },
    "components": {
        "schemas": {
            "User": {
                "type": "object",
                "required": ["id", "email"],
                "properties": {
                    "email": {"type": "string", "description": "Email address"},
                    "id": {"type": "string", "description": "Unique identifier"},
                    "name": {"type": "string", "description": "Display name"},
                },
            },
            "CreateUser": {
                "type": "object",
                "required": ["email"],
                "properties": {
                    "email": {"type": "string", "description": "Email address"},
                    "name": {"type": "string", "description": "Display name"},
                },
            },
        }
    },
}


@pytest.fixture()
def openapi_dir(tmp_path):
    """Create a directory with a sample OpenAPI spec."""
    spec_file = tmp_path / "openapi.json"
    spec_file.write_text(json.dumps(SAMPLE_OPENAPI_SPEC, indent=2))
    return tmp_path


@pytest.fixture()
def allof_spec_dir(tmp_path):
    """Create a spec using allOf for schema composition."""
    spec = {
        "openapi": "3.0.3",
        "info": {"title": "Composed API", "version": "1.0.0"},
        "paths": {
            "/items": {
                "post": {
                    "summary": "Create item",
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/NewItem"}
                            }
                        }
                    },
                    "responses": {
                        "201": {
                            "description": "Created",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/Item"}
                                }
                            },
                        }
                    },
                }
            }
        },
        "components": {
            "schemas": {
                "BaseItem": {
                    "type": "object",
                    "required": ["name"],
                    "properties": {
                        "name": {"type": "string", "description": "Item name"},
                    },
                },
                "NewItem": {
                    "type": "object",
                    "required": ["name"],
                    "properties": {
                        "name": {"type": "string", "description": "Item name"},
                        "tags": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Tags",
                        },
                    },
                },
                "Item": {
                    "allOf": [
                        {"$ref": "#/components/schemas/BaseItem"},
                        {
                            "type": "object",
                            "required": ["id"],
                            "properties": {
                                "id": {"type": "string", "description": "Unique ID"},
                            },
                        },
                    ]
                },
            }
        },
    }
    (tmp_path / "api.json").write_text(json.dumps(spec, indent=2))
    return tmp_path


@pytest.fixture()
def oneof_spec_dir(tmp_path):
    """Create a spec using oneOf/anyOf."""
    spec = {
        "openapi": "3.0.3",
        "info": {"title": "Union API", "version": "1.0.0"},
        "paths": {
            "/events": {
                "get": {
                    "summary": "List events",
                    "responses": {
                        "200": {
                            "description": "OK",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "payload": {
                                                "oneOf": [
                                                    {"type": "string"},
                                                    {"type": "integer"},
                                                ],
                                                "description": "Event payload",
                                            }
                                        },
                                    }
                                }
                            },
                        }
                    },
                }
            }
        },
    }
    (tmp_path / "events.json").write_text(json.dumps(spec, indent=2))
    return tmp_path


# -- Basic rendering tests ----------------------------------------------------


class TestBasicRendering:
    """Tests for basic endpoint rendering."""

    def test_renders_get_endpoint(self, openapi_dir):
        result = resolve_table_endpoint(
            {"path": "openapi.json"}, str(openapi_dir)
        )
        assert "### `GET /health`" in result
        assert "Health check" in result

    def test_renders_post_endpoint(self, openapi_dir):
        result = resolve_table_endpoint(
            {"path": "openapi.json"}, str(openapi_dir)
        )
        assert "### `POST /users`" in result
        assert "Create a new user" in result

    def test_renders_path_parameters(self, openapi_dir):
        result = resolve_table_endpoint(
            {"path": "openapi.json"}, str(openapi_dir)
        )
        assert "**Path Parameters**" in result
        assert "| `id` | string | yes | User identifier |" in result

    def test_renders_query_parameters(self, openapi_dir):
        result = resolve_table_endpoint(
            {"path": "openapi.json"}, str(openapi_dir)
        )
        assert "**Query Parameters**" in result
        assert "| `limit` | integer | no | Maximum number of users to return |" in result
        assert "| `offset` | integer | no | Pagination offset |" in result

    def test_renders_request_body(self, openapi_dir):
        result = resolve_table_endpoint(
            {"path": "openapi.json"}, str(openapi_dir)
        )
        assert "**Request Body**" in result
        assert "| `email` | string | yes | Email address |" in result
        assert "| `name` | string | no | Display name |" in result

    def test_renders_response(self, openapi_dir):
        result = resolve_table_endpoint(
            {"path": "openapi.json"}, str(openapi_dir)
        )
        assert "**Response 200**" in result
        assert "**Response 201**" in result

    def test_renders_description(self, openapi_dir):
        result = resolve_table_endpoint(
            {"path": "openapi.json"}, str(openapi_dir)
        )
        assert "Retrieves a single user by their unique identifier." in result

    def test_skips_empty_response(self, openapi_dir):
        """Responses without content (like 204) should not render a table."""
        result = resolve_table_endpoint(
            {"path": "openapi.json"}, str(openapi_dir)
        )
        assert "**Response 204**" not in result


# -- Filtering tests ----------------------------------------------------------


class TestFiltering:
    """Tests for endpoint and method filtering."""

    def test_filter_by_endpoint_prefix(self, openapi_dir):
        result = resolve_table_endpoint(
            {"path": "openapi.json", "endpoint": "/users"}, str(openapi_dir)
        )
        assert "### `GET /users`" in result
        assert "### `POST /users`" in result
        assert "### `GET /users/{id}`" in result
        assert "### `DELETE /users/{id}`" in result
        # Should NOT include /health
        assert "/health" not in result

    def test_filter_by_method(self, openapi_dir):
        result = resolve_table_endpoint(
            {"path": "openapi.json", "method": "GET"}, str(openapi_dir)
        )
        assert "### `GET /health`" in result
        assert "### `GET /users`" in result
        assert "### `GET /users/{id}`" in result
        # Should NOT include POST or DELETE
        assert "### `POST" not in result
        assert "### `DELETE" not in result

    def test_filter_method_case_insensitive(self, openapi_dir):
        result = resolve_table_endpoint(
            {"path": "openapi.json", "method": "get"}, str(openapi_dir)
        )
        assert "### `GET /health`" in result

    def test_filter_combined(self, openapi_dir):
        result = resolve_table_endpoint(
            {"path": "openapi.json", "endpoint": "/users", "method": "post"},
            str(openapi_dir),
        )
        assert "### `POST /users`" in result
        assert "### `GET" not in result
        assert "/health" not in result

    def test_filter_no_matches(self, openapi_dir):
        result = resolve_table_endpoint(
            {"path": "openapi.json", "endpoint": "/nonexistent"},
            str(openapi_dir),
        )
        assert "no matching endpoints" in result


# -- $ref resolution tests ----------------------------------------------------


class TestRefResolution:
    """Tests for $ref resolution within the same file."""

    def test_resolves_schema_ref(self, openapi_dir):
        """Response schema via $ref should render resolved properties."""
        result = resolve_table_endpoint(
            {"path": "openapi.json", "endpoint": "/users/{id}", "method": "get"},
            str(openapi_dir),
        )
        # User schema properties should be rendered
        assert "| `id` | string |" in result
        assert "| `email` | string |" in result
        assert "| `name` | string |" in result

    def test_resolves_request_body_ref(self, openapi_dir):
        """Request body schema via $ref should be resolved."""
        result = resolve_table_endpoint(
            {"path": "openapi.json", "endpoint": "/users", "method": "post"},
            str(openapi_dir),
        )
        assert "**Request Body**" in result
        assert "| `email` | string | yes | Email address |" in result

    def test_resolves_allof(self, allof_spec_dir):
        """allOf schemas should merge properties."""
        result = resolve_table_endpoint(
            {"path": "api.json"}, str(allof_spec_dir)
        )
        # Response uses Item which has allOf [BaseItem, {id}]
        assert "**Response 201**" in result
        assert "| `id` | string |" in result
        assert "| `name` | string |" in result

    def test_resolves_oneof(self, oneof_spec_dir):
        """oneOf schemas should render as union types."""
        result = resolve_table_endpoint(
            {"path": "events.json"}, str(oneof_spec_dir)
        )
        assert "string | integer" in result


# -- Error handling tests -----------------------------------------------------


class TestErrorHandling:
    """Tests for error conditions."""

    def test_missing_file(self, tmp_path):
        result = resolve_table_endpoint(
            {"path": "nonexistent.json"}, str(tmp_path)
        )
        assert "> *[selfdoc:" in result
        assert "not found" in result

    def test_invalid_json(self, tmp_path):
        bad_file = tmp_path / "bad.json"
        bad_file.write_text("{ not valid json }")
        result = resolve_table_endpoint(
            {"path": "bad.json"}, str(tmp_path)
        )
        assert "> *[selfdoc:" in result
        assert "invalid JSON" in result

    def test_empty_paths(self, tmp_path):
        spec = {"openapi": "3.0.0", "info": {"title": "Empty", "version": "1.0.0"}, "paths": {}}
        (tmp_path / "empty.json").write_text(json.dumps(spec))
        result = resolve_table_endpoint(
            {"path": "empty.json"}, str(tmp_path)
        )
        assert "no paths found" in result

    def test_missing_path_attr(self, tmp_path):
        result = resolve_table_endpoint({}, str(tmp_path))
        assert "requires a path" in result

    def test_no_paths_key(self, tmp_path):
        spec = {"openapi": "3.0.0", "info": {"title": "NoPaths", "version": "1.0.0"}}
        (tmp_path / "nopaths.json").write_text(json.dumps(spec))
        result = resolve_table_endpoint(
            {"path": "nopaths.json"}, str(tmp_path)
        )
        assert "no paths found" in result


# -- Schema type rendering tests ----------------------------------------------


class TestSchemaTypes:
    """Tests for type extraction from various schema patterns."""

    def test_array_type(self, openapi_dir):
        result = resolve_table_endpoint(
            {"path": "openapi.json", "endpoint": "/users", "method": "get"},
            str(openapi_dir),
        )
        # items field is array[object] (from $ref -> User)
        assert "array[object]" in result

    def test_nested_array_with_items(self, allof_spec_dir):
        result = resolve_table_endpoint(
            {"path": "api.json", "endpoint": "/items", "method": "post"},
            str(allof_spec_dir),
        )
        assert "array[string]" in result

    def test_simple_types(self, openapi_dir):
        result = resolve_table_endpoint(
            {"path": "openapi.json", "endpoint": "/health"},
            str(openapi_dir),
        )
        assert "| `status` | string |" in result


# -- Sorting tests ------------------------------------------------------------


class TestSorting:
    """Tests for endpoint ordering."""

    def test_sorted_by_path_then_method(self, openapi_dir):
        result = resolve_table_endpoint(
            {"path": "openapi.json"}, str(openapi_dir)
        )
        # Extract headings
        headings = [
            line for line in result.split("\n") if line.startswith("### `")
        ]
        # Should be sorted: /health GET, /users GET, /users POST, /users/{id} DELETE, /users/{id} GET
        assert headings[0] == "### `GET /health`"
        assert headings[1] == "### `GET /users`"
        assert headings[2] == "### `POST /users`"
        assert headings[3] == "### `DELETE /users/{id}`"
        assert headings[4] == "### `GET /users/{id}`"


# -- Dispatch tests -----------------------------------------------------------


class TestDispatch:
    """Tests for dispatch via resolve_content."""

    def test_dispatched_by_resolve_content(self, openapi_dir):
        result = resolve_content(
            "table-endpoint", {"path": "openapi.json"}, [], str(openapi_dir)
        )
        assert result is not None
        assert "### `GET /health`" in result

    def test_in_content_directives_set(self):
        from selfdoc.content import CONTENT_DIRECTIVES
        assert "table-endpoint" in CONTENT_DIRECTIVES


# -- Catalog tests ------------------------------------------------------------


class TestCatalog:
    """Tests for catalog registration."""

    def test_in_core_directives(self):
        from selfdoc.catalog import CORE_DIRECTIVES
        assert "table-endpoint" in CORE_DIRECTIVES

    def test_not_in_future_directives(self):
        from selfdoc.catalog import FUTURE_DIRECTIVES
        assert "table-endpoint" not in FUTURE_DIRECTIVES

    def test_spec_fields(self):
        from selfdoc.catalog import CORE_DIRECTIVES
        spec = CORE_DIRECTIVES["table-endpoint"]
        assert spec.category == "content"
        assert spec.required_attrs == ["path"]
        assert "endpoint" in spec.optional_attrs
        assert "method" in spec.optional_attrs
