# Test files count toward documentation coverage

## Problem

`selfdoc check` counts public symbols from test files (e.g., `tests/test_*.py`, `*_test.go`) toward the 100% coverage requirement. Test classes, fixtures, and helper functions in test files are not meant to be documented. In the gamehome project, 79 of 82 undocumented symbols are from `games/cubeconnect/tests/` — all test classes and fixtures.

The remaining 1 is `infra/autoscaler/main.go:Now` (a function variable for time mocking in tests).

## Expected behavior

Test files should be excluded from the public symbol count. Common patterns: `tests/`, `test_*.py`, `*_test.go`, `*_test.ts`, `__tests__/`, `spec/`. These contain public symbols by necessity (test frameworks require public functions) but those symbols are not part of the project's public API.

## Workaround

None available. Can't exclude specific subdirectories from a source path in selfdoc.json.

## Impact

Blocks gamehome 0.2.0 release (coverage 1020/1102 = 92%, requires 100%).
