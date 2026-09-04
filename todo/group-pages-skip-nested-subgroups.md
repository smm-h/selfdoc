# Group pages render no output for nested subgroups' commands

## Context

selfdoc renders CLI reference pages from a strictcli schema dump. The
schema translation layer (`selfdoc/strictcli_support.py`, the
dict-to-list translation functions) correctly preserves nested groups: a
group's `groups` key is carried through translation alongside its
`commands`.

## Problem

The group-page renderer iterates only a group's direct `commands` and
never recurses into its nested `groups`. A command that lives in a
subgroup (e.g. `app group subgroup cmd`) therefore appears on no page at
all: the parent group's page lists only its direct commands, and no page
is generated for the subgroup. The data is present in the translated
schema (verified in the translation layer); the loss is in page
generation/iteration downstream of it.

## Solutions

1. Recurse: group pages list nested subgroups with their commands
   inline, one page per top-level group. Pros: minimal page-count
   change; cons: deep nesting makes long pages.
2. One page per group at any depth, with parent pages linking child
   group pages. Pros: mirrors the CLI structure exactly, scales with
   nesting; cons: more pages, needs breadcrumb/linking work.
3. Flatten: render subgroup commands onto the parent group's page under
   a heading. Cheapest; loses the subgroup as a navigable unit.

The most correct option regardless of effort is (2): pages mirror the
real command tree, and every command has exactly one home page.

## Affected

- The group-page rendering path (the generator that iterates a group's
  `commands`).
- `selfdoc/strictcli_support.py` only if the renderer needs a different
  shape; the translation already preserves nested groups.
- The check layer, if any completeness check should assert every command
  in the schema appears on some page (worth adding: this gap was
  invisible because nothing asserts coverage).

## Effort

Small-medium: the recursion/page-splitting itself is small; the
every-command-has-a-page assertion and fixtures are the real work.
