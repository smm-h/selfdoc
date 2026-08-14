# Assembly push cannot disambiguate same-version tag families in a monorepo

## Context

A monorepo can publish several independently-versioned releasables, each with its
own tag family (`<name>@vX.Y.Z`). The post-release hook dispatches an assembly
rebuild for the just-released project at its latest tag, resolving a project ->
tag by version.

## Problem

When two releasable families in the same monorepo reach the **same version
number**, the assembly dispatch's version-to-tag resolution becomes ambiguous and
either errors or picks the wrong family's tag.

Observed on a real release where three families were at, respectively, patch/minor
versions and two of them collided on one version number:

- The dispatch for one project errored: `ambiguous release tag for version X.Y.Z:
  <famA>@vX.Y.Z, <famB>@vX.Y.Z. Two tag families carry the same version, so the
  dispatch cannot tell which one is this project's.`
- The dispatches that did fire resolved to the **wrong family's** tag (an older
  release of a different project that happened to share the version), so the
  assembly rebuilt from a stale ref for every project in the batch.

The release itself is unaffected (the assembly push is a non-fatal post-release
step), but the published docs on the unified assembly site end up pointing at
stale or wrong refs.

## Root cause

The resolution keys on version number alone. In a monorepo, version number is not
unique across tag families; the family name is the disambiguator and it is already
known at dispatch time (the hook knows which project it is running for).

## Solutions

### A. Resolve by the project's own tag family, not by version (preferred)

The post-release hook knows the releasable it is running for; pass the exact tag
(`<thisproject>@v<version>`) to the assembly dispatch instead of asking it to find
a tag by version.

- Pros: exact, no ambiguity possible, no cross-family collision; the family name is
  already in hand.
- Cons: the dispatch API/CLI must accept an explicit tag (or the ref) rather than a
  bare version; the hook must construct the family-qualified tag.

### B. Disambiguate by requiring the family prefix in the version lookup

Keep the version lookup but scope it to the family the hook names, so
`<famA>@vX.Y.Z` and `<famB>@vX.Y.Z` never compete.

- Pros: smaller change if the lookup already receives the project name.
- Cons: still a lookup where a direct tag would do; leaves the version-keyed path
  in place for other callers to trip over.

## Affected files (indicative — verify)

- The assembly-push command's tag/ref resolution (`selfblog assembly push` path).
- The generated per-project `post-release.sh` hook, if it passes a version rather
  than a tag.

## Effort

Small-to-medium: the fix is passing/using the family-qualified tag. A regression
test needs a monorepo fixture with two tag families colliding on one version,
asserting each project's assembly dispatch targets its own family's tag. Until it
lands, a monorepo whose families' versions ever coincide silently rebuilds docs
from the wrong ref.
