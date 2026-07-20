#!/bin/bash
# Test targets for greenland.
#
#   ./run_tests.sh smoke   fast import/startup checks; run on every commit
#   ./run_tests.sh base    the tests known to pass; run often, not every commit
#   ./run_tests.sh all     everything, including known-failing suites
#
# Any extra arguments are passed through to pytest, so this works:
#   ./run_tests.sh base -k combined_rank -x
#
# base excludes two directories:
#   clients/audio   - needs the audio submodule synced to its recorded commit
#   lib/benchmarks  - 16 known failures from stale datastore.* patch targets
set -euo pipefail

cd "$(dirname "$0")"
export PYTHONPATH=src

TARGET="${1:-base}"
shift || true

case "$TARGET" in
  smoke)
    exec python -m pytest src/tests -m smoke "$@"
    ;;
  base)
    exec python -m pytest src/tests \
      --ignore=src/tests/lib/benchmarks \
      "$@"
    ;;
  all)
    exec python -m pytest src/tests "$@"
    ;;
  *)
    echo "usage: $0 {smoke|base|all} [pytest args...]" >&2
    exit 2
    ;;
esac
