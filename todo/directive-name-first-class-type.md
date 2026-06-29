# DirectiveName as a first-class validated type

## Context

Directive names currently flow through the system as plain strings. The inline regex bug (see `inline-custom-directive-text-substitution.md`) exposed that nothing enforces a name grammar. The immediate fix (Solution 6: named constant + parse-time validation) is being implemented first. This todo captures Solution 10 — the most correct long-term approach — for later.

## Proposal

Make directive names a first-class concept in the type system via a `DirectiveName` class that validates on construction.

### What changes

- New `DirectiveName` class with `PATTERN = r'[a-zA-Z][\w-]*'` class variable
- `__init__` validates the name against the pattern, raises `ValueError` on mismatch
- `__str__`, `__eq__`, `__hash__` delegate to the underlying string for transparent use
- All 3 directive regexes (`_ONELINER_RE`, `_BLOCK_OPEN_RE`, `_INLINE_RE`) compose from `DirectiveName.PATTERN`
- `Directive.name` field type changes from `str` to `DirectiveName`
- Catalog dict keys (`catalog.py`) become `DirectiveName`, validated at import time
- Custom directive registration in `resolver.py` wraps config values in `DirectiveName()`, failing immediately on invalid names
- Tests constructing `Directive(name="foo")` need `DirectiveName("foo")` or a convenience helper

### Why this is better than Solution 6

Solution 6 validates at two points (config load + parse time) but internal code constructing `Directive` objects can still bypass validation. Solution 10 makes bad names structurally impossible — the type prevents them from propagating through the system at all.

### Why it was deferred

- Most invasive of all 10 solutions explored
- Touches catalog, resolver, Directive dataclass, and many tests
- Feels like Java-style type safety in Python — the team should be comfortable with the pattern before adopting it
- Solution 6 catches all real-world issues; Solution 10 is defense-in-depth

### Prerequisite

Solution 6 must be implemented first — it establishes the `_DIRECTIVE_NAME` constant and validation infrastructure that Solution 10 would promote to a type.

## Affected files

- `selfdoc/directives.py` — new `DirectiveName` class, regex composition, `Directive` dataclass
- `selfdoc/catalog.py` — dict keys become `DirectiveName`
- `selfdoc/resolver.py` — custom directive validation at registration
- `selfdoc/config.py` — custom directive names wrapped in `DirectiveName()`
- `tests/test_directives.py` — update `Directive` constructions
- `tests/test_catalog.py` — if exists, update key types
