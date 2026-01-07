#!/usr/bin/env bash
# Bootstrap a new linguistics database from scratch.
# Usage: scripts/bootstrap.sh
#
# This script will:
#   1. Check if database already exists (fail-fast if it does)
#   2. Initialize database tables and corpus configurations
#   3. Load word frequency data from enabled corpora
#   4. Calculate combined frequency ranks
#   5. Import lemmas from data/release JSONL files
#
# Environment overrides:
#   DB_PATH     - Path to SQLite database (default: src/wordfreq/data/linguistics.sqlite)
#   JSONL_DIR   - Path to JSONL data directory (default: data/release)

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

DB_PATH="${DB_PATH:-src/wordfreq/data/linguistics.sqlite}"
JSONL_DIR="${JSONL_DIR:-data/release}"

echo "=== Greenland Database Bootstrap ==="
echo "Database: $DB_PATH"
echo "JSONL data: $JSONL_DIR"
echo ""

# Step 0: Fail-fast if database already exists
if [[ -f "$DB_PATH" ]]; then
  echo "❌ ERROR: Database already exists at: $DB_PATH"
  echo ""
  echo "To start fresh, first remove the existing database:"
  echo "  rm $DB_PATH"
  echo ""
  echo "Or specify a different database path:"
  echo "  DB_PATH=/path/to/new.sqlite scripts/bootstrap.sh"
  exit 1
fi

echo "✓ Database does not exist - proceeding with bootstrap"
echo ""

# Step 1: Initialize database (tables + word frequency corpora)
echo "=== Step 1: Initializing database tables and word frequency data ==="
PYTHONPATH=src python -m agents.pradzia --init-full

if [[ $? -ne 0 ]]; then
  echo "❌ Failed to initialize database"
  exit 1
fi

echo "✓ Database initialization complete"
echo ""

# Step 2: Import lemmas from JSONL files
echo "=== Step 2: Importing lemmas from JSONL files ==="
echo "Source: $JSONL_DIR"

if [[ ! -d "$JSONL_DIR" ]]; then
  echo "⚠️  WARNING: JSONL directory not found: $JSONL_DIR"
  echo "Skipping lemma import."
  echo ""
  echo "To import lemmas later, run:"
  echo "  PYTHONPATH=src python -m agents.pradzia --import-jsonl $JSONL_DIR"
  echo ""
else
  PYTHONPATH=src python -m agents.pradzia --import-jsonl "$JSONL_DIR"

  if [[ $? -ne 0 ]]; then
    echo "❌ Failed to import lemmas from JSONL"
    exit 1
  fi

  echo "✓ Lemma import complete"
  echo ""
fi

# Done!
echo "=== Bootstrap Complete ==="
echo ""
echo "Database initialized at: $DB_PATH"
echo ""
echo "Next steps:"
echo "  1. Run the web UI: PYTHONPATH=src python -m barsukas.app"
echo "  2. Process a lemma: scripts/activate_guid.sh N06_015"
echo ""
