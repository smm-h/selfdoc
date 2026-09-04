# Short-help measurement is inconsistent for choice flags

## Context

The doc checks include a minimum-help-length rule (CLI002 in
`selfdoc/check.py`, `_MIN_HELP_LEN`) that warns when an element's help
text is too short. strictcli choice flags carry two help layers: the
flag member's own help and the per-value help of the choice it selects.

## Problem

For choice flags the measured string is not consistently chosen: on some
flags the check measures the member help, on others the member's VALUE
help. Observed on a consumer CLI where four choice-flag members with
comparable help shapes produced warnings on some and not others, with
the difference traceable to which layer was measured rather than to the
actual help quality. The consumer worked around it by lengthening BOTH
layers; the check should instead measure one deliberately chosen layer,
the same one every time.

## Solutions

1. Always measure the member help (the flag's own line in `--help`).
   Simplest and matches what a reader of the flag list sees.
2. Always measure the concatenation/maximum of both layers, so either
   layer being substantial passes. More lenient; still deterministic.
3. Measure both independently with two distinct findings. Strictest;
   may produce warning noise on value-help-light enums.

Any of the three is fine as long as it is one rule applied uniformly;
(1) is the most correct reading of "the help a user first encounters".

## Affected

- `selfdoc/check.py` (CLI002 emission and wherever the element help text
  is selected for choice flags), plus its tests.

## Effort

Small.
