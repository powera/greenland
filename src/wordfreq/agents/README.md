# WordFreq Agents

Autonomous agents for data quality monitoring and maintenance tasks. These agents are designed to run without user interaction, making them suitable for scheduled cron jobs or continuous monitoring.

## Quick Reference

- **Pradzia** (beginning) - Initializes and maintains the wordfreq database, including corpus configuration synchronization, data loading, and rank calculation.
- **Lokys** (bear) - Validates English lemma forms and other English-language properties (definitions, POS types).
- **Dramblys** (elephant) - Identifies missing words by scanning frequency corpora and can automatically process them using LLM to add to the database.
- **Bebras** (beaver) - Ensures database structural integrity by identifying orphaned records, missing fields, and constraint violations.
- **Voras** (spider) - Validates multi-lingual translations for correctness, reports on coverage, and can populate missing translations using LLM.
- **Vilkas** (wolf) - Monitors the presence and completeness of word forms across multiple languages in the database and can automatically generate missing forms.
- **Papuga** (parrot) - Validates and generates pronunciations (both IPA and simplified phonetic) for derivative forms.
- **Povas** (peacock) - Generates HTML pages displaying words organized by part-of-speech subtypes with comprehensive linguistic information.
- **Ungurys** (eel) - Exports word data to WireWord API format for external system integration.

## Available Agents

### Pradzia (Database Initialization Agent)

**Name:** "Pradzia" means "beginning" in Lithuanian - the starting point for all data!

**Purpose:** Initializes and maintains the wordfreq database, including corpus configuration synchronization, data loading, and rank calculation.

**Usage:**
```bash
# Check configuration and database state (no changes)
python pradzia.py --check [--output REPORT.json]

# Sync corpus configurations to database
python pradzia.py --sync-config [--dry-run]

# Load corpora
python pradzia.py --load [CORPUS1 CORPUS2 ...] [--dry-run]

# Calculate combined ranks
python pradzia.py --calc-ranks [--dry-run]

# Full initialization (sync + load + calc ranks)
python pradzia.py --init-full [--dry-run]
```

**Modes:**
- `--check` - Check configuration and database state without making changes
- `--sync-config` - Synchronize corpus configurations from config file to database
- `--load [CORPUS...]` - Load specified corpora (or all enabled if none specified)
- `--calc-ranks` - Calculate combined ranks for all words across corpora
- `--init-full` - Perform complete database initialization (all steps)

**Options:**
- `--dry-run` - Report what would be done without making changes
- `--output FILE` - Write detailed JSON report to specified file
- `--db-path PATH` - Use custom database path
- `--debug` - Enable debug logging

**Example Usage:**

Check configuration and database state:
```bash
python pradzia.py --check --output /tmp/pradzia_report.json
```

Sync corpus configurations (dry run):
```bash
python pradzia.py --sync-config --dry-run
```

Load specific corpora:
```bash
python pradzia.py --load subtlex_uk coca
```

Load all enabled corpora:
```bash
python pradzia.py --load
```

Calculate combined ranks:
```bash
python pradzia.py --calc-ranks
```

Full database initialization (dry run):
```bash
python pradzia.py --init-full --dry-run
```

Full database initialization:
```bash
python pradzia.py --init-full
```

**Output:**

The agent provides:
- Configuration validation results
- File existence status for corpus data files
- Database corpus information
- Synchronization results (added, updated, disabled corpora)
- Corpus loading results (imported counts per corpus)
- Rank calculation success/failure status
- Optional JSON report with full details

**Initialization Steps:**

When running `--init-full`, the agent performs these steps:
1. Ensures database tables exist
2. Syncs corpus configurations from config to database
3. Loads all enabled corpora
4. Calculates combined ranks using harmonic mean

---

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

### Vilkas (Multi-language Word Forms Checker)

**Name:** "Vilkas" means "wolf" in Lithuanian - a watchful guardian of the word database.

**Purpose:** Monitors the presence and completeness of word forms across multiple languages in the database, and can automatically generate missing forms.

**Supported Languages:**
- Lithuanian (lt): noun declensions, verb conjugations, adjective forms
- French (fr): verb conjugations, noun declensions
- German (de): verb conjugations, noun declensions
- Spanish (es): verb conjugations, noun declensions
- Portuguese (pt): verb conjugations, noun declensions
- English (en): verb conjugations

**Usage:**
```bash
# Check/reporting mode (no changes made)
python vilkas.py [--check CHECK_TYPE] [--output REPORT.json]

# Fix mode (generate missing forms)
python vilkas.py --fix [--pos-type TYPE] [--limit N] [--dry-run]
```

**Check Mode (Reporting Only):**
- `--check base-forms` - Check for lemmas with translations but missing derivative forms (default: Lithuanian)
- `--check noun-declensions` - Check noun declension coverage (nouns with only base forms)
- `--check verb-conjugations` - Check verb conjugation coverage (verbs with only infinitive)
- `--check all` - Run all checks and generate comprehensive report (default)

**Fix Mode (Generate Missing Forms):**
- `--fix` - Enable fix mode to generate missing word forms
- `--language LANG` - Language code for form generation (default: lt). Supported: lt, fr, de, es, pt, en
- `--pos-type TYPE` - Part of speech to fix (e.g., noun, verb, adjective). Defaults vary by language.
- `--limit N` - Maximum number of lemmas to process
- `--model MODEL` - LLM model to use for generation (default: gpt-5-mini)
- `--throttle SECONDS` - Seconds to wait between API calls (default: 1.0)
- `--source SOURCE` - Source for forms: llm (default) or wiki (Wiktionary, for Lithuanian nouns only)
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
python vilkas.py --fix --language lt --dry-run
```

Generate missing French verb conjugations:
```bash
python vilkas.py --fix --language fr --pos-type verb --limit 50 --yes
```

Generate missing German noun declensions:
```bash
python vilkas.py --fix --language de --pos-type noun --yes
```

Generate forms using Wiktionary instead of LLM (Lithuanian nouns only):
```bash
python vilkas.py --fix --language lt --source wiki --yes
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

### Papuga (Pronunciation Validation and Generation)

**Name:** "Papuga" means "parrot" in Lithuanian - repeating sounds with perfect accuracy!

**Purpose:** Validates existing pronunciations (IPA and simplified phonetic) for correctness and generates missing pronunciations for derivative forms.

**Usage:**
```bash
# Check/reporting mode (no changes made)
python papuga.py [--check] [--output REPORT.json]

# Populate mode (generate missing pronunciations)
python papuga.py --populate [--limit N] [--dry-run]

# Both modes (check existing AND populate missing)
python papuga.py --both [--limit N] [--dry-run]
```

**Modes:**
- `--check` - Validate existing pronunciations only (default, no database changes)
- `--populate` - Generate missing pronunciations and update database
- `--both` - Validate existing pronunciations AND populate missing ones

**Options:**
- `--output FILE` - Write detailed JSON report to specified file
- `--model MODEL` - LLM model to use (default: gpt-5-mini)
- `--limit N` - Maximum items to check/process
- `--sample-rate RATE` - Fraction of items to sample for validation (0.0-1.0, default: 1.0)
- `--confidence-threshold THRESHOLD` - Minimum confidence to flag issues (0.0-1.0, default: 0.7)
- `--all-languages` - Check all languages (default: English only)
- `--base-forms-only` - Only process base forms (populate mode only)
- `--dry-run` - Show what would be done without making changes (populate mode only)
- `--yes`, `-y` - Skip confirmation prompt before running LLM queries
- `--db-path PATH` - Use custom database path
- `--debug` - Enable debug logging

**Example Usage:**

Check existing pronunciations with report:
```bash
python papuga.py --check --output /tmp/papuga_report.json
```

Check with sampling:
```bash
python papuga.py --check --sample-rate 0.1 --yes
```

Generate missing pronunciations (dry run):
```bash
python papuga.py --populate --dry-run
```

Generate missing pronunciations for base forms only:
```bash
python papuga.py --populate --base-forms-only --limit 50 --yes
```

Validate and populate:
```bash
python papuga.py --both --limit 100 --yes
```

**Output:**

The agent provides:
- **Check mode**:
  - Count of pronunciations validated
  - Issues found with existing pronunciations
  - Suggested corrections for IPA and phonetic pronunciations
  - Count of forms missing pronunciations
- **Populate mode**:
  - Number of pronunciations successfully generated
  - Number of failures
  - Generated IPA and phonetic pronunciations

**Pronunciation Formats:**
- **IPA**: International Phonetic Alphabet with stress markers (e.g., `/ˈwɜːrd/`)
- **Phonetic**: Simplified readable format with hyphens and CAPS for stress (e.g., `WURD`)

---

### Povas (HTML Generation for POS Subtypes)

**Name:** "Povas" means "peacock" in Lithuanian - beautiful displays of information!

**Purpose:** Generates static HTML pages displaying all words organized by part-of-speech subtypes in tabular form with comprehensive linguistic information including definitions, translations, pronunciations, and example sentences.

**Usage:**
```bash
python povas.py [--index-only] [--db-path PATH] [--debug]
```

**Options:**
- `--index-only` - Generate only the index page (faster, useful for quick updates)
- `--db-path PATH` - Use custom database path
- `--debug` - Enable debug logging

**Example Usage:**

Generate all POS subtype HTML pages:
```bash
python povas.py
```

Generate only the index page:
```bash
python povas.py --index-only
```

Generate with debug logging:
```bash
python povas.py --debug
```

**Output:**

The agent generates:
- **Index page** (`pos_subtypes/index.html`) - Overview of all parts of speech with statistics
- **POS type pages** (e.g., `pos_subtypes/noun.html`) - Lists all subtypes for a specific POS
- **POS subtype pages** (e.g., `pos_subtypes/noun_common.html`) - Detailed word tables for each subtype
- **Static assets** - CSS and JavaScript files for interactive features

All files are written to `{OUTPUT_DIR}/pos_subtypes/` (configured in `constants.OUTPUT_DIR`).

**Features:**
- Sortable and filterable word tables
- Multiple translations (Chinese, French, Korean, Swahili, Lithuanian, Vietnamese)
- Phonetic and IPA pronunciations
- Example sentences
- Frequency rankings
- Grammatical form information

---

### Ungurys (WireWord Export Agent)

**Name:** "Ungurys" means "eel" in Lithuanian - swimming data downstream to external systems!

**Purpose:** Exports word data to WireWord API format for external system integration. Replaces the legacy "export wireword" functionality from trakaido/utils.py.

**Usage:**
```bash
# Directory export (default) - creates organized file structure
python ungurys.py [--output-dir DIR]

# Single-file export
python ungurys.py --mode single --output FILE.json

# Both modes
python ungurys.py --mode both --output FILE.json --output-dir DIR
```

**Modes:**
- `--mode directory` - Export to organized directory structure (default)
  - Creates `{OUTPUT_DIR}/wireword/by_level/` with files for each level (level_01.json, level_02.json, etc.)
  - Creates `{OUTPUT_DIR}/wireword/by_subtype/` with files for each subtype
  - Creates `{OUTPUT_DIR}/wireword/complete.json` with all words
- `--mode single` - Export to a single JSON file
- `--mode both` - Perform both single-file and directory exports

**Options:**
- `--output FILE` - Output path for single-file export (required for single/both modes)
- `--output-dir DIR` - Output directory for directory export (defaults to constants.OUTPUT_DIR)
- `--level N` - Filter by specific difficulty level
- `--pos-type TYPE` - Filter by specific POS type (e.g., noun, verb)
- `--pos-subtype SUBTYPE` - Filter by specific POS subtype
- `--limit N` - Limit number of results
- `--include-without-guid` - Include lemmas without GUIDs (default: False)
- `--include-unverified` - Include unverified entries (default: True)
- `--db-path PATH` - Use custom database path
- `--debug` - Enable debug logging

**Example Usage:**

Export all words to directory structure:
```bash
python ungurys.py
```

Export to custom directory:
```bash
python ungurys.py --output-dir /path/to/output
```

Export single file with all words:
```bash
python ungurys.py --mode single --output /tmp/wireword.json
```

Export only level 5 words:
```bash
python ungurys.py --mode single --output /tmp/level5.json --level 5
```

Export only nouns:
```bash
python ungurys.py --mode single --output /tmp/nouns.json --pos-type noun
```

Export both formats:
```bash
python ungurys.py --mode both --output /tmp/wireword.json --output-dir /tmp/wireword_dir
```

**Output:**

The agent provides:
- **Directory mode**: Organized file structure with separate files for each level and subtype
- **Single-file mode**: Complete export in one JSON file
- Export statistics including file counts, word counts, and level/subtype coverage
- WireWord format includes:
  - GUID, base Lithuanian/English forms
  - Corpus and group assignments
  - Difficulty levels
  - Word types (POS)
  - Alternative forms and synonyms
  - Grammatical forms (verb conjugations, noun declensions)
  - Frequency ranks and notes
  - Tags for filtering and organization

**WireWord Format Structure:**
```json
{
  "guid": "550e8400-e29b-41d4-a716-446655440000",
  "base_lithuanian": "katė",
  "base_english": "cat",
  "corpus": "WORDS1",
  "group": "Animal",
  "level": 2,
  "word_type": "noun",
  "grammatical_forms": {
    "plural_nominative": {
      "level": 4,
      "lithuanian": "katės",
      "english": "cats"
    }
  },
  "frequency_rank": 1234,
  "tags": ["animal", "level_2", "verified"]
}
```

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
