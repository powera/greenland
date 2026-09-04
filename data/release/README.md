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
│   │   ├── ancient.jsonl
│   │   ├── audio.jsonl
│   │   └── {lang}.jsonl
│   ├── animals/
│   │   └── base.jsonl
│   └── ...
├── verbs/
│   └── ...
└── ...
data/release/phrases/
├── greetings/
│   └── base.jsonl
└── traveler/
    └── base.jsonl
data/release/sentences/
├── beginner/
│   └── nouns/
│       └── food/
│           └── base.jsonl
└── ...
data/release/idioms/
└── base.jsonl
data/release/names/
└── base.jsonl
```

Each `base.jsonl` file contains concept definitions with translations and
optional difficulty overrides. Sentence `base.jsonl` files contain sentence
translations, word breakdowns, pattern words, and approved audio references.
Lemma `audio.jsonl` files contain approved audio references grouped by GUID.
Per-language lemma files (`{lang}.jsonl`) contain inflection data, grammar
facts, and synonym-class lexical variants for that language.

Beside `base.jsonl` a lemma category may hold **grouped translation files**:
`secondary.jsonl` for every Tier 3/4 language, and one file per named extra
language group (`ancient.jsonl`). These hold the same
`{guid, translations, translation_metadata}` shape as `base.jsonl` but for
languages kept out of the main record, and they are *not* per-language files -
their stem is a group name, not a language code. Anything reading the tree has
to route them by name; see
`storage.backend.jsonl.storage.GROUPED_TRANSLATION_FILE_STEMS`.

Idioms and names each live in a single `base.jsonl`. Neither is subtyped in the
release tree: an idiom has no subtype at all, and a name's kind is already
encoded in its GUID prefix.

## Tools for Loading/Updating Data

### Bootstrap SQLite from this release

Use the administrative bootstrap script when creating a complete SQLite
database from this directory. It refuses to replace a populated database unless
`--force` is supplied.

```bash
PYTHONPATH=src python bootstrap_database.py \
  --db-path /path/to/linguistics.sqlite
```

Pass `--release-only` to omit local word-frequency corpora, tier imports, and
combined-rank calculation.

### Sync via Barsukas UI

Use the **Barsukas web UI** to compare and sync data between data/release and SQLite:

1. Start Barsukas: `src/barsukas/launch.sh` (the default `local` persona uses SQLite)
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

# Export to data/release/phrases (default)
PYTHONPATH=src python src/storage/migrate.py sqlite-to-phrase-release

# Export to data/release/idioms (default)
PYTHONPATH=src python src/storage/migrate.py sqlite-to-idiom-release

# Export to data/release/names (default)
PYTHONPATH=src python src/storage/migrate.py sqlite-to-name-release

# Export only lemma audio files
PYTHONPATH=src python src/storage/migrate.py sqlite-to-lemma-audio-release

# Export to a custom directory
PYTHONPATH=src python src/storage/migrate.py sqlite-to-release \
  --release-dir /path/to/output
```

Idioms and names also import in the other direction. Both skip records whose
GUID is already present, so re-running is safe; reconciling a record that
changed on either side is the sync UI's job, not the importer's:

```bash
PYTHONPATH=src python src/storage/migrate.py idiom-release-to-sqlite
PYTHONPATH=src python src/storage/migrate.py name-release-to-sqlite
```

### Sync lemma audio back from data/release into SQLite

`sqlite-to-lemma-audio-release` only writes files. To pull the approved lemma
audio in `data/release/lemmas/*/audio.jsonl` **back into** an existing SQLite
database, use **lemma-audio-release-to-sqlite**. It upserts audio rows matched on
`(guid, language_code, voice_name, grammatical_form)`, links each row to its
lemma by GUID, and leaves local review metadata (`reviewed_by`, `notes`,
`quality_issues`, acceptance columns) untouched:

```bash
# Add/update audio rows from release files
PYTHONPATH=src python src/storage/migrate.py lemma-audio-release-to-sqlite

# Also delete exportable audio rows that are no longer in the release files
PYTHONPATH=src python src/storage/migrate.py lemma-audio-release-to-sqlite --prune
```

## Sync Capabilities Summary

Lemma modes live under `/sync/lemmas`:

| Change Type               | Barsukas page              |
|---------------------------|----------------------------|
| New GUIDs                 | `/sync/lemmas/additions`   |
| Remove orphaned GUIDs     | `/sync/lemmas/removals`    |
| Changed lemma_text        | `/sync/lemmas/changes`     |
| Difficulty (base level)   | `/sync/lemmas/difficulty`  |
| Changed translations      | `/sync/lemmas/translations` |
| Tier 3/4 translations     | `/sync/lemmas/secondary-translations` |
| Grammar facts             | `/sync/lemmas/grammar-facts` |
| Difficulty overrides      | manage_difficulty_overrides.py |

Other element types have their own sections under `/sync`:
`/sync/derivatives`, `/sync/synonyms`, `/sync/variants`, `/sync/relations`,
`/sync/sentences`, `/sync/phrases`, `/sync/idioms`, `/sync/names`,
`/sync/lemma-audio`, `/sync/tombstones`.

Idioms and names are compared and written **whole**: each has one `base.jsonl`
and no per-language files, so a record either matches or it does not, and
picking a side replaces the whole record on the other. Their pages therefore
offer three modes (additions, removals, changes) plus a whole-file export.

Concepts are deliberately not synced. They are keyed to Wikidata and never
enter `data/release`; the only concept data that ships is a lemma's `qid`,
which the lemma "changes" mode reconciles.

Long difference lists are paginated (default 200 rows). The button beneath each
list applies one choice to the whole list, including the rows not on the current
page; it echoes back the count it was rendered with and refuses the submit if
the list has changed size since.

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
  "english": "apple",
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

The `english` field is the English word the audio relates to (the lemma's
`concept_label`), included so the file is self-describing without a lookup into
`base.jsonl`. It is informational on import. In the long run lemma audio will
move into the per-language `{lang}.jsonl` files; for now it stays in
`audio.jsonl`.

Sentence `base.jsonl` records live under
`sentences/{collection}/{pos_type_dir}/{pos_subtype}/base.jsonl` and contain
the sentence GUID, sparse translations, optional `word_hints`, optional
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

A per-language record may also contain `variants`: alternate *spellings of the
same lexeme*, each carrying its own full paradigm. "grey" is not a synonym of
"gray" (a different lexeme) nor an inflection of it (a different grammatical
slot), which is why it is neither of the two arrays above:

```json
{
  "guid": "A02_008",
  "variants": [
    {
      "kind": "spelling",
      "key": "grey",
      "forms": [
        {"grammatical_form": "adjective/en_positive", "text": "grey", "is_base_form": true},
        {"grammatical_form": "adjective/en_comparative", "text": "greyer", "is_base_form": false}
      ]
    }
  ]
}
```

A variant is the same lemma written another way, and that is what separates it
from the other two relations the database records:

* An **inflection** is a different grammatical slot of one spelling (gray,
  grayer, grayest). It is a `forms` entry, from `derivative_forms`.
* A **variant** is another way of writing the lemma itself (grey for gray, TV
  for television). It is a `variants` entry, from `variant_forms`, and carries
  a paradigm of its own — which is why it cannot be one extra `forms` row.
* A **synonym** is a different lemma with a similar meaning (quickly/swiftly).
  It belongs to neither word, so it is a relation between lemmas, in
  `lemma_relations/synonym/`.

`kind` is `spelling`, `script` (Chinese simplified/traditional),
`abbreviation`, or `expanded`; it is deliberately open, since the meaningful
kinds are language-specific. `key` identifies the variant within the lemma and
is conventionally the variant's own base form. `is_base_form` is scoped to the
variant: "grey" is the base form of the "grey" variant, while "gray" remains
the lemma's own base form in `forms`.

**Only en-US variants are written today.** A row saying "grey" is an accepted
way to write "gray" makes no claim that it is *the British* form — a regional
dialect is a different axis, and is not stored here yet. When en-GB is taken up
properly it becomes either a region tag on these rows or a storage dialect of
its own. See `storage/models/variant_form.py`.

Name records live in `names/base.jsonl`:

```json
{
  "guid": "E01_001",
  "kind": "given_name",
  "name_text": "George",
  "gender": "masculine",
  "translations": {
    "lt": "Džordžas",
    "zh": "乔治",
    "ja": "ジョージ"
  },
  "translation_metadata": {
    "lt": {"ipa_pronunciation": "ˈdʒɔrdʒɐs", "verified": true},
    "zh": {"sort_key": "qiaozhi"}
  }
}
```

A name is a proper noun that appears in our texts but is not vocabulary -
"George", "Fresh Mart", "Maple Street". It is release data because its
per-language renderings are: every text that casts the same character has to
render it identically. `translations` is a flat map exactly as it is for
lemmas, and the extras a rendering can carry (IPA, phonetic respelling, the
romanized `sort_key`, `verified`) live in `translation_metadata` under the same
language codes.

Names carry no difficulty level and no definition: a learner does not *learn*
George, and a sentence's `minimum_level` skips names when rolling up difficulty.
The `kind` is one of `storage.models.name_entity.NAME_KINDS` and is also encoded
in the GUID prefix (`E01` given_name, `E02` family_name, `E03` full_name, `E04`
place, `E05` organization, `E06` brand, `E07` animal, `E99` other).

### Retired GUIDs: `tombstones/guid_tombstones.jsonl`

A GUID is permanent. When a word is removed, or its part of speech is corrected
and it needs a GUID from another prefix, the old number is **retired** rather
than freed, and a tombstone records that:

```json
{
  "guid": "A05_001",
  "original_lemma_text": "kind",
  "original_pos_type": "adjective",
  "original_pos_subtype": "quality",
  "reason": "release_history_gap",
  "replacement_guid": "A16_001",
  "notes": "Tombstoned from git history to prevent GUID reuse.",
  "changed_by": "agent_git_history_backfill",
  "tombstoned_at": "2026-06-15T00:00:00"
}
```

This is the machine-readable form of the "leave gaps for removed words" rule
below. `storage.utils.guid.generate_guid` reads it and will not issue a
tombstoned number, which matters most for a prefix whose lemmas are *all* gone:
counting up from the highest live row would otherwise restart at `_001` on top
of GUIDs that already shipped.

`reason` is one of the values in `storage.models.guid_tombstone.TOMBSTONE_REASONS`.
Optional fields are omitted rather than written as `null`. The lemma's local
database id is deliberately **not** part of the record: it changes with every
bootstrap, and `replacement_guid` carries the only link worth shipping.

Tombstones are never deleted. `/sync/tombstones` therefore offers export but no
delete, and `tombstone-release-to-sqlite` refreshes existing rows rather than
skipping them:

```bash
PYTHONPATH=src python src/storage/migrate.py tombstone-release-to-sqlite
```

Note that a gap in the numbering does **not** imply a tombstone. Some gaps never
held a word at all - a category split that started numbering mid-range, or a
range reserved in a generator (see `src/wordfreq/data/family_relations_sections.py`,
which hardcodes its `N35` GUIDs). Only a GUID that actually named something gets
a tombstone.

## Important Guidelines

- **GUIDs**: Keep files sorted by GUID. Add new words at the end. Leave gaps
  for removed words (don't renumber). A removed GUID is retired permanently and
  recorded in `tombstones/guid_tombstones.jsonl`; `generate_guid` reads that
  file's contents and will not reissue it.
- **Difficulty**: New words should have difficulty level `-1` unless specified.
- **Lemma form**: Words should be in lemma form with disambiguation if needed.
- **Chinese**: Use mainland Chinese with simplified characters.
- **Phrases**: Fixed traveler phrases (e.g. "Where is the toilet?") are stored as
  lemmas with `pos_type` `phrase` under `lemmas/phrases/<subtype>/` (GUID prefixes
  `F01` greetings, `F02` traveler). The English phrase goes in `concept_label` and
  a one-line usage note in `concept_definition`. Phrases are intentionally excluded
  from sentence assembly and the rhyming dictionary
  (`storage.translation_helpers.NON_LEXEME_POS_TYPES`).
