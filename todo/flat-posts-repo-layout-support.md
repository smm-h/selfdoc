# Support the flat posts-repo layout

## Background

The shared posts repository (smm-h/posts, declared as the `posts` source
in consuming projects' selfdoc.json) has been restructured in a local
clone: the per-project subdirectories are gone, and every post now lives
as a flat list of markdown files under a single `posts/` directory,
date-prefixed filenames, no nesting. The restructure is committed locally
and deliberately NOT pushed, because the posts-fetch side currently
assumes the old layout — it pulls each consuming project's own
subdirectory from the repo, so pushing the flat layout as-is would make
every consumer's blog build find zero posts.

## What to consider doing

- Teach the posts fetch the flat layout: read `posts/*.md` and associate
  each post with a consuming project by an explicit mechanism — most
  naturally a frontmatter key on the post (each post declares which
  project's blog publishes it), or a filter declared in the consumer's
  posts configuration. Pick one mechanism explicitly; do not support
  both layouts side by side (single layout, clean migration — the old
  subdirectory reading is deleted, not kept as a fallback).
- Decide what an unassociated post means: not published anywhere (a
  parked draft, which the flat layout should support first-class) — and
  make that an explicit state, not an accident.
- Coordinate the cutover: the selfblog release carrying the new fetch
  must ship before (or together with) the push of the flat layout to the
  posts repository, so no consumer's build ever sees a layout its
  installed selfblog cannot read.

## Why

The restructure is already made and waiting; until the fetch side
understands it, the posts repository cannot be pushed without silently
emptying every consumer's blog. The frontmatter-association mechanism
also removes the directory hierarchy as a hidden coupling between the
posts repository's shape and each consumer's identity.
