#!/usr/bin/env bash
set -euo pipefail

echo "Running pre-release checks..."

if [ -f go.mod ]; then
  echo "  Go: vet + build + test"
  go vet ./...
  go build ./...
  go test ./... -race -short -count=1
fi

if [ -f pyproject.toml ]; then
  echo "  Python: pytest"
  uv run pytest -x -q
fi

if [ -f package.json ] && node -e "process.exit(require('./package.json').scripts?.test ? 0 : 1)" 2>/dev/null; then
  echo "  npm: test"
  npm test
fi

echo "Pre-release checks passed."
