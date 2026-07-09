# table-commands `path` semantics diverge from sibling directives (footgun)

## Context

Since commit `8bb81ce` ("fix table-commands: respect path attribute for monorepo sub-projects"), the `table-commands` directive joins its `path` attribute onto the project root and looks for `<root>/<path>/.strictcli/schema.json`. This made `path` mean "the directory that contains `.strictcli/`" — for standalone repos that is `path="."`.

The sibling directives `list-features` and `list-modules` use `path` to mean "the Python source directory" (e.g. `path="src/<pkg>/"`). Same attribute name, different contract.

## Problem

A consumer project naturally wrote `table-commands path="src/<pkg>/"` to match its other directives. The result: `read_schema_json` looks for `src/<pkg>/.strictcli/schema.json`, finds nothing, and the directive fails with `no strictcli app found in 'src/<pkg>/'`. Worse, the error string can end up baked into the generated README for a long time before anyone notices, and it hard-blocks `selfdoc check` (and therefore releases) once noticed.

The error message compounds the trap: it says "no strictcli app found", suggesting an app-discovery/import problem, when the actual mechanism is purely a schema-file lookup (`strictcli_support.py` never imports the module). Nothing points the user at the real fix (`path="."`).

## Possible solutions

1. **Distinct attribute name.** Give `table-commands` a `schema-dir` (or `project`) attribute and reject `path` at parse time with an actionable error. Pros: contract is explicit, impossible to confuse with source-dir `path`; fits "mandatory flags over defaults". Cons: breaking change for existing users (all known users pass `path="."`, so migration is mechanical); touches directive parsing + docs + tests.
2. **Deterministic ancestor walk.** `read_schema_json` walks up from the joined path to the nearest ancestor containing `.strictcli/schema.json`. Pros: both spellings work deterministically (not a silent try-A-then-B: the rule is "nearest ancestor", single strategy). Cons: two spellings meaning the same thing hides the contract; a monorepo sub-project directive could silently pick up the root schema when the sub-project forgot to dump its own — arguably a new silent-degradation hazard.
3. **Registration-time validation with a pointed error.** Keep semantics, but when the lookup fails AND a `.strictcli/schema.json` exists at the project root (or nearest ancestor), fail with: `no .strictcli/schema.json under '<joined>'; found one at '<actual>' — table-commands path must point at the directory containing .strictcli/ (use path=".")`. Pros: no contract change, converts a mystery failure into a self-explaining one; smallest change. Cons: the attribute-name collision itself remains.

Options 1 and 3 compose: do 3 now, 1 at the next breaking-change window.

## Affected files

- `selfdoc/content.py` (`resolve_table_commands`)
- `selfdoc/strictcli_support.py` (`read_schema_json`)
- directive parsing/validation + tests for the chosen option
- docs for the directive

## Effort

- Option 3: small (~30 min incl. tests)
- Option 1: medium (~1–2 h incl. migration of existing `path="."` users and docs)
- Option 2: small-medium, but weakest on principle
