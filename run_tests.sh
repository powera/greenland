#!/bin/bash
# Test targets for greenland.
#
#   ./run_tests.sh smoke      fast import/startup checks; run on every commit
#   ./run_tests.sh portable   base minus tests that need native/optional deps
#   ./run_tests.sh base       the tests known to pass; run often, not every commit
#   ./run_tests.sh all        everything, including known-failing suites
#
# Any extra arguments are passed through to pytest, so this works:
#   ./run_tests.sh base -k combined_rank -x
#
# base excludes one directory:
#   clients/audio   - needs the audio submodule synced to its recorded commit
#
# portable is base with the tests that require optional native dependencies
# removed, so the suite runs cleanly in environments where those wheels do not
# build or install (jieba, pypinyin, opencc, pykakasi). It is a strict superset
# of smoke and a strict subset of base. The exclusions below are paths rather
# than pytest markers on purpose: the offending imports (notably jieba, pulled
# in eagerly by benchmarks.lib.generators) fail at collection time, before any
# marker-based deselection would apply. Keep this list in sync with the Testing
# section of AGENTS.md when it changes.
set -euo pipefail

cd "$(dirname "$0")"
export PYTHONPATH=src

# Tests that cannot be collected or cannot pass without optional native deps.
# See the comment above for why these are path exclusions.
PORTABLE_EXCLUDES=(
  # jieba: benchmarks.lib.generators.pinyin_letter_count_generator imports jieba
  # at module load, and benchmarks.lib.utils eagerly imports the generators
  # package, so the whole benchmarks tree fails to collect without it.
  --ignore=src/tests/benchmarks
  --ignore=src/tests/lib/benchmarks
  # pypinyin + pykakasi: reading-field construction for Chinese/Japanese.
  --ignore=src/tests/wireword/test_readings.py
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
  base)
    exec python -m pytest src/tests "$@"
    ;;
  all)
    exec python -m pytest src/tests "$@"
    ;;
  *)
    echo "usage: $0 {smoke|portable|base|all} [pytest args...]" >&2
    exit 2
    ;;
esac
