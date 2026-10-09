# scripts

Repo-level utility scripts: pre-commit checks, bootstrap, and pipeline
helpers. (Database maintenance scripts live in `src/scripts/` instead.)

- `wordlists/` — curated wordlist-to-level import scripts and their shared
  `wordlist_import_helper.py`; sport/game lists live in `wordlists/sports_games/`.
  Preview a list with
  `GREENLAND_TEST_MODE=1 PYTHONPATH=src python scripts/wordlists/import_yle_starters_level_440.py`.
  Imports require `--execute` to make changes and may use paid LLM calls.
- `import_yle_names.py` — unfinished Cambridge YLE given-name seed, retained
  separately from the vocabulary imports.

- `bootstrap.sh` — initialize the database from scratch (create tables, load
  frequency corpora, calculate ranks)
- `activate_guid.py` / `activate_guid.sh` — run the full agent pipeline for a
  single lemma GUID
- `check_duplicate_guids.py` — pre-commit check for duplicate GUIDs in
  `data/release`
- `check_api_mirror_routes.py` — pre-commit check that `api/` facades match
  `src/barsukas` routes
- `check_langtools_required_functions.py` — pre-commit check that required
  langtools functions exist per language
- `migrate_synonym_uniqueness.py` — report cross-lemma synonym duplicates
