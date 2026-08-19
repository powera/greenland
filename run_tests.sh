#!/bin/bash
# Test targets for greenland.
#
#   ./run_tests.sh smoke      fast import/startup checks; run on every commit
#   ./run_tests.sh portable   base minus tests that need native/optional deps
#   ./run_tests.sh base       the tests known to pass; run often, not every commit
#   ./run_tests.sh all        currently identical to base
#
# Any extra arguments are passed through to pytest, so this works:
#   ./run_tests.sh base -k combined_rank -x
#
# base excludes nothing; it is the whole of src/tests. `all` is kept as an
# alias so existing invocations and docs keep working. (base once excluded
# clients/audio, which needed the audio submodule synced; those tests target
# src/clients/audio, run in ~0.2s with no submodule, and are no longer
# special-cased.)
#
# portable is base with the tests that require optional native dependencies
# removed, so the suite runs cleanly in environments where those wheels do not
# build or install (jieba, pypinyin, opencc, pykakasi). It is a strict superset
# of smoke and a strict subset of base. Keep this list in sync with the Testing
# section of AGENTS.md when it changes.
#
# Everything else in the tree imports its optional deps behind a try/except and
# degrades or skips at runtime, so it collects fine without them. Keep it that
# way: a bare `import jieba` at module scope in anything reachable from src/
# breaks *collection*, which no marker or exclusion below can recover -- smoke
# collects the whole tree to find its marked tests and would fail too.
set -euo pipefail

cd "$(dirname "$0")"
export PYTHONPATH=src

# Tests that cannot pass without optional native deps. Path exclusions rather
# than marker deselection so that a collection-time failure is also covered.
PORTABLE_EXCLUDES=(
  # pypinyin + pykakasi: asserts real reading output for Chinese/Japanese.
  --ignore=src/tests/exports/wireword/test_readings.py
)

TARGET="${1:-base}"
shift || true

case "$TARGET" in
  smoke)
    exec python -m pytest src/tests -m smoke "$@"
    ;;
  portable)
    exec python -m pytest src/tests "${PORTABLE_EXCLUDES[@]}" "$@"
    ;;
  base|all)
    exec python -m pytest src/tests "$@"
    ;;
  *)
    echo "usage: $0 {smoke|portable|base|all} [pytest args...]" >&2
    exit 2
    ;;
esac
