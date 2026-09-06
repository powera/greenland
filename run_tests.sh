#!/bin/bash
# Test targets for greenland.
#
#   ./run_tests.sh smoke      fast import/startup checks; run on every commit
#   ./run_tests.sh affected   smoke plus the tests covering your changed files
#   ./run_tests.sh all        the whole of src/tests
#
# Any extra arguments are passed through to pytest, so this works:
#   ./run_tests.sh all -k combined_rank -x
#
# `affected` is the pre-submit target: smoke alone only proves the tree imports,
# and `all` is more than a single-file change warrants.  It maps each changed
# file to the test directories that exercise it and runs those.
#
# The map is static and lives in src/tests/affected_map.py -- no build step and
# nothing to regenerate on every edit.  Its entries were measured, not guessed:
# tools/measure_test_coverage.py runs the suite under per-test coverage and
# prints which test dirs actually reach each source dir.  Rerun it after a large
# refactor and update the map by hand.  Over-selection is the intended failure
# mode: an unmapped path runs the whole suite rather than nothing.
#
# `base` and `portable` were removed.  base duplicated all (it was the whole of
# src/tests), and portable's one path exclusion was stale -- every optional
# native dep (jieba, pypinyin, opencc, pykakasi) is now gated at runtime behind
# an *_AVAILABLE flag, so the suite skips cleanly where those wheels are absent
# instead of needing a separate target.  Keep it that way: a bare `import jieba`
# at module scope in anything reachable from src/ breaks *collection*, which no
# marker or exclusion can recover -- smoke collects the whole tree to find its
# marked tests and would fail too.
set -euo pipefail

cd "$(dirname "$0")"
export PYTHONPATH=src

TARGET="${1:-all}"
shift || true

case "$TARGET" in
  smoke)
    exec python -m pytest src/tests -m smoke "$@"
    ;;
  affected)
    # Keep the selector's own diagnostics on stderr and out of the target list.
    SELECTED=$(python tools/select_affected_tests.py "$@") || exit $?
    if [ -z "$SELECTED" ]; then
      echo "No mapped tests for these changes; running smoke only." >&2
      exec python -m pytest src/tests -m smoke
    fi
    # smoke runs as its own pass, not as `-m smoke` alongside the node ids --
    # combining them would deselect every selected test that is not marked
    # smoke.  The failure this repo actually hits is a moved module that
    # something named as a string, which only a full collect finds.
    python -m pytest src/tests -m smoke || exit $?
    exec python -m pytest $SELECTED
    ;;
  base|portable)
    echo "error: the '$TARGET' target was removed; use 'affected' before a commit or 'all'." >&2
    exit 2
    ;;
  all)
    exec python -m pytest src/tests "$@"
    ;;
  *)
    echo "usage: $0 {smoke|affected|all} [pytest args...]" >&2
    exit 2
    ;;
esac
