# Data Release Directory

This directory contains the canonical JSONL-format linguistic data that can be
imported into or exported from the SQLite database.

## Directory Structure

```
data/release/lemmas/
├── nouns/
│   ├── food/
│   │   ├── base.jsonl
│   │   ├── secondary.jsonl
│   │   ├── audio.jsonl
│   │   └── {lang}.jsonl
│   ├── animals/
│   │   └── base.jsonl
│   └── ...
├── verbs/
│   └── ...
└── ...
data/release/sentences/
├── beginner/
│   └── nouns/
│       └── food/
│           └── base.jsonl
└── ...
```

Each `base.jsonl` file contains concept definitions with translations and
optional difficulty overrides. Sentence `base.jsonl` files contain sentence
translations, word breakdowns, pattern words, and approved audio references.
Lemma `audio.jsonl` files contain approved audio references grouped by GUID.
Per-language lemma files (`{lang}.jsonl`) contain inflection data, grammar
facts, and synonym-class lexical variants for that language.

## Tools for Loading/Updating Data

### Sync via Barsukas UI

Use the **Barsukas web UI** to compare and sync data between data/release and SQLite:

1. Start Barsukas: `PYTHONPATH=src python -m barsukas.app`
2. Navigate to: `/sync` (or use the Sync menu in the navbar)
3. The hub shows counts for each sync type:
   - **Additions**: GUIDs in release but not in SQLite (import new lemmas)
   - **Removals**: GUIDs in SQLite but not in release (delete orphaned lemmas)
   - **Difficulty**: Different difficulty levels (same lemma_text)
   - **Text Changes**: Same GUID but different lemma_text
4. Click into each category to review and apply changes

### Sync per-language difficulty overrides

For per-language difficulty overrides (e.g., different difficulty in Chinese vs
German), use **manage_difficulty_overrides.py**:

```bash
# Set a difficulty override for a specific word/language
PYTHONPATH=src python src/wordfreq/tools/manage_difficulty_overrides.py \
  set LM00001234 zh 2 --notes "Common in Chinese"

# Exclude a word from a language (level -1)
PYTHONPATH=src python src/wordfreq/tools/manage_difficulty_overrides.py \
  set LM00001234 de -1 --notes "Not relevant for German"

# View overrides for a word
PYTHONPATH=src python src/wordfreq/tools/manage_difficulty_overrides.py view LM00001234

# Bulk import from CSV
PYTHONPATH=src python src/wordfreq/tools/manage_difficulty_overrides.py import overrides.csv
```

### Export SQLite to data/release

Use **migrate.py** to export the database back to release format:

```bash
# Export to data/release/lemmas (default)
PYTHONPATH=src python src/storage/migrate.py sqlite-to-release

# Export to data/release/sentences (default)
PYTHONPATH=src python src/storage/migrate.py sqlite-to-sentence-release

# Export only lemma audio files
PYTHONPATH=src python src/storage/migrate.py sqlite-to-lemma-audio-release

# Export to a custom directory
PYTHONPATH=src python src/storage/migrate.py sqlite-to-release \
  --release-dir /path/to/output
```

## Sync Capabilities Summary

| Change Type               | Barsukas `/sync`   |
|---------------------------|--------------------|
| New GUIDs                 | `/sync/additions`  |
| Difficulty (base level)   | `/sync/difficulty` |
| Changed translations      | `/sync/translations` |
| Changed lemma_text        | `/sync/changes`    |
| Remove orphaned GUIDs     | `/sync/removals`   |
| Difficulty overrides      | manage_difficulty_overrides.py |

## File Format

Lemma `base.jsonl` records contain:

```json
{
  "guid": "LM00001234",
  "pos_type": "nouns",
  "pos_subtype": "food",
  "concept_label": "apple",
  "concept_definition": "a round fruit",
  "translations": {
    "en": "apple",
    "lt": "obuolys",
    "es": "manzana"
  },
  "difficulty_overrides": {
    "lt": 3
  }
}
```

Translations are sparse maps. Missing language keys mean no translation is
available for that language. Use a per-language difficulty override of `-1`
when a concept is intentionally not applicable to a language.

Lemma `audio.jsonl` records contain approved audio rows grouped by GUID:

```json
{
  "guid": "LM00001234",
  "audio": [
    {
      "language_code": "lt",
      "voice_name": "alloy",
      "filename": "LM00001234.mp3",
      "status": "approved",
      "expected_text": "obuolys",
      "manifest_md5": "abc123",
      "s3_prod_url": "https://...",
      "s3_staging_url": "https://...",
      "staging_agent": "vieversys",
      "grammatical_form": null
    }
  ]
}
```

Sentence `base.jsonl` records live under
`sentences/{collection}/{pos_type_dir}/{pos_subtype}/base.jsonl` and contain
the sentence GUID, sparse translations, optional `pattern_words`, optional
per-language `words`, and approved sentence `audio` rows. Conversation and
rejected sentences are not exported.

Per-language lemma records may contain `synonyms`, a list of lexical variants
kept out of the main lemma record:

```json
{
  "guid": "N01_001",
  "synonyms": [
    {"grammatical_form": "synonym", "text": "bicycle"},
    {"grammatical_form": "synonym_near", "text": "cycle"},
    {"grammatical_form": "abbreviation", "text": "bike"}
  ]
}
```

The `grammatical_form` value is the relation label. Use specific labels such
as `synonym_near`, `synonym_regional`, `synonym_register`,
`synonym_related`, `synonym_synecdoche`, `abbreviation`, or `expanded_form`
when the words are not exact drop-in equivalents.

## Important Guidelines

- **GUIDs**: Keep files sorted by GUID. Add new words at the end. Leave gaps
  for removed words (don't renumber).
- **Difficulty**: New words should have difficulty level `-1` unless specified.
- **Lemma form**: Words should be in lemma form with disambiguation if needed.
- **Chinese**: Use mainland Chinese with simplified characters.
