# table-endpoint directive for REST API documentation

Implement a `table-endpoint` directive that renders HTTP endpoint documentation from structured route metadata. This would auto-generate endpoint reference pages showing paths, methods, parameters, request/response models.

## Context

- wesktop (ASGI framework) has a planned route metadata API (see wesktop/todo/route-metadata-api.md) that would expose endpoint structure programmatically.
- selfdoc already auto-generates module/function/class reference docs via `ref` and `table-schema` directives. `table-endpoint` would complete the picture for web APIs.

## Data source options

1. **wesktop route metadata API**: Read structured dicts from wesktop's router. Requires wesktop to implement get_routes() or similar.
2. **OpenAPI spec**: Read /openapi.json. Standard format, works with any framework. Requires the app to generate OpenAPI.
3. **Static analysis**: Parse Python route decorators via AST. No runtime dependency. Less accurate for dynamic routes.

## Output format

Each endpoint renders as a section with: method badge, path, path parameters (name, type), query parameters (name, type, constraints), request body model fields, response model fields, description.
