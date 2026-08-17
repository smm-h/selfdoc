# The generated CLI reference leaves the Short column empty for selection members

## Context

A strictcli app can declare a selection (`elect_by: "member-flags"`) whose
members are elected by their own flags, and a member may carry a short form.
In the dumped schema a payload-carrying member looks like this:

```json
{
  "name": "session",
  "elect_by": "member-flags",
  "choices": [
    { "name": "cont", "help": "continue the most recent conversation ..." },
    { "name": "resume", "help": "resume one specific session",
      "flags": [
        { "name": "value", "help": "session to resume ...", "short": "r",
          "value_schema": {"type": "string"}, "presence": "required" }
      ] }
  ]
}
```

The app's own `--help` renders `--resume, -r <str>`.

## Problem

The generated CLI reference page renders the member rows with an empty Short
column, even for the members whose short is present in the schema:

```
| Name | Short | Type | Presence | Env | Description |
| --- | --- | --- | --- | --- | --- |
| `session` |  | choice | default: `{"choice": "new-session"}` |  | Selection (not typed as a flag). Elect exactly one of `--cont`, `--resume`, ... |
|     `--cont` |  |  | required |  | Elects `session` = `cont`. continue the most recent conversation ... |
|     `--resume` |  | str | required |  | Elects `session` = `resume`. resume one specific session Its value: session to resume ... |
```

So a reader of the docs sees `--resume` only and never learns `-r` exists,
while `--help` shows both. The docs contradict the tool. For a CLI whose
short forms are the spelling most operators actually type, the reference page
is the wrong half of the story.

Two separate misses are worth distinguishing:

1. **Payload-carrying members**: the short IS in the schema, on the member's
   value flag (`choices[].flags[].short`). The renderer walks that flag for
   its type and presence but does not lift its `short` into the row. This is
   fixable here and is the whole of this todo's ask.
2. **Payload-less members**: the schema dump currently omits the short
   entirely, so there is nothing for the renderer to read. That half needs a
   fix in the schema producer first; this todo does not depend on it, and the
   renderer should simply show a short whenever one is present.

## How to reproduce

1. Point a project at a strictcli app with a member-flags selection where one
   member's value declares `short`.
2. Regenerate the docs.
3. The CLI reference row for that member has an empty Short cell; the app's
   `--help` shows the short.

## Solutions

### A. Lift the member's short into the member row (recommended)

When rendering a member row, read `short` from the member's value flag (and,
once the producer exports it, from the member record itself) and render it in
the Short column exactly as an ordinary flag's short is rendered.

- Pro: the reference matches `--help`, which is the whole point of a generated
  reference.
- Pro: purely additive -- rows that have no short are unchanged.
- Con: pages whose content hash is tracked will report a content change and
  need a reviewed baseline acceptance on the next run.

### B. Append the short to the member's description text

Write `-r` into the prose cell instead of the Short column.

- Pro: no column semantics to decide.
- Con: the table already has a Short column; putting the value elsewhere makes
  it unfindable and unsortable. Not recommended.

### C. Render the value flag as its own indented sub-row

Give the member's value its own row, with name, short, type and presence.

- Pro: describes the value fully, including its own help.
- Con: doubles the row count for every payload-carrying member and buries the
  member itself. Only worth it if member values grow more attributes.

## Affected areas

- the CLI reference table renderer (the member-flags selection branch)
- whatever fixture or conformance page covers a selection with member shorts
- the content-hash baselines of any project regenerating an affected page

## Effort

Small: one lookup and one cell in the member-row renderer, plus a fixture.
