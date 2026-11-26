#!/bin/bash
set -uo pipefail
cd /app
mkdir -p /logs/verifier
# restore original tests in case the solver edited or added files under tests/
git checkout cf19179e8e2fd54c601378cec9e0d21bb12b6fb1 -- tests/
git clean -fdq tests/
cp /tests/test_feature.py tests/test_taskforge_feature.py
python /tests/run_eval.py
