# WordFreq Agents

Autonomous agents for data quality monitoring and maintenance tasks. These agents are designed to run without user interaction, making them suitable for scheduled cron jobs or continuous monitoring.

## Quick Reference

- **Lokys** - Validates English lemma forms and other English-language properties (definitions, POS types).
- **Dramblys** - Identifies missing words by scanning frequency corpora and can automatically process them using LLM to add to the database.
- **Bebras** - Ensures database structural integrity by identifying orphaned records, missing fields, and constraint violations.
- **Voras** - Validates multi-lingual translations for correctness, reports on coverage, and can populate missing translations using LLM.
- **Vilkas** - Monitors the presence and completeness of Lithuanian word forms in the database and can automatically generate missing forms.

## Available Agents

### Lokys (English Lemma Validation)

**Name:** "Lokys" means "bear" in Lithuanian - thorough and careful in checking quality.

**Purpose:** Validates English-language properties including lemma forms (ensuring they're in proper dictionary/base form like "shoe" not "shoes"), definitions, and POS types.

**Usage:**
```bash
python lokys.py [--output REPORT.json] [--model MODEL] [--limit N] [--sample-rate RATE] [--yes]
```

**Options:**
- `--output FILE` - Write detailed JSON report to specified file
- `--model MODEL` - LLM model to use (default: gpt-5-mini)
- `--limit N` - Maximum items to check
- `--sample-rate RATE` - Fraction of items to sample (0.0-1.0, default: 1.0)
- `--confidence-threshold THRESHOLD` - Minimum confidence to flag issues (0.0-1.0, default: 0.7)
- `--yes`, `-y` - Skip confirmation prompt before running LLM queries
- `--db-path PATH` - Use custom database path
- `--debug` - Enable debug logging

**Example Usage:**

Check all English lemmas:
```bash
python lokys.py --output /tmp/lokys_report.json
```

Check English lemma forms with sampling:
```bash
python lokys.py --sample-rate 0.1 --yes
```

Check with custom model and limit:
```bash
python lokys.py --model gpt-4o --limit 100
```

**Output:**

The agent provides:
- Issue rates (percentage of problems found)
- Counts of validated vs. problematic entries
- Suggested corrections for English lemmas
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

### Voras (Multi-lingual Translation Validator and Populator)

**Name:** "Voras" means "spider" in Lithuanian - weaving together the web of translations!

**Purpose:** Validates multi-lingual translations for correctness and proper lemma form, reports on translation coverage, and generates missing translations using LLM.

**Modes:**
- `coverage` - Report on translation coverage (default, no LLM calls)
- `check-only` - Validate existing translations without populating missing ones
- `populate-only` - Add missing translations without validating existing ones
- `both` - Validate existing translations AND populate missing ones

**Usage:**
```bash
python voras.py [--mode MODE] [--language LANG] [--output REPORT.json] [--yes]
```

**Options:**
- `--mode MODE` - Operation mode: coverage (default), check-only, populate-only, both
- `--language LANG` - Specific language to process (lt, zh, ko, fr, sw, vi)
- `--output FILE` - Write detailed JSON report to specified file
- `--yes`, `-y` - Skip confirmation prompt before running LLM queries
- `--model MODEL` - LLM model to use (default: from constants)
- `--limit N` - Maximum items to process per language
- `--sample-rate RATE` - Fraction of items to sample for validation (0.0-1.0, default: 1.0)
- `--confidence-threshold THRESHOLD` - Minimum confidence to flag issues (0.0-1.0, default: 0.7)
- `--dry-run` - Show what would be done without making changes
- `--db-path PATH` - Use custom database path
- `--debug` - Enable debug logging

**Example Usage:**

Report on translation coverage (no LLM calls):
```bash
python voras.py --mode coverage --output /tmp/voras_report.json
```

Validate Lithuanian translations only:
```bash
python voras.py --mode check-only --language lt
```

Populate missing French translations only:
```bash
python voras.py --mode populate-only --language fr --limit 50
```

Validate all existing translations AND populate missing ones:
```bash
python voras.py --mode both --yes
```

Validate with sampling and custom confidence threshold:
```bash
python voras.py --mode check-only --sample-rate 0.1 --confidence-threshold 0.8
```

Dry run to see what would be populated:
```bash
python voras.py --mode populate-only --language lt --dry-run
```

**Output:**

The agent provides:
- **Coverage mode**: Overall statistics, per-language coverage, difficulty level breakdown
- **Check-only mode**: Translation validation issues with suggested corrections and confidence scores
- **Populate-only mode**: Number of translations populated and any failures
- **Both mode**: Combined validation issues and population statistics

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
