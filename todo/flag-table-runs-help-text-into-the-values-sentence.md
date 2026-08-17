# The CLI flag table runs a flag's help straight into its "Values:" sentence

## Symptom

With strictcli >= 0.33.0 a choices entry is a record carrying its own help, and
the generated `cli-<command>.md` flag table appends a `Values:` sentence listing
them. When the flag's own help does not end in punctuation, the two run
together:

```
| `--method` |  | str | default: `hybrid` |  | how each scanned file's format group is decided before it is counted Values: `ext` (group by extension only, sniffing nothing), `type` (content-sniff every file), `hybrid` (trust known text extensions, content-sniff everything else). |
```

`...before it is counted Values: ...` — no separator, and the sentence that
follows is capitalized, so it reads as a run-on.

## Cause

The description cell is built by concatenating the flag's help with the values
sentence and no separator. Flag help conventionally has no terminal period (it
is a fragment rendered after the flag name on one `--help` line), so the missing
separator is the normal case rather than the exception.

## Fix

Insert a separator when the help does not already end in `.`, `!`, `?` or `:`.
A period plus a space matches the values sentence's own style (it ends in `.`).
The alternative — rendering the values on their own line or in a nested list —
is a bigger presentation decision; the separator is the minimal correct fix.

## Affected files

- The CLI flag-table renderer under `selfdoc/` (the code that composes the
  `Values:` sentence into the description column).
- A regression test over a flag whose help ends without punctuation and whose
  choices carry help.

## Effort

Very small. It grows more visible as projects adopt helped choice records.
