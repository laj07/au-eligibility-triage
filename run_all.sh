#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
python3 data/generate_synthetic.py
python3 evaluate.py > /dev/null
python3 tests/test_triage.py
