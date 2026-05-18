# Brotli pre-compression dependency promotion

## Status: Deferred
## Priority: Low

## Context

selfdoc pre-compresses static output files at build time. Gzip (`.gz`) is always generated. Brotli (`.br`) is only generated when the optional `brotli` Python package is installed (`pip install selfdoc[perf]`).

Brotli achieves 15-25% smaller files than gzip by using a built-in 120KB dictionary of common web patterns and higher compression levels. Since compression is done at build time (level 11), the CPU cost is paid once.

## Why deferred

Cloudflare Pages (the primary deploy target) already applies Brotli compression at the edge. Pre-compression is partially redundant for CF Pages consumers. GitHub Pages only serves gzip, making pre-compression more relevant there, but the savings are smaller in absolute terms for typical documentation sites.

## Options

1. **Make `brotli` a required dependency** -- guarantees all consumers get optimal compression. Adds a compiled C extension that may complicate some installs (especially on Alpine, musl-based containers).
2. **Keep as `perf` extra but improve messaging** -- show concrete missed savings in build output (e.g., "Brotli would save 47KB across 12 files; install with `pip install selfdoc[perf]`"). Currently the message is easy to overlook.
3. **Keep current behavior** -- optional with quiet fallback.

## Recommendation

Option 2: louder messaging with concrete savings. The build already walks all compressible files for gzip; computing the hypothetical Brotli savings without actually compressing is not feasible, but a general recommendation with the number of files that would benefit is actionable.

## Affected files

- `selfdoc/build.py`: `_compress_output()` function (lines ~791-852)
- `pyproject.toml`: `[project.optional-dependencies]` perf extra
