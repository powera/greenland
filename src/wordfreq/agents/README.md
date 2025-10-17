# WordFreq Agents

Autonomous agents for data quality monitoring and maintenance tasks. These agents are designed to run without user interaction, making them suitable for scheduled cron jobs or continuous monitoring.

## Quick Reference

- **Lokys** - Validates multi-lingual translations for correctness and ensures English lemmas are in proper dictionary/base form.
- **Dramblys** - Identifies missing words by scanning frequency corpora and can automatically process them using LLM to add to the database.
- **Bebras** - Ensures database structural integrity by identifying orphaned records, missing fields, and constraint violations.
- **Voras** - Reports on multi-lingual translation coverage across all languages and can generate missing translations using LLM.
- **Vilkas** - Monitors the presence and completeness of Lithuanian word forms in the database and can automatically generate missing forms.

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

**Output:**

The agent provides:
- Issue rates (percentage of problems found)
- Counts of validated vs. problematic entries
- Suggested corrections for lemmas and translations
- Confidence scores for each finding
- Optional JSON report with full details

---

### Dramblys (Missing Words Detector)

**Name:** "Dramblys" means "elephant" in Lithuanian - never forgets what's missing!

**Purpose:** Identifies missing words that should be in the dictionary by scanning frequency corpora, and can automatically process them using LLM to add to the database.

**Usage:**
```bash
# Check/reporting mode (no changes made)
python dramblys.py [--check CHECK_TYPE] [--output REPORT.json] [--top-n N]

# Fix mode (process missing words)
python dramblys.py --fix [--limit N] [--dry-run]
```

**Check Mode (Reporting Only):**
- `--check frequency` - Find high-frequency words missing from the database
- `--check orphaned` - Find derivative forms without parent lemmas
- `--check subtypes` - Check POS subtype coverage and identify under-represented categories
- `--check levels` - Check difficulty level distribution for gaps and imbalances
- `--check all` - Run all checks (default)

**Fix Mode (Process Missing Words):**
- `--fix` - Enable fix mode to process high-frequency missing words using LLM
- `--limit N` - Maximum number of words to process
- `--top-n N` - Number of top frequency words to check for missing (default: 5000)
- `--model MODEL` - LLM model to use (default: gpt-5-mini)
- `--throttle SECONDS` - Seconds to wait between API calls (default: 1.0)
- `--dry-run` - Show what would be fixed **WITHOUT making any LLM calls**
- `--yes`, `-y` - Skip confirmation prompt

**Options:**
- `--output FILE` - Write detailed JSON report to specified file
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

Process missing words (dry run):
```bash
python dramblys.py --fix --dry-run
```

Process top 20 missing words:
```bash
python dramblys.py --fix --limit 20 --yes
```

**Output:**

The agent provides:
- Lists of high-frequency missing words with rank information
- Orphaned derivative forms needing parent lemmas
- Under-covered POS subtypes that need more words
- Difficulty level gaps and imbalances
- Priority recommendations for adding new words

In fix mode:
- Handles plurals (e.g., "years" → lemma "year")
- Handles polysemous words (e.g., "set" → multiple lemmas/definitions)
- Handles grammatical words (e.g., "since" → identifies correct POS and lemma)
- Creates appropriate WordToken, Lemma, and DerivativeForm entries
- Number of words successfully processed vs. failed

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


**Output:**

The agent provides:
- Counts of integrity violations by category
- Details of problematic records with IDs for manual cleanup
- Severity ratings (high/medium) for prioritization
- Total issues summary

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

**Output:**

The agent provides:
- Overall translation coverage statistics (fully translated, partially translated, not translated)
- Per-language coverage percentages
- Coverage breakdown by part of speech (POS) type
- Translation coverage across difficulty levels
- Lists of lemmas missing translations for each language

---

### Vilkas (Lithuanian Word Forms Checker)

**Name:** "Vilkas" means "wolf" in Lithuanian - a watchful guardian of the word database.

**Purpose:** Monitors the presence and completeness of Lithuanian word forms in the database, and can automatically generate missing forms.

**Usage:**
```bash
# Check/reporting mode (no changes made)
python vilkas.py [--check CHECK_TYPE] [--output REPORT.json]

# Fix mode (generate missing forms)
python vilkas.py --fix [--pos-type TYPE] [--limit N] [--dry-run]
```

**Check Mode (Reporting Only):**
- `--check base-forms` - Check for lemmas with Lithuanian translations but missing derivative forms
- `--check noun-declensions` - Check Lithuanian noun declension coverage (nouns with only base forms)
- `--check verb-conjugations` - Check Lithuanian verb conjugation coverage (verbs with only infinitive)
- `--check all` - Run all checks and generate comprehensive report (default)

**Fix Mode (Generate Missing Forms):**
- `--fix` - Enable fix mode to generate missing word forms
- `--pos-type TYPE` - Part of speech to fix (e.g., noun, verb). Defaults to 'noun' for Lithuanian.
- `--language LANG` - Language code for form generation (default: lt, currently only lt supported)
- `--limit N` - Maximum number of lemmas to process
- `--model MODEL` - LLM model to use for generation (default: gpt-5-mini)
- `--throttle SECONDS` - Seconds to wait between API calls (default: 1.0)
- `--source SOURCE` - Source for Lithuanian noun forms: llm (default) or wiki (Wiktionary)
- `--dry-run` - Show what would be fixed **WITHOUT making any LLM calls or database changes**
- `--yes`, `-y` - Skip confirmation prompt

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

Generate missing Lithuanian noun declensions (dry run):
```bash
python vilkas.py --fix --dry-run
```

Generate missing Lithuanian noun declensions with limit:
```bash
python vilkas.py --fix --limit 50 --yes
```

Generate forms using Wiktionary instead of LLM:
```bash
python vilkas.py --fix --source wiki --yes
```

**Output:**

The agent provides:
- Coverage percentages for each check type
- Counts of missing/incomplete entries
- Lists of lemmas needing attention (with GUIDs, levels, subtypes)
- Optional JSON report with full details

In fix mode:
- Number of forms successfully generated
- Number of failures
- Detailed logs of each generation attempt

---

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
