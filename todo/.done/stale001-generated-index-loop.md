# STALE001 false positive on generated index pages

## Problem

`selfdoc check` reports STALE001 on `gen-index.md` (and potentially other generated pages whose content changes between runs while their description stays static). This creates a circular failure during release:

1. `selfdoc gen` regenerates gen-index.md with a hardcoded description but updated content (new modules listed)
2. `selfdoc check` sees content hash changed but description hash unchanged -> STALE001 error (exit 1)
3. The release aborts because selfdoc check failed

The description for gen-index.md is hardcoded in `selfdoc/gen.py` line 372 as a static string. Every time new modules are added to the project, the index listing content changes, but the description cannot change because it is hardcoded.

## Root cause

The staleness detection in `selfdoc_core/staleness.py` (`check_staleness`) fires when content changes and description does not. For hand-written pages this is correct: if you changed the content, you should review the description. For generated pages whose description is fixed by `selfdoc gen`, this check is a false positive.

## Workaround used

The workaround is to temporarily change the description (any change), run `selfdoc check` (which advances the baseline since both content and description changed), then let `selfdoc gen` overwrite the description back to the hardcoded one. Since the content does not change on the next `selfdoc gen` run, `check_staleness` returns None (content unchanged). This workaround must be repeated each time new modules are added to the project.

## Suggested fix

`check_staleness` should skip pages where `generated: true` is set in the frontmatter. The description on generated pages is controlled by selfdoc itself, not by the user, so checking whether the user updated the description is meaningless.

Alternatively, `selfdoc gen` could update the stored hash baseline for pages it writes, so that the next `selfdoc check` sees the content as "unchanged" relative to what gen produced.

## Affected files

- `selfdoc_core/staleness.py`: `check_staleness()` function
- `selfdoc/gen.py`: `_build_gen_index()` function (hardcoded description)
