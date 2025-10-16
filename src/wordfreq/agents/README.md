# WordFreq Agents

Autonomous agents for data quality monitoring and maintenance tasks. These agents are designed to run without user interaction, making them suitable for scheduled cron jobs or continuous monitoring.

## Available Agents

### Lokys (Translation and Lemma Validation)

**Name:** "Lokys" means "bear" in Lithuanian - thorough and careful in checking quality.

**Purpose:** Validates multi-lingual translations for correctness and ensures English lemma forms are in proper dictionary/base form (e.g., "shoe" not "shoes").

**Usage:**
```bash
python lokys.py [--check CHECK_TYPE] [--language LANG] [--output REPORT.json] [--model MODEL]
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
