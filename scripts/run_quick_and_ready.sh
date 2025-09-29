#!/usr/bin/env bash
set -euo pipefail
export PYTHONWARNINGS="ignore"
python -c "import os; os.makedirs('outputs/artifacts', exist_ok=True); os.makedirs('outputs/reports', exist_ok=True)"
python -m jox.cli --workflow quick-and-ready
