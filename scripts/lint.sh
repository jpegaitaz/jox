#!/usr/bin/env bash
set -euo pipefail
ruff check jox
ruff format jox
echo "✅ Lint + format done."
