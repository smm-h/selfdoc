# Sticky column breaks striped row backgrounds

## Status: Pending | Priority: Low | Effort: Small

## Problem

In horizontally-overflowing tables, the sticky first column sets `background: var(--bg)` which overrides the alternating-row stripe (`tr:nth-child(even) td { background: var(--sidebar-bg) }`) and hover highlight (`tr:hover td { background: var(--sidebar-hover-bg) }`) on the first cell. This causes even rows and hovered rows to lose their background color on the first cell.

## Solution

Add specificity-matched rules in `selfdoc/themes/minimal.css`:

- `tr:nth-child(even) td:first-child` within `.table-wrap.has-overflow` should use `var(--sidebar-bg)`
- `tr:hover td:first-child` within `.table-wrap.has-overflow` should use `var(--sidebar-hover-bg)`

## Affected files

- `selfdoc/themes/minimal.css`
