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
| **sarka** | magpie | Dialog/conversation generator (bulk, keyword-driven) |
| **povas** | peacock | HTML report generator |
| **ungurys** | eel | WireWord API export |
| **elnias** | deer | Bootstrap export (minimal format) |
| **strazdas** | thrush | Audio generation (eSpeak-NG) |
| **vieversys** | lark | Audio generation (OpenAI TTS) |
| **seskas** | ferret | Multi-model verb-conjugation consensus generator |
| **erelis** | eagle | False lemma match detection in sentences |
| **gandras** | stork | Audio manifest downloader (S3 staging) |
| **genys** | woodpecker | Document parser and pending import stager |
| **ozys** | billy goat | Story-library text generator (retellings, learner conversations) |
| **gegute** | cuckoo | Idiom generator, equivalent populator, and equivalent auditor |

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
--persona NAME      Barsukas persona whose main database to use
                    (prod, golden, hosted, local, local-sqlite, scholar)
--backend TYPE      [requires --persona custom] Storage backend: sqlite, jsonl, postgres
--data-dir DIR      [requires --persona custom] Data directory for the jsonl backend
--postgres          [requires --persona custom] Shorthand for --backend postgres
```

Select the database with `--persona`; the default (no persona) is the local
SQLite database. `--persona custom` unlocks the manual backend flags for
development setups that need to spell out the backend directly.

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

Bulk, keyword-driven dialog generation: picks words at a level and writes
conversations around them, aiming for each word to be used about twice.

```bash
sarka.py --generate --level 3                 # 12 dialogs for level 3
sarka.py --generate --level 3 --by-category   # Keep noun categories coherent
sarka.py --generate --max-level 5 --num-sentences 10
sarka.py --show-words --level 3               # What vocabulary is available
sarka.py --stats                              # Conversation counts by level
```

For a *specific* scene ("buying tomatoes at the grocery store") rather than
level coverage, use the Barsukas-first flow instead: Conversations → New
Dialog, which enqueues `conversations.scene.generate` and stores word links,
a derived difficulty level, and a coverage report of the words the dictionary
is missing. See `docs/dialog_generation.md`.

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

### erelis (False Lemma Matches)

```bash
erelis.py --language zh               # Detect false lemma matches in Chinese
erelis.py --language zh --limit 100   # Limit number of sentences checked
erelis.py --language zh --guid V03_007
```

### gandras (Audio Manifest Downloader)

```bash
gandras.py --mode list                # Show available S3 manifests
gandras.py --mode report --language lt
gandras.py --mode download --language lt --voice ruta --output-dir audio/
```

### genys (Document Import)

```bash
genys.py --input document.txt --language en
genys.py --input document.txt --language zh --store-sentences
```

### gegute (Idioms)

Generates idioms, fills in their cross-language equivalents, and audits the
equivalents already stored. Execution lives in `workqueue/handlers/idioms/`
under the canonical task names `idioms.generate`,
`idioms.equivalents.populate`, and `idioms.equivalents.validate`; the
generation library itself is `src/idioms/generation.py`.

```bash
gegute.py --coverage                          # Equivalent coverage report (default)
gegute.py --coverage --source-language en     # Only English-sourced idioms

gegute.py --generate --source-language lt --count 10
gegute.py --generate --source-language en --theme "work and money"

gegute.py --populate --guid M01_003           # Fill missing equivalents for one idiom
gegute.py --populate --language ja ko         # Only these target languages
gegute.py --populate --all-languages          # Regenerate, not just missing

gegute.py --validate --guid M01_002           # Audit stored equivalents (read-only)

gegute.py --populate --use-workqueue          # Enqueue instead of running inline
```

`--validate` reports problems rather than applying corrections: the findings
name an equivalent id for a human to act on, so an unreviewed LLM call cannot
overwrite curated data.

## Creating New Agents

See `STYLE.md` for architecture patterns and conventions. Key points:

1. Use Lithuanian animal name that metaphorically represents the function
2. Use `agents/common/common_args.py` for standardized CLI arguments
3. Use `agents/common/lemma_selection.py` for database queries
4. Support `--check` (read-only), `--fix`, and `--dry-run` modes
5. Be idempotent (safe to run multiple times)
6. Require confirmation for destructive operations (unless `--yes`)
