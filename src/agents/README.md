# Agents

Autonomous agents for database maintenance and data processing. Named after Lithuanian animals. Designed for scheduled jobs or CI/CD pipelines.

Run agents with: `PYTHONPATH=src python src/agents/<agent>.py --help`

## Architecture direction

As of the queue-first transition, agent CLIs are moving toward **work discovery and enqueueing**, while execution is centralized in `src/workqueue/handlers/`. See `WORKQUEUE_REFACTOR_PLAN.md` for the migration plan and target architecture.

## Quick Reference

| Agent | Lithuanian | Purpose |
|-------|-----------|---------|
| **pradzia** | beginning | Database initialization, corpus sync, rank calculation |
| **bebras** | beaver | Database integrity (orphans, missing fields, duplicates) |
| **lokys** | bear | English lemma validation (dictionary form, definitions) |
| **dramblys** | elephant | Missing words detector, JSONL import |
| **voras** | spider | Translation validator/populator (10 languages) |
| **vilkas** | wolf | Word forms checker (conjugations, declensions for 6 languages) |
| **papuga** | parrot | Pronunciation validation/generation (IPA, phonetic) |
| **sernas** | boar | Synonym and alternative form generator |
| **lape** | fox | Grammar facts (measure words, gender, declension class) |
| **zvirblis** | sparrow | Example sentence generator |
| **buivolas** | buffalo | Example sentences (multi-language) |
| **sarka** | magpie | Dialog/conversation generator |
| **povas** | peacock | HTML report generator |
| **ungurys** | eel | WireWord API export |
| **elnias** | deer | Bootstrap export (minimal format) |
| **strazdas** | thrush | Audio generation (eSpeak-NG) |
| **vieversys** | lark | Audio generation (OpenAI TTS) |
| **seskas** | ferret | Multi-model verb-conjugation consensus generator |
| **vanagas** | hawk | External wordlist comparison (Cambridge YLE vs lemma DB) |

## Common Arguments

All agents use standardized arguments from `agents/common/common_args.py`:

```
--db-path PATH      Database path (default: from environment)
--debug             Enable debug logging
--yes, -y           Skip confirmation prompts
--dry-run           Preview changes without committing
--model MODEL       LLM model (default: gpt-5.4-mini)
--throttle SECS     Delay between API calls (default: 1.0)
--limit N           Maximum items to process
--sample-rate RATE  Fraction to process (0.0-1.0)
--guid GUID         Process single item by GUID
--level N           Filter by difficulty level (single or range like "1-9")
--language LANG     Filter by language code
--backend TYPE      Storage backend: sqlite, jsonl, postgres
--postgres          Shorthand for --backend postgres
```

## Agent Details

### pradzia (Database Initialization)

```bash
pradzia.py --check                    # Check config and database state
pradzia.py --sync-config              # Sync corpus configs to database
pradzia.py --load [CORPUS...]         # Load corpora (all enabled if none specified)
pradzia.py --calc-ranks               # Calculate combined frequency ranks
pradzia.py --init-full                # Full initialization (sync + load + ranks)
```

### bebras (Database Integrity)

```bash
bebras.py --check all                 # Run all integrity checks (default)
bebras.py --check orphaned            # Find orphaned records
bebras.py --check missing-fields      # Find missing required fields
bebras.py --check duplicates          # Find duplicate GUIDs
bebras.py --check invalid-levels      # Find levels outside 1-20
```

### lokys (English Validation)

```bash
lokys.py                              # Check all English lemmas
lokys.py --sample-rate 0.1 --yes      # Check 10% sample
lokys.py --confidence-threshold 0.8   # Adjust confidence threshold
```

### dramblys (Missing Words / Import)

```bash
# Check mode
dramblys.py --check frequency         # Find high-frequency missing words
dramblys.py --check orphaned          # Find derivatives without parents
dramblys.py --check subtypes          # Check POS subtype coverage
dramblys.py --top-n 10000             # Check top N frequency words

# Fix mode (process with LLM)
dramblys.py --fix --limit 20 --yes    # Process 20 missing words
```

### voras (Translations)

```bash
voras.py --mode coverage              # Report translation coverage (default)
voras.py --mode check-only            # Validate existing translations
voras.py --mode populate-only         # Add missing translations
voras.py --mode both                  # Validate and populate
voras.py --language fr --limit 50     # Process specific language
```

### vilkas (Word Forms)

Supports: Lithuanian (lt), French (fr), German (de), Spanish (es), Portuguese (pt), English (en)

```bash
vilkas.py --check all                 # Run all form checks
vilkas.py --check noun-declensions    # Check noun declension coverage
vilkas.py --check verb-conjugations   # Check verb conjugation coverage

vilkas.py --fix --language lt         # Generate Lithuanian forms
vilkas.py --fix --language fr --pos-type verb  # French verb conjugations
vilkas.py --fix --source wiki         # Use Wiktionary (Lithuanian nouns only)
```

### papuga (Pronunciations)

```bash
papuga.py --check                     # Validate existing pronunciations
papuga.py --populate                  # Generate missing pronunciations
papuga.py --both                      # Validate and populate
papuga.py --all-languages             # Check all languages (default: English)
papuga.py --base-forms-only           # Only process base forms
```

### sernas (Synonyms)

```bash
sernas.py --check all                 # Check all languages for missing synonyms
sernas.py --fix --language en         # Generate English synonyms
sernas.py --type synonym              # Only synonyms (not alternative forms)
sernas.py --type alternative_form     # Only alternative forms
```

### lape (Grammar Facts)

```bash
lape.py --task measure-word --language zh    # Chinese measure words
lape.py --task noun-gender --language de     # German noun gender
lape.py --task declension-class --language lt  # Lithuanian declension class
lape.py --task verb-transitivity --language en  # English verb transitivity
lape.py --task verb-reflexivity --language fr   # French reflexive verbs
```

### zvirblis (Sentences)

```bash
zvirblis.py --guid N07_008            # Generate sentences for specific word
zvirblis.py --level 3 --limit 10      # Generate for level 3 nouns
zvirblis.py --num-sentences 5         # Generate 5 sentences per word
zvirblis.py --languages en lt zh      # Specify target languages
```

### sarka (Dialogs)

```bash
sarka.py --level 3 --topic greetings  # Generate dialogs for topic at level
sarka.py --num-exchanges 5            # Number of dialog exchanges
```

### povas (HTML Reports)

```bash
povas.py                              # Generate all POS subtype HTML pages
povas.py --index-only                 # Generate only the index page
```

Output: `{OUTPUT_DIR}/pos_subtypes/`

### ungurys (WireWord Export)

```bash
ungurys.py                            # Export to directory structure
ungurys.py --mode single --output FILE.json   # Single file export
ungurys.py --mode both --output FILE.json     # Both formats
ungurys.py --level 5                  # Filter by level
ungurys.py --pos-type noun            # Filter by POS type
```

Output: `{OUTPUT_DIR}/wireword/`

### elnias (Bootstrap Export)

```bash
elnias.py                             # Export bootstrap data (Lithuanian)
elnias.py --language zh               # Export for Chinese
elnias.py --level 1-5                 # Filter by level range
```

### strazdas (eSpeak Audio)

```bash
strazdas.py --language lt             # Generate Lithuanian audio
strazdas.py --list-voices             # List available voices
strazdas.py --voices Ona Jonas        # Specify voice names
```

### vieversys (OpenAI TTS Audio)

```bash
vieversys.py --language en            # Generate English audio
vieversys.py --voice alloy            # Specify OpenAI voice
```

### seskas (Verb Conjugation Consensus)

```bash
seskas.py --language lt --verbs-file data/verbs/lt.txt
seskas.py --language es --verbs-file /tmp/es_verbs.txt --output src/langtools/es/generated_conjugations.py
seskas.py --language pl --verbs-file /tmp/pl_verbs.txt --model-paths qwen3-4b-lms phi-4-lms gemma-3-12b-lms
seskas.py --language lt --verbs-file /tmp/lt_verbs.txt --on-existing merge
```

### vanagas (YLE Wordlist Comparison)

Read-only, no LLM calls. Cross-references the Cambridge YLE wordlist
(`data/cambridge/yle_wordlist.json`, produced by `src/scripts/extract_yle_wordlist.py`)
against `Lemma.lemma_text` and reports coverage gaps, POS mismatches, excluded
lemmas, and difficulty outliers per YLE level.

```bash
vanagas.py                                # write text report to data/cambridge/yle_comparison_report.txt
vanagas.py --format json                  # write JSON to data/cambridge/yle_comparison_report.json
vanagas.py --levels starters --stdout     # starters only, print to stdout
vanagas.py --output /tmp/yle.txt          # override output path
```

Output: `data/cambridge/yle_comparison_report.{txt,json}`

## Creating New Agents

See `STYLE.md` for architecture patterns and conventions. Key points:

1. Use Lithuanian animal name that metaphorically represents the function
2. Use `agents/common/common_args.py` for standardized CLI arguments
3. Use `agents/common/lemma_selection.py` for database queries
4. Support `--check` (read-only), `--fix`, and `--dry-run` modes
5. Be idempotent (safe to run multiple times)
6. Require confirmation for destructive operations (unless `--yes`)
