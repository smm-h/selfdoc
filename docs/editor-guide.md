---
title: Editor Guide
description: "Run the local authoring app for blog posts: the hand-written registry of repositories it opens, the loopback server it binds, the tinymoon editor component it mounts, and the preview that is byte-for-byte the page publishing would produce."
nav_group: "Guides"
nav_order: 20
---

# Editor Guide

`selfblog editor serve` runs a local authoring app for blog posts. It opens in a browser, lists the repositories a hand-written registry declares, shows each one's posts, and puts the post source in an editor beside a live preview.

Two properties are worth stating before anything else, because the whole design follows from them:

1. **The preview is the publish.** The pane on the right is not a Markdown approximation and not a second renderer. It is the same render the build performs, handed the unsaved buffer instead of a file, and its output is byte-for-byte the page that publishing this post would write. What you approve on screen is what readers get.
2. **Previewing writes nothing.** Rendering a buffer touches no file in the working tree -- no injected page, no baseline, no manifest. The only write the app ever performs is the save you ask for.

Both are asserted by the test suite, the second by fingerprinting the whole working tree before and after a render and requiring the two to match.

## Scope

The app is local, single-user and unauthenticated. It binds `127.0.0.1` and nothing else, and the bind address is not configurable -- a surface that writes working trees and answers without credentials has no business listening on anything reachable. It is not a hosted service and there is no plan for it to become one.

Mobile layouts are not a priority. The window collapses to a single column below 900 pixels wide, which is enough to read on a small screen and not enough to author comfortably.

## The registry

The app opens the repositories one file names. That file is hand-written, machine-local, and is not framework configuration -- nothing in a project's `selfdoc.json` declares it and nothing generates it.

Its default location is:

```
~/Projects/ark/selfblog-registry.toml
```

Override it with `--registry <path>` on either editor command.

### Format

Every entry is a `[[repo]]` block declaring a `name` and a `kind`. A local entry names a working tree on this machine; edits land in it directly.

```toml
[[repo]]
name = "selfdoc"
kind = "local"
path = "~/Projects/selfdoc"

[[repo]]
name = "notes"
kind = "local"
path = "/srv/notes"
```

| Key | Kind | Required | Meaning |
| --- | --- | --- | --- |
| `name` | both | yes | Unique, and addressable in a URL: letters, digits, dot, dash, underscore. No slashes, no spaces. |
| `kind` | both | yes | `"local"` or `"remote"`. No default -- the file states which. |
| `path` | local | yes | The working tree. `~` is expanded; the directory must exist. |
| `repo` | remote | yes | The repository, as `owner/name`. |
| `ref` | remote | yes | The ref to read. |
| `cache` | remote | yes | Where a checkout of it would live. |
| `render` | remote | yes | Whether rendering runs against a checkout. Boolean, no default. |

A remote entry looks like this:

```toml
[[repo]]
name = "afar"
kind = "remote"
repo = "smm-h/afar"
ref = "v1.2.3"
cache = "~/.cache/selfblog/afar"
render = true
```

**Remote entries are validated in full but are not served yet.** Every path that would have to reach one refuses with `remote entries not yet served`, naming the entry. The validation is complete; the behaviour is honestly deferred rather than half-implemented.

`render` is required and has no default because directive resolution reads a source tree. Whether a remote entry gets one changes what its posts can contain, and neither answer is safe to assume on the author's behalf.

### Every malformed shape refuses

The registry is read strictly. There is no shape that is quietly skipped, because an entry that silently fails to parse is a project whose posts silently stop being editable with no message anywhere to explain it. Each of these is a hard error naming the offender:

- the file is missing, or is not valid TOML;
- a top-level key other than `repo`;
- `repo` that is not an array of tables;
- a missing `name`, `kind`, `path`, `repo`, `ref`, `cache` or `render`;
- an unknown `kind`;
- an unknown key on an entry -- including a remote key on a local entry, which is how a typo is told from a shape;
- `render` that is not a boolean;
- a `path` that is not a directory;
- two entries with the same `name`;
- a `name` that could not be a URL path segment.

## Listing what is registered

```bash
selfblog editor list-repos
selfblog editor list-repos --registry ./my-registry.toml
```

Read-only. It validates the whole file -- so it doubles as the way to check a registry before serving from it -- and prints one line per entry:

```
selfdoc  local   /home/me/Projects/selfdoc
afar     remote  smm-h/afar@v1.2.3 [render, not served yet]
```

## Running the app

```bash
selfblog editor serve --port 4173
```

`--port` is required and has no default. The editor occupies a port on the machine you work on and writes working trees through it; which port that is belongs in the command line rather than in a default nobody reads.

Flags:

| Flag | Default | Meaning |
| --- | --- | --- |
| `--port` | none, required | Port to bind on `127.0.0.1`. |
| `--registry` | the machine-local registry | Path to the registry TOML. |
| `--tinymoon-assets` | the installed tinymoon package | Directory to serve the tinymoon assets from. |

Stop it with Ctrl-C: the accept loop ends, every held event stream is released, and the socket is closed.

The command refuses a `--dry-run` run rather than previewing one. An interactive server has no set of effects known at launch -- the writes are the saves made at the keyboard minutes later -- so recording them at startup would describe nothing.

### Where the front-end comes from

The editing surface is tinymoon's editor component: a real text area over a scroll-synchronised decoration layer, with the framework's own chrome, theme and light/dark handling around it.

tinymoon is not a runtime dependency of selfblog, so the app is told where its assets are rather than discovering them. There are exactly two answers and the caller picks one:

- **`--tinymoon-assets <path>`** -- a checkout's `assets` directory;
- **nothing** -- the installed tinymoon package, read through its own asset path.

Neither is a fallback for the other. If no path is given and no tinymoon is installed, the command refuses and names the flag; it does not quietly serve something else. Either way the resolved tree is checked for every file the shell loads, and a tree missing any of them is refused before a port is bound, with all the missing names listed.

The editor component, its completion popup and its stylesheet are newer than the released tinymoon package, so a checkout is currently the only complete source:

```bash
selfblog editor serve --port 4173 --tinymoon-assets ~/Projects/tinymoon/assets
```

The command prints which source it used on startup, so a session never has to guess.

## Authoring

The sidebar lists the registry's entries; picking one lists its posts, newest first, with drafts marked. Picking a post opens it.

The address bar carries the selection, so a post can be linked to and survives a reload:

```
http://127.0.0.1:4173/#/selfdoc/2026-08-12-hello.md
```

Typing schedules a preview 300 milliseconds after the last keystroke. The buffer is sent to the server, rendered in memory, and the resulting page is pushed to the browser over one server-sent-events channel. Nothing on that path writes.

Saving is explicit: the **Save** button, or Ctrl-S. It writes the buffer into the repository's working tree atomically -- a temporary file in the same directory, then a rename -- so a build, a check or another reader never sees a half-written post. The status line beside the button says whether the buffer differs from what is on disk.

A post path that does not exist yet is created on save, so a new post can be written by navigating to a name and saving it.

### What the preview shows

The rendered page is served at the address the post publishes to, with the repository's build output underneath it. That is what lets the page's own links -- its stylesheet, its feed, its neighbours -- resolve while you look at it.

The consequence is worth knowing: **if the repository has never been built, the preview is correct but unstyled.** The page bytes are right; the stylesheet they point at does not exist yet. Run a posts build in that repository once and the preview picks it up.

A draft is the one case with no published counterpart. A buffer declaring `draft: true` is rendered the way a drafts build renders it, which is the only way to see a draft at all. The decision is read off the buffer every time, never off a mode the server carries.

### Decorations

The editor mounts with an empty decoration set and an empty gutter. Spelling and lint decorations are the next piece of this work and arrive through the same two calls the component already exposes; nothing about the mount changes to accept them.

## Errors

Every refusal is a message, not a silent difference in behaviour:

- a registry that will not parse stops the command before a port is bound;
- an asset tree missing files the shell loads stops it too, naming all of them;
- a request for a repository the registry does not declare answers 404, listing the ones it does;
- a request that reaches a remote entry answers 501 with `remote entries not yet served`;
- a document path that tries to leave the posts directory is refused;
- a buffer the post rules reject -- a missing date, an undeclared directive marker -- comes back as the same message the check would print, in the status line.
