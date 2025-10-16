# WordFreq Agents

Autonomous agents for data quality monitoring and maintenance tasks. These agents are designed to run without user interaction, making them suitable for scheduled cron jobs or continuous monitoring.

## Available Agents

### Lokys (Translation and Lemma Validation)

**Name:** "Lokys" means "bear" in Lithuanian - thorough and careful in checking quality.

**Purpose:** Validates multi-lingual translations for correctness and ensures English lemma forms are in proper dictionary/base form (e.g., "shoe" not "shoes").

**Usage:**
```bash
python lokys.py [--check CHECK_TYPE] [--language LANG] [--output REPORT.json] [--model MODEL] [--yes]
```

**Check Types:**
- `--check lemmas` - Validate English lemma_text values are in base form
- `--check translations` - Validate multi-lingual translations
- `--check all` - Run both lemma and translation checks (default)

**Options:**
- `--language LANG` - Check specific language (lt, zh, ko, fr, sw, vi)
- `--output FILE` - Write detailed JSON report to specified file
- `--model MODEL` - LLM model to use (default: gpt-5-mini)
- `--limit N` - Maximum items to check
- `--sample-rate RATE` - Fraction of items to sample (0.0-1.0, default: 1.0)
- `--confidence-threshold THRESHOLD` - Minimum confidence to flag issues (0.0-1.0, default: 0.7)
- `--yes`, `-y` - Skip confirmation prompt before running LLM queries
- `--db-path PATH` - Use custom database path
- `--debug` - Enable debug logging

**Example Usage:**

Check all lemmas and translations:
```bash
python lokys.py --check all --output /tmp/lokys_report.json
```

Check only Lithuanian translations with sampling:
```bash
python lokys.py --check translations --language lt --sample-rate 0.1
```

Check English lemma forms with custom model:
```bash
python lokys.py --check lemmas --model gpt-4o --limit 100
```

Run as a weekly cron job:
```bash
# Add to crontab: Run weekly on Sunday at 3 AM
0 3 * * 0 cd /Users/powera/repo/greenland/src/wordfreq/agents && python lokys.py --sample-rate 0.2 --output /var/log/lokys_weekly.json
```

**Output:**

The agent provides:
- Issue rates (percentage of problems found)
- Counts of validated vs. problematic entries
- Suggested corrections for lemmas and translations
- Confidence scores for each finding
- Optional JSON report with full details

Example console output:
```
================================================================================
LOKYS AGENT REPORT - Translation & Lemma Validation
================================================================================
Timestamp: 2025-01-15 03:00:00
Model: gpt-5-mini
Sample Rate: 100%
Confidence Threshold: 0.7
Duration: 45.67 seconds

ENGLISH LEMMA FORMS:
  Total checked: 1234
  Issues found: 12
  Issue rate: 1.0%

MULTI-LINGUAL TRANSLATIONS:
  Lithuanian (lt):
    Checked: 1234
    Issues: 15 (1.2%)
  Chinese (zh):
    Checked: 567
    Issues: 8 (1.4%)
  Korean (ko):
    Checked: 234
    Issues: 3 (1.3%)
  ...
  Total issues (all languages): 45
================================================================================
```

**What It Checks:**

1. **English Lemma Forms:** Validates that `lemma_text` values are in dictionary/base form:
   - Nouns: singular (e.g., "shoe" not "shoes", "child" not "children")
   - Verbs: infinitive (e.g., "eat" not "eating", "ate", or "eaten")
   - Adjectives: positive form (e.g., "good" not "better" or "best")
   - Adverbs: base form (e.g., "quickly" not "more quickly")

2. **Multi-lingual Translations:** Validates translations in all languages (Lithuanian, Chinese, Korean, French, Swahili, Vietnamese):
   - Semantic correctness: Does the translation accurately convey the meaning?
   - Lemma form correctness: Is the translation in dictionary/base form for that language?
     - Nouns: singular nominative
     - Verbs: infinitive
     - Adjectives: positive/base form

**LLM Integration:**

Lokys uses the LLM validation helpers from `wordfreq/tools/llm_validators.py`, which load prompts from `wordfreq/prompts/lemma_validation/` and `wordfreq/prompts/translation_validation/`. This ensures consistent, configurable validation across different runs.

---

### Dramblys (Missing Words Detector)

**Name:** "Dramblys" means "elephant" in Lithuanian - never forgets what's missing!

**Purpose:** Identifies missing words that should be in the dictionary by scanning frequency corpora, checking category coverage, and finding gaps.

**Usage:**
```bash
python dramblys.py [--check CHECK_TYPE] [--output REPORT.json] [--top-n N]
```

**Check Types:**
- `--check frequency` - Find high-frequency words missing from the database
- `--check orphaned` - Find derivative forms without parent lemmas
- `--check subtypes` - Check POS subtype coverage and identify under-represented categories
- `--check levels` - Check difficulty level distribution for gaps and imbalances
- `--check all` - Run all checks (default)

**Options:**
- `--output FILE` - Write detailed JSON report to specified file
- `--top-n N` - Number of top frequency words to check (default: 5000)
- `--min-subtype-count N` - Minimum expected words per subtype (default: 10)
- `--db-path PATH` - Use custom database path
- `--debug` - Enable debug logging

**Example Usage:**

Run full check with report:
```bash
python dramblys.py --check all --output /tmp/dramblys_report.json
```

Check top 10000 frequency words:
```bash
python dramblys.py --check frequency --top-n 10000
```

Find under-covered subtypes:
```bash
python dramblys.py --check subtypes --min-subtype-count 20
```

Run as a weekly cron job:
```bash
# Add to crontab: Run weekly on Monday at 1 AM
0 1 * * 1 cd /Users/powera/repo/greenland/src/wordfreq/agents && python dramblys.py --output /var/log/dramblys_weekly.json
```

**Output:**

The agent provides:
- Lists of high-frequency missing words with rank information
- Orphaned derivative forms needing parent lemmas
- Under-covered POS subtypes that need more words
- Difficulty level gaps and imbalances
- Priority recommendations for adding new words

Example console output:
```
================================================================================
DRAMBLYS AGENT REPORT - Missing Words Detection
================================================================================
Timestamp: 2025-01-15 01:00:00
Duration: 12.34 seconds

HIGH-FREQUENCY MISSING WORDS:
  Frequency tokens checked: 5000
  Missing words found: 342
  Existing words in database: 1234
  Top 10 missing by rank:
    1. 'example' (rank: 245)
    2. 'another' (rank: 389)
    ...

ORPHANED DERIVATIVE FORMS:
  Total forms checked: 5678
  Orphaned forms: 12

POS SUBTYPE COVERAGE:
  Total subtypes: 45
  Well-covered: 32
  Under-covered: 13
  Most under-covered subtypes:
    1. kitchen_utensils (noun): 3 words
    2. weather_phenomena (noun): 5 words
    ...

DIFFICULTY LEVEL DISTRIBUTION:
  Total trakaido words: 1234
  Average per level: 61.7
  Empty levels: [18, 19]
  Imbalanced levels:
    Level 1: 25 words (expected ~62)
    Level 15: 15 words (expected ~62)
================================================================================
```

**What It Checks:**

1. **High-Frequency Missing Words:** Scans frequency corpora for common words not yet in the database, automatically excluding stopwords and invalid tokens.

2. **Orphaned Derivative Forms:** Finds derivative forms that reference non-existent lemma IDs.

3. **POS Subtype Coverage:** Identifies semantic categories (subtypes) that are under-represented, helping prioritize which types of words to add next.

4. **Difficulty Level Distribution:** Checks that trakaido words are evenly distributed across levels 1-20, identifying gaps and imbalances.

---

### Bebras (Database Integrity Checker)

**Name:** "Bebras" means "beaver" in Lithuanian - industrious builder of solid structures!

**Purpose:** Ensures database structural integrity by identifying orphaned records, missing required fields, and constraint violations.

**Usage:**
```bash
python bebras.py [--check CHECK_TYPE] [--output REPORT.json]
```

**Check Types:**
- `--check orphaned` - Find orphaned records (invalid foreign keys)
- `--check missing-fields` - Find records with missing required fields
- `--check no-derivatives` - Find lemmas without any derivative forms
- `--check duplicates` - Find duplicate GUIDs
- `--check invalid-levels` - Find difficulty levels outside valid range (1-20)
- `--check all` - Run all checks (default)

**Options:**
- `--output FILE` - Write detailed JSON report to specified file
- `--db-path PATH` - Use custom database path
- `--debug` - Enable debug logging

**Example Usage:**

Run full integrity check:
```bash
python bebras.py --check all --output /tmp/bebras_report.json
```

Check only for orphaned records:
```bash
python bebras.py --check orphaned
```

Find missing required fields:
```bash
python bebras.py --check missing-fields
```

Run as a daily cron job:
```bash
# Add to crontab: Run daily at 4 AM
0 4 * * * cd /Users/powera/repo/greenland/src/wordfreq/agents && python bebras.py --output /var/log/bebras_daily.json
```

**Output:**

The agent provides:
- Counts of integrity violations by category
- Details of problematic records with IDs for manual cleanup
- Severity ratings (high/medium) for prioritization
- Total issues summary

Example console output:
```
================================================================================
BEBRAS AGENT REPORT - Database Integrity Check
================================================================================
Timestamp: 2025-01-15 04:00:00
Duration: 5.67 seconds

ORPHANED RECORDS:
  Derivative forms: 3
  Word frequencies: 0
  Example sentences: 1

MISSING REQUIRED FIELDS:
  High severity: 8
  Medium severity: 12

LEMMAS WITHOUT DERIVATIVE FORMS:
  Count: 45

DUPLICATE GUIDs:
  Count: 2

INVALID DIFFICULTY LEVELS:
  Count: 0

TOTAL ISSUES FOUND: 71
================================================================================
```

**What It Checks:**

1. **Orphaned Records:**
   - Derivative forms with invalid lemma_id references
   - Word frequencies with invalid word_token_id or corpus_id
   - Example sentences with invalid derivative_form_id

2. **Missing Required Fields:**
   - Lemmas without definitions or POS types (high severity)
   - Trakaido words (with GUIDs) missing difficulty levels (medium severity)
   - Derivative forms without text or language codes (high severity)

3. **Lemmas Without Derivatives:** Lemmas that have no derivative forms at all, which means they can't be used in practice.

4. **Duplicate GUIDs:** Multiple lemmas sharing the same GUID, which violates uniqueness constraints.

5. **Invalid Difficulty Levels:** Difficulty levels outside the valid range of 1-20.

**When to Run:**

Bebras should be run regularly (e.g., daily) to catch integrity issues early. It's especially useful:
- After bulk imports or migrations
- Before major exports
- When debugging unexpected behavior
- As part of continuous integration checks

---

### Voras (Multi-lingual Translation Coverage Reporter)

**Name:** "Voras" means "spider" in Lithuanian - weaving together the web of translations!

**Purpose:** Reports on the coverage of multi-lingual translations across all languages in the database. Identifies gaps, calculates statistics, and provides insights into translation completeness. Can also generate missing translations using LLM.

**Usage:**
```bash
python voras.py [--check CHECK_TYPE] [--language LANG] [--output REPORT.json] [--fix] [--yes]
```

**Check Types:**
- `--check overall` - Check overall translation coverage across all languages
- `--check language` - Check coverage for a specific language (requires --language)
- `--check difficulty` - Check translation coverage by difficulty level
- `--check all` - Run all checks (default)

**Options:**
- `--language LANG` - Specific language to check (lt, zh, ko, fr, sw, vi) - required for language check
- `--output FILE` - Write detailed JSON report to specified file
- `--fix` - Generate missing translations using LLM and update the database
- `--yes`, `-y` - Skip confirmation prompt before running LLM queries (for --fix mode)
- `--model MODEL` - LLM model to use for translations (default: from constants)
- `--limit N` - Maximum translations to generate per language (for --fix mode)
- `--dry-run` - Show what would be fixed without making changes (for --fix mode)
- `--db-path PATH` - Use custom database path
- `--debug` - Enable debug logging

**Example Usage:**

Check all coverage metrics:
```bash
python voras.py --check all --output /tmp/voras_report.json
```

Check coverage for a specific language:
```bash
python voras.py --check language --language lt
```

Check overall coverage across all languages:
```bash
python voras.py --check overall
```

Generate missing Lithuanian translations (with confirmation):
```bash
python voras.py --fix --language lt
```

Generate all missing translations without confirmation:
```bash
python voras.py --fix --yes
```

Generate up to 50 missing French translations (dry run):
```bash
python voras.py --fix --language fr --limit 50 --dry-run
```

Run as a weekly cron job:
```bash
# Add to crontab: Run weekly on Friday at 6 AM
0 6 * * 5 cd /Users/powera/repo/greenland/src/wordfreq/agents && python voras.py --output /var/log/voras_weekly.json
```

**Output:**

The agent provides:
- Overall translation coverage statistics (fully translated, partially translated, not translated)
- Per-language coverage percentages
- Coverage breakdown by part of speech (POS) type
- Translation coverage across difficulty levels
- Lists of lemmas missing translations for each language

Example console output:
```
================================================================================
VORAS AGENT REPORT - Multi-lingual Translation Coverage
================================================================================
Timestamp: 2025-01-15 06:00:00
Duration: 2.34 seconds

OVERALL COVERAGE:
  Total curated lemmas: 1234
  Fully translated (all languages): 987 (80.0%)
  Partially translated: 234 (19.0%)
  Not translated: 13 (1.0%)

COVERAGE BY LANGUAGE:
  Lithuanian (lt):
    Translated: 1200/1234 (97.2%)
    Missing: 34
  Chinese (zh):
    Translated: 1150/1234 (93.2%)
    Missing: 84
  Korean (ko):
    Translated: 1100/1234 (89.1%)
    Missing: 134
  French (fr):
    Translated: 1180/1234 (95.6%)
    Missing: 54
  Swahili (sw):
    Translated: 1050/1234 (85.1%)
    Missing: 184
  Vietnamese (vi):
    Translated: 1120/1234 (90.8%)
    Missing: 114

COVERAGE BY DIFFICULTY LEVEL:
  Total levels with data: 20
  Sample (first 5 levels):
    Level 1 (62 words):
      Lithuanian: 100.0%
      Chinese: 98.4%
      Korean: 96.8%
      French: 100.0%
      Swahili: 93.5%
      Vietnamese: 95.2%
    ...
================================================================================
```

**What It Checks:**

1. **Overall Coverage:** Counts how many lemmas are fully translated (in all languages), partially translated (in some languages), or not translated at all.

2. **Per-Language Coverage:** For each language, calculates what percentage of curated lemmas have translations and identifies missing ones.

3. **Coverage by POS Type:** When checking a specific language, breaks down coverage by part of speech (noun, verb, adjective, etc.).

4. **Coverage by Difficulty Level:** Shows translation coverage across difficulty levels 1-20, helping identify if certain levels need more translation work.

**What It Can Fix (with `--fix` flag):**

When run with the `--fix` flag, Voras can automatically generate missing translations:
- Uses LLM to query for word definitions including translations for all languages
- Matches the LLM response to existing lemmas by part of speech
- Updates the database with the generated translations
- Provides detailed progress reporting and error handling
- Supports dry-run mode to preview changes before applying them

**When to Run:**

Voras should be run regularly (e.g., weekly) to monitor translation progress and identify gaps. It's especially useful:
- **Reporting mode**: After adding new lemmas to identify what needs translation
- **Reporting mode**: Before releases to ensure translation quality
- **Reporting mode**: To track progress on translation efforts over time
- **Reporting mode**: To prioritize translation work by identifying the least-covered languages or difficulty levels
- **Fix mode**: To batch-generate missing translations for new lemmas
- **Fix mode**: To fill in gaps for specific languages that are under-translated
- **Fix mode**: To quickly bootstrap translations for a new language

---

### Vilkas (Lithuanian Word Forms Checker)

**Name:** "Vilkas" means "wolf" in Lithuanian - a watchful guardian of the word database.

**Purpose:** Monitors the presence and completeness of Lithuanian word forms in the database.

**Usage:**
```bash
python vilkas.py [--check CHECK_TYPE] [--output REPORT.json] [--debug]
```

**Check Types:**
- `--check base-forms` - Check for lemmas with Lithuanian translations but missing derivative forms
- `--check noun-declensions` - Check Lithuanian noun declension coverage (nouns with only base forms)
- `--check verb-conjugations` - Check Lithuanian verb conjugation coverage (verbs with only infinitive)
- `--check all` - Run all checks and generate comprehensive report (default)

**Options:**
- `--output FILE` - Write detailed JSON report to specified file
- `--db-path PATH` - Use custom database path (defaults to `constants.WORDFREQ_DB_PATH`)
- `--debug` - Enable debug logging

**Example Usage:**

Run all checks with report output:
```bash
python vilkas.py --check all --output /tmp/vilkas_report.json
```

Check only noun declensions:
```bash
python vilkas.py --check noun-declensions
```

Run as a daily cron job:
```bash
# Add to crontab: Run daily at 2 AM
0 2 * * * cd /Users/powera/repo/greenland/src/wordfreq/agents && python vilkas.py --output /var/log/vilkas_daily.json
```

**Output:**

The agent provides:
- Coverage percentages for each check type
- Counts of missing/incomplete entries
- Lists of lemmas needing attention (with GUIDs, levels, subtypes)
- Optional JSON report with full details

Example console output:
```
================================================================================
VILKAS AGENT REPORT - Lithuanian Word Forms Check
================================================================================
Timestamp: 2025-01-15 02:00:00
Duration: 1.23 seconds

MISSING LITHUANIAN BASE FORMS:
  Total lemmas with Lithuanian translation: 1234
  Missing derivative forms: 56
  Coverage: 95.5%

LITHUANIAN NOUN DECLENSIONS:
  Total nouns: 567
  With declensions: 234
  Needing declensions: 333
  Coverage: 41.3%

LITHUANIAN VERB CONJUGATIONS:
  Total verbs: 123
  With conjugations: 45
  Needing conjugations: 78
  Coverage: 36.6%
================================================================================
```

**What It Checks:**

1. **Missing Base Forms:** Lemmas that have a `lithuanian_translation` field but no corresponding DerivativeForm entries with `language_code='lt'`. This indicates the translation exists but hasn't been properly added to the derivative forms table.

2. **Noun Declensions:** Lithuanian nouns that have base forms but are missing declension forms (genitive, dative, accusative, instrumental, locative, vocative in both singular and plural). A noun with only 1 Lithuanian form likely needs the remaining 13 declension forms.

3. **Verb Conjugations:** Lithuanian verbs that have only the infinitive form but are missing conjugated forms (present, past, future tenses across different persons and numbers).

## Creating New Agents

To create a new autonomous agent:

1. Create a new Python file in this directory (e.g., `my_agent.py`)
2. Implement the agent class with appropriate check methods
3. Add a `main()` function with argument parsing
4. Make the file executable: `chmod +x my_agent.py`
5. Add documentation to this README
6. Update `__init__.py` to export the agent

**Agent Design Principles:**
- Autonomous: No user interaction required during execution
- Idempotent: Can be run multiple times safely
- Informative: Clear logging and reporting
- Configurable: Command-line arguments for flexibility
- Error-tolerant: Handle database issues gracefully
