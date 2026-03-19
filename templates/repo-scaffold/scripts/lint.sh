#!/bin/bash
# lint.sh — Run project linter
# Customize this for your project's linting tools

set -euo pipefail

echo "Running linter..."

# Uncomment and customize for your stack:
# npx eslint .
# ruff check .
# golangci-lint run
# cargo clippy

echo "⚠️ No linter configured yet. Edit scripts/lint.sh for your project."
exit 0
