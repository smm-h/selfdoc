+++
title = "The .stricttools/ layout"
description = "Where selfdoc keeps a repository's state: one hidden directory of function-named directories, an owners file that grants each one, a derived ignore file, the two layout commands, and the script that moves a repository onto the layout."
nav_group = "Guides"
nav_order = 4
+++

# The .stricttools/ layout

Every directory selfdoc owns in a repository lives under one hidden directory at
the repository root, `.stricttools/`, and every directory under it is named for
its FUNCTION rather than for the tool that writes it. Another tool's state sits
beside selfdoc's, under its own function name, in the same directory.

## The directories selfdoc claims

| Directory | Side | Commitment | What it holds |
| --------- | ---- | ---------- | ------------- |
| `.stricttools/docs/` | handwritten | committed | The pages you write, the underscore-prefixed templates they include, and the docs configuration that sits beside them (`projects.toml`, `cv.toml`, `custom.css`). |
| `.stricttools/docs-state/` | generated | committed | What selfdoc generates and the repository keeps: `manifest.json`, `post-manifest.json`, `revisions.json`, `hashes/hashes.json`, `data/` and the generated pages under `pages/`. |
| `.stricttools/docs-cache/` | generated | uncommitted | What selfdoc generates and the repository throws away: the built site at `build/` and one extracted checkout per archived version at `versions/`. |
| `.stricttools/posts/` | handwritten | committed | The project's blog posts. |
| `.stricttools/vocabulary/` | handwritten | committed | The project's accepted and rejected vocabulary. |

The same table, as the data a fleet check reads, comes from the tool itself:

```bash
selfdoc layout dump
```

It prints one object per directory -- its name and path, its side, its
commitment, a description, and the paths it replaced -- so a description of the
layout is generated from one source rather than restated per repository.

### Side: handwritten or generated, never both

A directory is entirely handwritten or entirely generated. A page selfdoc
generates carries a marker comment under its frontmatter, and that marker is
what tells the two apart on disk: a marked page in a handwritten directory, or
an unmarked one in a generated directory, is a defect `selfdoc layout validate`
reports with the move to make.

### Two docs roots, one set of addresses

The pages you write and the pages selfdoc generates live in different
directories and publish into one URL namespace: a page's address comes from its
path relative to whichever root it sits in, so `.stricttools/docs/guide.md` and
`.stricttools/docs-state/pages/internal-build.md` publish at `/guide/` and
`/internal-build/`. Two pages that would take the same address are refused by
the build, with both files named -- there is no rule about which one wins.

A handwritten page also owns its NAME: `selfdoc gen` generates no page for a
module whose page you have written yourself.

## Ownership: one owner per directory

`.stricttools/OWNERS.csv` declares who owns each directory. It carries a header
line and one row per directory:

```csv
directory,owner
docs,selfdoc
docs-state,selfdoc
docs-cache,selfdoc
posts,selfdoc
```

A row is the permission to create. selfdoc creates a directory under
`.stricttools/` only when a row names it as the owner, and refuses with the exact
row to add when none does. selfdoc never writes this file and never creates
`.stricttools/` itself: granting the permission is the repository's own act.

A row whose directory does not exist is a defect, and git carries no empty
directory -- so a directory selfdoc does not create itself gets its row when its
content arrives. `.stricttools/vocabulary/` is such a directory: add
`vocabulary,selfdoc` when you add the vocabulary files.

Reading and writing are open to anyone. The owner is what validates.

## The derived ignore file

`.stricttools/.gitignore` keeps the uncommitted directories out of the
repository. It is derived from the commitment each tool declares rather than
written by hand, and selfdoc owns only the block between its two marker
comments:

```gitignore
# BEGIN selfdoc -- derived from selfdoc's layout declaration
docs-cache/
# END selfdoc
```

Every other line belongs to whoever wrote it and is left alone, so several tools
write their own blocks into one file. `selfdoc build` rewrites selfdoc's block
when it is out of date; commit the result.

It is the one entry inside `.stricttools/` allowed to start with a dot.
`.stricttools/` is hidden already, and nothing inside it needs to be.

## Checking a repository

```bash
selfdoc layout validate
```

It answers for the repository it runs in: every directory under
`.stricttools/` is named in the owners file and everything the owners file names
exists; every directory selfdoc owns holds only what its side allows; nothing
inside starts with a dot except the derived ignore file; and that file carries
what the commitment declarations render. Each problem names its remedy. With
`--json` it publishes the same answer as a payload, which is what a fleet-wide
check reads.

## Moving a repository onto the layout

selfdoc reads this layout and no other. A repository still carrying a
`.selfdoc/` directory, or declaring a `docs`, `output` or `posts.dir` path
outside `.stricttools/`, is refused by every command that reads project state,
with the move named. There is no migrator inside selfdoc and no dual reading.

A repository is moved once, by hand:

```bash
python3 scripts/move-to-stricttools-layout.py --dry-run
python3 scripts/move-to-stricttools-layout.py --apply
```

The dry run prints every move and every content rewrite and changes nothing.
The apply run moves the tracked files with `safegit mv` as one commit -- a page
carrying the generated marker into `.stricttools/docs-state/pages/`, every other
page into `.stricttools/docs/` -- rewrites the paths the moved content names as a
second commit, and then builds the site and refuses to finish unless the URL set
is identical to the one the last build before the move published. Page addresses
come from the path relative to the docs root, so the move keeps every URL, and
the comparison is what proves it.

Before running it, create `.stricttools/` and write its `OWNERS.csv`: the script
prints the rows and refuses until they are there.

### What the config declares afterwards

```json
{
  "docs": ".stricttools/docs/",
  "output": ".stricttools/docs-cache/build/"
}
```

Both keys still name a directory, and both have to name one inside
`.stricttools/`. A project that declares neither gets these.

### A version tagged before the move

A multi-version build extracts each archived version's docs out of its git tag.
A tag made before the move carries the old layout, and no build can read it, so
the archived pages of such a version stay as they were last built. Versions
tagged after the move build from their tags as before.
