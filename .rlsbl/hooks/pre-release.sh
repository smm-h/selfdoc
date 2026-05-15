#!/usr/bin/env bash
set -euo pipefail
<<<<<<< /home/m/Projects/selfdoc/tmprkrd0xsx.ours

echo "Running pre-release checks..."

if [ -f go.mod ]; then
  echo "  Go: vet + build + test"
  go vet ./...
  go build ./...
  go test ./... -race -short -count=1
fi

if [ -f pyproject.toml ]; then
  echo "  Python: pytest"
  python3 -m pytest -x -q
fi

if [ -f package.json ] && node -e "process.exit(require('./package.json').scripts?.test ? 0 : 1)" 2>/dev/null; then
  echo "  npm: test"
  npm test
fi

echo "Pre-release checks passed."
=======
# Project-specific pre-release checks.
# Built-in checks (tests, lint) run automatically before this hook.
# Add custom validation here, e.g.:
#   - Check for uncommitted documentation
#   - Verify external service connectivity
#   - Run integration tests not covered by the test suite
>>>>>>> /home/m/Projects/selfdoc/tmp60ztcla5.theirs
