# src/reports

Reports over the linguistic database. Run each one with
`PYTHONPATH=src python src/reports/<name>.py --help`. Unless a script is marked
**writes** below, it only reads the database. Run them under `GREENLAND_TEST_MODE=1`.

## Curriculum

- **curriculum_bands.py**: a shared library, not a script. It holds the band rules for the core (1-30)
  and named (100-499) bands: missing frequency data sorts as uncommon, and tiers only break ties. It also
  has `backup_database` and `apply_moves`, which write hand-chosen level moves with an operation log.
- **level_warnings.py**: the level report. Warns about core levels outside 20-50 words (ideal 25-40),
  headwords with two senses in the core, scattered subtypes, obscure early words and senses taught out
  of order. Warnings only; levels are placed by hand.
- **level_candidates.py**: suggests levels for a word that has none yet, usually a pending import.
- **level_words.py**: writes each level's words as one diffable text file, for diffing before and after
  a batch of moves.
- **verb_placement.py**: turns `data/wordfreq/cooccurrence.json` into a readable report of verb
  usability, general-purpose verbs, and the verbs each noun group needs. A helper for choosing verbs by
  hand; nothing places verbs automatically.
- **term_age.py**: classifies curated lemmas by lexical stratum, from ancient basic vocabulary to modern
  coinages. It is advisory only and never edits `difficulty_level`.

## Coverage

- **translation_coverage_by_level.py**: translation coverage per language, optionally broken down per
  level (`--per-level`) or listing one language's gaps (`--missing-for`). Use it to plan which
  languages go in a batched translation run.
- **vocabulary_distribution.py**: coverage per POS subtype and the distribution of difficulty levels.
- **broadly_common_words.py**: tokens in the top 150 of at least 3 corpora, ordered by combined rank,
  then the next 50 combined ranks not in that list. It is cheap enough that Barsukas renders it on
  request at `/reports/broadly-common`.
- **missing_words.py**: high-frequency English words that are absent from the dictionary.
- **wordlist_coverage.py**: dictionary coverage for an English word list in wikitext format.

## Data health

- **integrity.py**: runs the structural checks in `storage.integrity` (orphans, missing fields,
  duplicates, level mismatches, stale audio). It is strictly read-only, and the checks' `fix=True`
  option is not exposed here.
- **stale_audio.py**: audio whose `expected_text` no longer matches the current translation, grouped as
  text changed, translation removed, or no matching lemma.
