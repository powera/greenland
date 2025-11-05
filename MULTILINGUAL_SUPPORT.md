# Multi-Language Support Enhancement: Spanish and German

This document describes the changes made to add Spanish and German support to the wordfreq database/codebase, with a new scalable architecture using a `lemma_translations` table.

## Summary

Added comprehensive support for Spanish and German translations, matching the existing French implementation. The architecture has been refactored from individual language columns to a scalable `lemma_translations` table.

## Architecture Changes

### 1. Database Schema

**New Table: `lemma_translations`**
- Replaces individual language columns (`french_translation`, `chinese_translation`, etc.) with a scalable table
- Schema: `lemma_id`, `language_code`, `translation`, `verified`, timestamps
- Supports unlimited languages without schema changes

**File:** `src/wordfreq/storage/models/schema.py`
- Added `LemmaTranslation` model with relationship to `Lemma`
- Maintains backward compatibility with existing columns

### 2. Migration

**File:** `src/wordfreq/storage/migrate_to_lemma_translations.py`
- Migrates existing translations from columns to new table
- Supports all languages: French, Chinese, Korean, Swahili, Vietnamese, Lithuanian
- Includes dry-run mode for safety
- Command: `python -m wordfreq.storage.migrate_to_lemma_translations [--dry-run]`

### 3. Grammatical Forms

**File:** `src/wordfreq/storage/models/enums.py`

**Spanish Forms:**
- Nouns: `NOUN_ES_SINGULAR`, `NOUN_ES_PLURAL` (2 forms)
- Adjectives: 4 forms (2 genders × 2 numbers)
- Verbs: 36 forms (6 persons × 6 tenses)
  - Present (presente)
  - Preterite (pretérito)
  - Imperfect (imperfecto)
  - Future (futuro)
  - Conditional (condicional)
  - Subjunctive (subjuntivo)

**German Forms:**
- Nouns: `NOUN_DE_SINGULAR`, `NOUN_DE_PLURAL` (2 forms)
- Adjectives: 4 forms (2 genders × 2 numbers, simplified)
- Verbs: 36 forms (6 persons × 6 tenses)
  - Present (Präsens)
  - Simple Past (Präteritum)
  - Perfect (Perfekt)
  - Future (Futur I)
  - Conditional (Konjunktiv II)
  - Subjunctive (Konjunktiv I)

### 4. Translation Generation

**Files:**
- `src/wordfreq/translation/client.py`
- `src/wordfreq/prompts/translation_generation/`

**Changes:**
- Parametrized `query_translations()` to accept list of languages
- Default languages: Chinese, Korean, French, Spanish, German, Swahili, Vietnamese
- Updated prompts to use templates with dynamic language lists
- Added language-specific instructions for Spanish and German

**New Methods:**
- `query_spanish_noun_forms(lemma_id)` - Generate Spanish noun forms
- `query_spanish_verb_conjugations(lemma_id)` - Generate Spanish verb conjugations
- `query_german_noun_forms(lemma_id)` - Generate German noun forms
- `query_german_verb_conjugations(lemma_id)` - Generate German verb conjugations

### 5. Prompts

**Spanish Prompts:**
- `src/wordfreq/prompts/spanish_noun_forms/` - Noun declension rules
- `src/wordfreq/prompts/spanish_verb_conjugations/` - Verb conjugation rules

**German Prompts:**
- `src/wordfreq/prompts/german_noun_forms/` - Noun declension rules
- `src/wordfreq/prompts/german_verb_conjugations/` - Verb conjugation rules

Each includes:
- `prompt.txt` - Task-specific instructions
- `context.txt` - Language-specific grammar rules and guidelines

### 6. Generation Scripts

**Spanish:**
- `src/wordfreq/translation/generate_spanish_noun_forms.py`
- `src/wordfreq/translation/generate_spanish_verb_forms.py`

**German:**
- `src/wordfreq/translation/generate_german_noun_forms.py`
- `src/wordfreq/translation/generate_german_verb_forms.py`

All scripts:
- Use new `lemma_translations` table
- Support `--limit`, `--throttle`, `--model`, `--debug` flags
- Automatically skip lemmas with existing forms
- Include error handling and progress reporting

### 7. Agent Updates

**File:** `src/wordfreq/agents/voras.py`
- Added Spanish (`es`) and German (`de`) to `LANGUAGE_FIELDS`
- Now validates and populates Spanish and German translations
- Supports all validation and regeneration operations

### 8. Export Configuration

**File:** `src/wordfreq/trakaido/utils/export_manager.py`
- Added Spanish and German to `LANGUAGE_CONFIG`
- Enables export in Spanish and German formats

### 9. Data Models

**File:** `src/wordfreq/storage/models/translations.py`
- Added `spanish` and `german` fields to `TranslationSet`
- Updated `get_translations()` dictionary

## Usage

### Generate Translations

```bash
# Generate Spanish translations for all lemmas
python -m wordfreq.translation.generate_spanish_noun_forms --limit 100
python -m wordfreq.translation.generate_spanish_verb_forms --limit 100

# Generate German translations for all lemmas
python -m wordfreq.translation.generate_german_noun_forms --limit 100
python -m wordfreq.translation.generate_german_verb_forms --limit 100
```

### Migrate Existing Data

```bash
# Dry run to see what would be migrated
python -m wordfreq.storage.migrate_to_lemma_translations --dry-run

# Perform actual migration
python -m wordfreq.storage.migrate_to_lemma_translations
```

### Validate Translations

```bash
# Using Voras agent (supports all languages including Spanish and German)
python -m wordfreq.agents.voras --check-coverage
python -m wordfreq.agents.voras --validate-all
```

## Backward Compatibility

- Existing language columns remain in database for backward compatibility
- Migration can be run multiple times safely (idempotent)
- New code queries `lemma_translations` table
- Legacy code using old columns will continue to work during transition

## Future Extensions

Adding a new language now only requires:
1. Add language to `DEFAULT_TRANSLATION_LANGUAGES` in client.py
2. Create prompts for noun/verb forms (if applicable)
3. Add grammatical form enums (if needed)
4. Create generation scripts
5. Update agents and export configuration

No database schema changes needed!

## Testing

Before deploying, test with:
1. Run migration in dry-run mode
2. Generate forms for small subset (--limit 10)
3. Validate translations with Voras agent
4. Export sample data in each new language

## Files Modified/Created

**Modified:**
- `src/wordfreq/storage/models/schema.py`
- `src/wordfreq/storage/models/enums.py`
- `src/wordfreq/storage/models/translations.py`
- `src/wordfreq/storage/database.py`
- `src/wordfreq/translation/client.py`
- `src/wordfreq/prompts/translation_generation/prompt.txt`
- `src/wordfreq/prompts/translation_generation/context.txt`
- `src/wordfreq/agents/voras.py`
- `src/wordfreq/trakaido/utils/export_manager.py`

**Created:**
- `src/wordfreq/storage/migrate_to_lemma_translations.py`
- `src/wordfreq/prompts/spanish_noun_forms/`
- `src/wordfreq/prompts/spanish_verb_conjugations/`
- `src/wordfreq/prompts/german_noun_forms/`
- `src/wordfreq/prompts/german_verb_conjugations/`
- `src/wordfreq/translation/generate_spanish_noun_forms.py`
- `src/wordfreq/translation/generate_spanish_verb_forms.py`
- `src/wordfreq/translation/generate_german_noun_forms.py`
- `src/wordfreq/translation/generate_german_verb_forms.py`
- `MULTILINGUAL_SUPPORT.md` (this file)
