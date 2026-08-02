# Directive descriptors: custom-directive unification, build-time enforcement, discovery caching

Successor to `todo/.done/spec-driven-directive-descriptors.md`. Its realized slice
shipped: the built-in catalogue is a strictspec-governed declarative document with a
generated validator, and dispatch-freshness tests pin the dispatch table to the document.
Three parts were NOT realized and live on here.

## 1. Custom-directive descriptor unification

The custom-directive registration path (`config["directives"]` / register_directive) does
not produce the same descriptor shape as the built-in catalogue, so custom directives are
skipped by attribute enforcement (they have no spec to enforce against). Unify: custom
registration should construct the same descriptor object (name, attribute schema,
resolver, category, example, docs blurb) so enforcement, docs tables, and dispatch treat
custom and core directives identically.

## 2. Build-time enforcement

Only check/gen enforce directive attributes today; a bare `selfdoc build` resolves unknown
attributes silently. Enforcement should run wherever directives resolve.

## 3. Schema-discovery caching for table-commands

table-commands' unique-schema discovery walks the tree per resolution; cache it per build.

## Effort

Medium: (1) is a registration-path restructure, mechanical per directive once the shape
exists; (2) and (3) are small once (1) lands.
