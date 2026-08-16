# selfdoc's own CLI does not build under strictcli 0.41

## Context

strictcli 0.41.0 turned a set of previously-inferred facts into mandatory
declarations, and every one of the new rules is a **registration-time hard
error**. An app that has not migrated does not start at all — it raises before
any command runs, which is deliberate (an unmigrated app fails to build rather
than misbehaving).

selfdoc has not migrated. With strictcli 0.41 installed, `selfdoc --version`
raises:

```
ValueError: Flag "author-url": presence is undeclared: declare exactly one of
presence="required", presence="optional", or default=<value>
```

That is the first flag registration that fails; the rest of the surface has not
been reached yet, so the real work list is however many sites the errors
enumerate one at a time.

## Why this is urgent rather than routine

selfdoc runs on the machine's shared interpreter, so the strictcli it imports is
the shared one. That makes the two possible states mutually exclusive:

- **shared strictcli 0.40** — selfdoc runs, but any consumer already migrated to
  0.41 cannot be imported by a selfdoc custom directive. A directive that
  imports its own project's package dies with `flag() got an unexpected keyword
  argument 'presence'`, and `selfdoc check` reports the directive FAILED and
  exits 1.
- **shared strictcli 0.41** — migrated consumers import fine, and selfdoc itself
  does not start, for every project on the machine.

There is no third state. Any project that migrates to strictcli 0.41 is
therefore blocked at `selfdoc gen` / `selfdoc check`, which are steps 7 and 8 of
the standard release pipeline — so it cannot release until selfdoc has migrated
and shipped.

## The migration, as the 0.41 rules define it

Each of these is a hard error at registration, so the work list is mechanical
once the first is fixed and the next one surfaces:

1. **Presence is declared, never inferred.** Every flag and every positional arg
   declares exactly one of `presence="required"`, `presence="optional"`, or
   `default=<value>`. Declaring none or two raises. `default=None` is refused
   with a redirect to `presence="optional"` — optionality has one spelling.
2. **The arg `required=` parameter is deleted.** `@arg(..., required=False)`
   becomes `presence="optional"`; `required=True` becomes `presence="required"`.
3. **A repeatable or dict flag no longer defaults silently.** Declare
   `default=[]` / `default={}` to keep an empty collection, or
   `presence="optional"` to receive absence instead.
4. **The mutating-default ban.** On a command declaring `effect="mutating"`, no
   flag and no positional arg may declare a *value* default: absence must never
   resolve to a value the invocation did not state. Empty collection defaults, a
   `RelativeToRoot` default, a choice flag's own selector default, an app-level
   global's default, and every declaration on a `read_only` command all stay
   legal. The three remedies the error names are: make it `required`, make it
   `optional`, or apply the fallback in the handler **and say so in the flag's
   help**.
5. **`MutexGroup` is removed.** Exactly-one-of-these is a member-spelled choice
   flag: `@strictcli.choice_flag(name, elect_by="member-flags", choices=[...])`
   with one `@strictcli.choice` class per member. The argv is unchanged and the
   error sentences are reproduced byte for byte, so this is a declaration-side
   change only. A member flag now declares `required` (read as *required once
   this member is elected*), inverting the old rule.
6. **A `choices=` entry is always a record.** `choices=["a", "b"]` becomes
   `choices=[strictcli.Choice("a", help="..."), strictcli.Choice("b")]`, on
   flags and positional args alike. Help per entry is optional.
7. **`dependencies=[...]` is now `constraints=[...]`,** every constraint carries
   a mandatory name, `CoRequired` is deleted in favor of `AllOrNone`, a member is
   a `Member(name, when=...)` record rather than a bare string, and a bool member
   must declare its `when`.
8. **Stacked `@strictcli.arg` decorators now bind top-down.** 0.41 fixed a
   reversal: two or more stacked arg decorators used to bind bottom-up, so any
   declaration written to compensate for the old bug is now inverted. Every
   command with two or more positionals needs its decorator stack re-read
   against the argv it intends. This one is silent — it does not raise.

## Suggested approach

**A. One pass over the whole declaration surface.** Bump the floor, let
registration fail, and work the errors down in a single pass per file, checking
the multi-positional commands by hand for (8). Pro: the errors *are* the work
list, and every rule is enforced, so nothing is missed. Con: nothing runs until
the pass is complete, which is the point.

**B. Stay on the old floor.** Not viable: it does not remove the shared-
interpreter conflict, it only chooses which side of it breaks, and it blocks
every migrated consumer's release indefinitely.

Recommendation: A. Note that (4) and (6) are the two that change *behavior* or
*help output* rather than just spelling, so they deserve the closest reading;
(8) is the one that changes behavior with no error at all.

## Related

A separate item covers what selfdoc *renders* from a 0.41 consumer's
`.strictcli/schema.json` (schema version 2 deletes keys selfdoc reads and adds
constructs it has no rendering for). The two are independent: this one is
selfdoc's own declarations, that one is selfdoc's reader.

## Effort

Medium, and mostly mechanical — the size is however many declaration sites
selfdoc has. The floor bump plus a first failing run gives an exact count.
