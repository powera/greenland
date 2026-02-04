# Data Release Directory

This directory contains the canonical JSONL-format linguistic data that can be
imported into or exported from the SQLite database.

## Directory Structure

```
data/release/lemmas/
├── nouns/
│   ├── food/
│   │   └── base.jsonl
│   ├── animals/
│   │   └── base.jsonl
│   └── ...
├── verbs/
│   └── ...
└── ...
```

Each `base.jsonl` file contains concept definitions with translations and
optional difficulty overrides.

## Tools for Loading/Updating Data

### Import NEW lemmas (pradzia)

Use **pradzia** to import new GUIDs into the database. This tool **only adds
new lemmas** - it skips any GUID that already exists.

```bash
# Preview what would be imported (dry-run)
PYTHONPATH=src python src/agents/pradzia.py --import-jsonl data/release/lemmas --dry-run

# Actually import
PYTHONPATH=src python src/agents/pradzia.py --import-jsonl data/release/lemmas
```

**What it syncs:**
- ✅ New GUIDs (lemmas that don't exist in DB)
- ❌ Changed translations on existing lemmas
- ❌ Changed difficulty levels on existing lemmas
- ❌ Any other changes to existing records

### Import with translation updates (dramblys)

Use **dramblys** for imports that also update translations on existing lemmas:

```bash
# Preview import
PYTHONPATH=src python src/agents/dramblys.py --import-jsonl data/release/lemmas --dry-run

# Actually import
PYTHONPATH=src python src/agents/dramblys.py --import-jsonl data/release/lemmas
```

**What it syncs:**
- ✅ New GUIDs
- ✅ New/changed translations on existing lemmas (adds missing languages)
- ❌ Changed difficulty levels (use manage_difficulty_overrides.py instead)
- ❌ Changed lemma_text (reports as collision error if different)

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
PYTHONPATH=src python src/wordfreq/storage/migrate.py sqlite-to-release

# Export to a custom directory
PYTHONPATH=src python src/wordfreq/storage/migrate.py sqlite-to-release \
  --release-dir /path/to/output
```

## Sync Capabilities Summary

| Change Type               | pradzia | dramblys | Barsukas `/sync` |
|---------------------------|---------|----------|------------------|
| New GUIDs                 | ✅      | ✅       | `/sync/additions` |
| New translations          | ✅      | ✅       |                  |
| Changed translations      | ❌      | ✅       |                  |
| Difficulty (base level)   | ❌      | ❌       | `/sync/difficulty` |
| Difficulty overrides      | ❌      | ❌       | manage_difficulty_overrides.py |
| Changed lemma_text        | ❌      | ❌       | `/sync/changes` |
| Remove orphaned GUIDs     | ❌      | ❌       | `/sync/removals` |

## File Format

Each `base.jsonl` record contains:

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

## Important Guidelines

- **GUIDs**: Keep files sorted by GUID. Add new words at the end. Leave gaps
  for removed words (don't renumber).
- **Difficulty**: New words should have difficulty level `-1` unless specified.
- **Lemma form**: Words should be in lemma form with disambiguation if needed.
- **Chinese**: Use mainland Chinese with simplified characters.
