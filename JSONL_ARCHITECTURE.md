# JSONL Storage Backend - Architecture and Outstanding Issues

## Overview

The JSONL storage backend provides a flat-file alternative to the SQLite database, storing linguistic data in human-readable JSON Lines format. This document describes the architecture and outstanding issues that need to be addressed.

## What Was Fixed (December 2025)

### 1. Missing Data in Temporary SQLite Database

**Issue:** When the JSONL backend creates a temporary in-memory SQLite database for queries, it wasn't populating difficulty_overrides and derivative_forms. This meant that even though data was stored in JSONL files, queries for these fields would return empty results.

**Fix:** Updated `_populate_sqlite()` method in `src/wordfreq/storage/backend/jsonl/session.py` to:
- Extract and populate `LemmaDifficultyOverride` records from `lemma.difficulty_overrides` dict
- Extract and populate `DerivativeForm` records from `lemma.derivative_forms` dict
- Added logging to show counts of all populated tables

### 2. Write Synchronization Issue

**Issue:** When code queries the temporary SQLite database and modifies the returned objects, those changes weren't being synced back to JSONL files. The root cause was that queries return SQLAlchemy model instances (from the temp DB), but the JSONL session's `commit()` method only handled JSONL dataclass models.

**Fix:** Enhanced the `commit()` method to:
- Detect SQLAlchemy model instances (e.g., `SQLLemmaTranslation`) from temp database queries
- Find the corresponding JSONL parent model (e.g., the `Lemma` that contains the translation)
- Update the nested data in the JSONL model and save it to disk
- This ensures all writes properly sync to JSONL files regardless of which model type is used

### 3. Schema Mismatches

**Issue:** The JSONL `Sentence` model had fields that didn't exist in the SQLite schema, causing confusion and potential data loss:
- JSONL had: `sentence_text`, `language_code`, `difficulty_level`, `audio_url`
- SQLite has: `pattern_type`, `tense`, `minimum_level`, etc.

**Fix:**
- Updated JSONL Sentence model to include both sets of fields for compatibility
- Added conversion logic in `_populate_sqlite()` to properly map JSONL fields to SQLite schema
- The JSONL model now stores the primary sentence text directly (for convenience), while SQLite stores it in `SentenceTranslation`

### 4. Missing SentenceWord Fields

**Issue:** The JSONL `SentenceWord` model was missing the `is_required_vocab` field present in the SQLite schema.

**Fix:** Added `is_required_vocab: bool = True` to the JSONL SentenceWord dataclass.

### 5. Translation Helper Compatibility

**Issue:** The `set_translation()` helper function wasn't setting the `lemma` reference when creating new `LemmaTranslation` objects, which the JSONL backend requires for nested updates.

**Fix:** Modified `src/wordfreq/storage/translation_helpers.py` to:
- Set `lemma=lemma` when creating new `LemmaTranslation` instances
- Ensure the lemma reference is set when updating existing translations

## Outstanding Architectural Issues

### 1. Missing Tables in JSONL Backend

The following SQLite tables are **NOT** currently represented in the JSONL backend:

#### WordToken
- **Purpose:** Stores word tokens - the specific spelling of a word in a specific language
- **SQLite schema:** `id`, `token`, `language_code`, `frequency_rank`, timestamps
- **Relationships:** Has many `DerivativeForm` and `WordFrequency` records
- **Recommendation:** Consider whether JSONL needs this table. Currently, `DerivativeForm` stores `derivative_form_text` directly without linking to `WordToken`. If frequency analysis is needed, this table should be added.

#### Corpus
- **Purpose:** Stores information about language corpora used for frequency analysis
- **SQLite schema:** `id`, `name`, `description`, `corpus_weight`, `max_unknown_rank`, `enabled`, timestamps
- **Recommendation:** If JSONL backend is used for production data, corpus metadata should be stored. Could be a single `corpus.jsonl` file in `data/working/`.

#### WordFrequency
- **Purpose:** Stores word frequency rankings from different corpora
- **SQLite schema:** `id`, `word_token_id`, `corpus_id`, `rank`, `frequency`
- **Recommendation:** If frequency analysis is needed in JSONL mode, this data should be stored. Could be organized as `data/working/frequencies/{corpus_name}.jsonl`.

**Decision needed:** Are these tables required for the JSONL backend use case, or is JSONL only for export/archival purposes?

### 2. Extension Files Architecture (Minimize Diffs)

**Current Problem:** When mutable data (like audio hashes or additional translations) changes, the entire lemma file is rewritten, creating large git diffs.

**Proposed Solution:** Split mutable "extension" data into separate files:

```
data/working/
├── lemmas/                    # Core lemma data (stable)
│   ├── nouns/
│   │   └── common.jsonl       # Lemma definitions, base translations
│   └── verbs/
│       └── common.jsonl
├── extensions/                # Mutable extension data
│   ├── translations/          # Additional language translations
│   │   ├── de.jsonl           # German translations by GUID
│   │   ├── es.jsonl           # Spanish translations by GUID
│   │   └── pt.jsonl           # Portuguese translations by GUID
│   ├── audio/                 # Audio file metadata
│   │   ├── zh-ash.jsonl       # Chinese voice "ash" audio hashes
│   │   ├── fr-alloy.jsonl     # French voice "alloy" audio hashes
│   │   └── ...
│   └── overrides/             # Per-language difficulty overrides
│       ├── zh.jsonl           # Chinese difficulty overrides
│       └── fr.jsonl           # French difficulty overrides
```

**Benefits:**
- Core lemma data rarely changes → minimal diffs
- Adding a new language only creates one new file
- Audio regeneration only modifies audio extension files
- Difficulty adjustments only touch override files

**Implementation Approach:**
1. Modify `JSONLStorage._load_lemmas()` to also load extension files
2. After loading base lemma data, merge in translations from `extensions/translations/*.jsonl`
3. Merge in audio hashes from `extensions/audio/*.jsonl`
4. Merge in difficulty overrides from `extensions/overrides/*.jsonl`
5. On save, split data back out:
   - Core fields → base lemma file
   - `translations` dict → extension files by language
   - `audio_hashes` dict → extension files by language/voice
   - `difficulty_overrides` dict → extension files by language

**Extension File Format:**
```jsonl
{"guid": "N01_001", "translation": "comer"}
{"guid": "N01_002", "translation": "beber"}
```

or for audio:
```jsonl
{"guid": "N01_001", "voice": "ash", "hash": "abc123..."}
{"guid": "N01_001", "voice": "alloy", "hash": "def456..."}
```

## Write Path Summary

Here's how writes flow through the JSONL backend:

1. **User modifies data via web UI** (e.g., updates a translation)
2. **Route handler** calls helper function (e.g., `set_translation()`)
3. **Helper queries** temp SQLite database, gets SQLAlchemy model instance
4. **Helper modifies** instance and calls `session.add(instance)`
5. **Session tracks** the modified instance in `_pending_adds`
6. **Route handler** calls `session.commit()`
7. **Commit method** detects SQLAlchemy instance, finds parent JSONL model
8. **Commit method** updates nested data in JSONL model (e.g., `lemma.translations[lang] = value`)
9. **Storage layer** rewrites the appropriate JSONL file atomically
10. **Result:** Data persisted to disk in JSONL format

## Query Path Summary

1. **Code queries** session (e.g., `session.query(Lemma).filter(...)`)
2. **Session creates** temporary in-memory SQLite database (first query only)
3. **Session populates** SQLite with all data from JSONL files (via `_populate_sqlite()`)
4. **Query executes** against SQLite database
5. **SQLAlchemy models returned** (from temp database)
6. **Code works with** models as normal
7. **On session.commit()**, modified models sync back to JSONL (see Write Path)

## Testing Notes

When testing JSONL backend changes:
1. **Set environment variable:** `export STORAGE_BACKEND=jsonl`
2. **Run migration:** `python scripts/migrate_backend.py export path/to/sqlite.db path/to/jsonl/dir`
3. **Test writes:** Make changes via web UI, verify JSONL files are updated
4. **Test queries:** Verify data can be queried correctly, including:
   - Translations (nested data)
   - Difficulty overrides (nested data)
   - Derivative forms (nested data)
   - Grammar facts (nested data)
5. **Check diffs:** Verify that small changes result in small diffs

## Recommendations

1. **Implement extension files** to minimize diffs (priority: high)
2. **Decide on missing tables** - Do we need WordToken, Corpus, WordFrequency? (priority: medium)
3. **Add integration tests** for JSONL backend (priority: high)
4. **Document migration process** for production use (priority: medium)
5. **Consider compression** for large JSONL files (priority: low)
6. **Add validation** to ensure JSONL data integrity (priority: medium)

## Performance Considerations

**Advantages:**
- Human-readable format (great for git/review)
- No database locks or connection pooling issues
- Easy to backup/version control
- Can process with standard Unix tools (grep, jq, etc.)

**Disadvantages:**
- Entire dataset loaded into memory on session creation
- Full file rewrites for any change (before extension files implemented)
- Temporary SQLite database created per session (startup cost)
- Not suitable for very large datasets (>1M lemmas)

**Recommended Use Cases:**
- Development/staging environments
- Linguistic databases with <100K lemmas
- Situations requiring version control of data
- Export format for archival/sharing

**Not Recommended For:**
- Production systems with frequent writes
- Very large datasets
- Systems requiring complex transactions
- High-concurrency write scenarios
