# Assembly CI cloning alternatives

The assembly CI uses shallow git clones. This works but has limitations for large projects.

## Alternatives

- GitHub release assets: project CI uploads built docs as release asset. No clone needed.
- R2/S3 storage: project CI uploads to cloud storage. Fast, no git overhead.
- Builds branch: each project pushes built content to a dedicated branch. Assembly clones that branch.
- createCommitOnBranch direct: project CI pushes directly to assembly repo via GraphQL. Has payload size limits.

## When to revisit

If shallow clone times exceed 60 seconds, or total assembly rebuild time exceeds 1 hour.
