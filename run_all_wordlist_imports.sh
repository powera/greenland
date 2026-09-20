#!/usr/bin/env bash
# One-off driver: run the corpus-derived wordlist imports in serial.
#
# Covers every scripts/import_*_level_*.py wordlist on this branch, in level
# order.  One script is deliberately absent: import_yle_names.py, which seeds
# the names table rather than a wordlist and takes none of the flags passed
# through here.
#
# These scripts POST to the live Barsukas server, which makes paid LLM calls for
# every word it has not seen.  They are idempotent -- the helper's preflight
# skips any word the database already accounts for and any word already sitting
# in the pending-import queue -- so re-running a completed domain costs only the
# two preflight requests.
#
# Usage:
#   ./run_all_wordlist_imports.sh            # dry run: prints each plan, no HTTP at all
#   ./run_all_wordlist_imports.sh --execute  # live, paid
#
# Any extra arguments (--model, --limit) pass through to every script.
#
# Per-script stdout/stderr lands in LOG_DIR; the run continues past a failing
# script and reports the failures at the end.

set -u -o pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="${LOG_DIR:-$ROOT/logs/wiki_imports_$(date +%Y%m%d_%H%M%S)}"
mkdir -p "$LOG_DIR"

# Level order, so the log reads in curriculum order.
SCRIPTS=(
  import_unlinked_level_320
  import_wiki_arts_level_330
  import_wiki_biology_level_340
  import_wiki_geography_level_350
  import_wiki_history_level_360
  import_wiki_modern_life_level_370
  import_wiki_physical_science_level_380
  import_wiki_society_level_390
  import_legal_scotus_level_400
  import_cooking_exclusive_level_410
  import_wiki_math_exclusive_level_420
  import_hyphenated_level_430
  import_yle_starters_level_440
  import_yle_movers_level_450
  import_linguistics_basic_level_460
  import_yle_flyers_level_470
  import_wiki_arts_exclusive_level_1000
  import_wiki_biology_exclusive_level_1010
  import_wiki_geography_exclusive_level_1020
  import_wiki_history_exclusive_level_1030
  import_wiki_modern_life_exclusive_level_1040
  import_wiki_physical_science_exclusive_level_1050
  import_wiki_society_exclusive_level_1060
  import_legal_scotus_exclusive_level_1070
  import_chemical_elements_level_1100
  import_linguistics_advanced_level_1110
  import_legal_terms_of_art_level_1130
)

failed=()
for name in "${SCRIPTS[@]}"; do
  log="$LOG_DIR/$name.log"
  echo "=== $name ===" | tee "$log"
  if PYTHONPATH="$ROOT/src" python "$ROOT/scripts/$name.py" "$@" 2>&1 | tee -a "$log"; then
    :
  else
    failed+=("$name")
    echo "!!! $name exited non-zero (see $log)"
  fi
done

echo
echo "Logs: $LOG_DIR"
if ((${#failed[@]})); then
  printf 'FAILED: %s\n' "${failed[*]}"
  exit 1
fi
echo "All ${#SCRIPTS[@]} scripts completed."
