# Agents

Animal-named compatibility CLIs for database work discovery and maintenance.
Long-running sentence and lemma execution is dispatched by capability-named
workqueue handlers under `src/workqueue/handlers/`.

Run agents with: `PYTHONPATH=src python src/agents/<agent>.py --help`

## Architecture direction

Agent CLIs are moving toward **work discovery and enqueueing** entry points.
Sentence implementations live in `src/sentences/`; word implementations live
in `src/words/` or behind `src/workqueue/handlers/words/`. Old animal imports
remain available for compatibility, but queue tasks and deduplication keys use
capability names such as `words.forms` and `words.pronunciations`.

## Quick Reference

| Agent | Lithuanian | Purpose |
|-------|-----------|---------|
| **bebras** | beaver | Database integrity (orphans, missing fields, duplicates) |
| **lokys** | bear | English lemma validation (dictionary form, definitions) |
| **dramblys** | elephant | Missing words detector, JSONL import |
| **voras** | spider | Translation validator/populator (10 languages) |
| **vilkas** | wolf | Word forms checker (conjugations, declensions for 6 languages) |
| **papuga** | parrot | Pronunciation validation/generation (IPA, phonetic) |
| **sernas** | boar | Synonym and alternative form generator |
| **lape** | fox | Grammar facts (measure words, gender, declension class) |
| **zvirblis** | sparrow | Finds translations missing from existing sentences |
| **buivolas** | buffalo | Finds pattern or LLM example-generation work |
| **sarka** | magpie | Plans bulk, vocabulary-driven conversations |
| **povas** | peacock | HTML report generator |
| **ungurys** | eel | Compatibility wrapper for `exports.wireword` |
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
--languages LANG [LANG ...]
                    Filter by one or more language codes
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

# Pending import queue (implementation lives in words/pending_imports/)
dramblys.py --list-pending                    # Everything waiting for review
dramblys.py --list-pending --target-kind name # Only terms that become names
dramblys.py --approve 42                      # Create the lemma/name/concept
dramblys.py --reject 42                       # Drop it and exclude the word
```

A pending import becomes one of three things when approved: a **lemma**
(vocabulary), a **name** (proper noun, no difficulty), or a **concept**
(encyclopedia entry). Only the lemma path costs an LLM call. The kind is
guessed when the term is staged and can be changed on the Barsukas detail
page.

### voras (Translations)

```bash
voras.py --coverage                    # Report translation coverage (default)
voras.py --populate --languages fr es --limit 50
voras.py --populate --guid N07_008 --languages fr
voras.py --regenerate --use-workqueue --yes
```

### vilkas (Word Forms)

Supports: Lithuanian (lt), French (fr), German (de), Spanish (es), Portuguese (pt), English (en)

```bash
vilkas.py --task all --coverage
vilkas.py --task lt-noun-declensions --populate --use-workqueue
vilkas.py --task fr-verb-conjugations --populate --guid V03_007
vilkas.py --task en-noun-forms --populate --use-wiktionary
```

### papuga (Pronunciations)

```bash
papuga.py --coverage                   # Report missing pronunciations (default)
papuga.py --populate --use-workqueue
papuga.py --populate --languages fr es --base-forms-only --use-workqueue
papuga.py --coverage --all-languages
```

### sernas (Synonyms)

```bash
sernas.py --coverage --languages en fr
sernas.py --populate --languages en --use-workqueue
sernas.py --populate --type synonym --languages en
sernas.py --regenerate --languages en --yes
```

### lape (Grammar Facts)

```bash
lape.py --fact-type measure_words --languages zh --populate --use-workqueue
lape.py --fact-type grammatical_gender --languages de --populate
lape.py --fact-type declension_class --languages lt --coverage
lape.py --task verbs --languages en fr --populate --use-workqueue
```

Lemma task payloads use `lemma_id` as their target identifier. A task acting on
one language uses `language_code`; a task acting on a language set uses
`languages`. Workers still accept the former `lang_code` spelling when reading
persisted legacy tasks, but new producers must not emit it.

### zvirblis (Sentences)

```bash
zvirblis.py --guid N07_008 --languages lt zh fr
zvirblis.py --level 3 --translation-limit 5
zvirblis.py --guid N07_008 --use-translategemma
zvirblis.py submit-batch --languages lt zh fr --limit 100
```

Žvirblis does not create examples. It finds existing sentences linked to the
selected lemmas and queues `sentences.translate` (rich structured output) or
`sentences.translate.simple` (text-only TranslateGemma output). Batch discovery
queues `sentences.translate.batch_submit`. Add `--execute-inline` only for an
intentional foreground run.

### buivolas (Sentence examples)

```bash
python -m agents.buivolas --task generate-candidates --all-patterns --limit 100
python -m agents.buivolas --task generate-sentences --mode pattern --guid N06_001
python -m agents.buivolas --task generate-sentences --mode llm --level 3 --limit 10
python -m agents.buivolas --task generate-sentences --mode guided --guid N06_001
```

Buivolas discovers pattern or lemma targets and queues
`sentences.patterns.generate` or `sentences.examples.generate`. The generated
rows are English-first; other languages are added by the sentence translation
pipeline. Use `--execute-inline` for debugging only.

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

Generation and definition modes enqueue `conversations.generate` and
`conversations.definitions.generate` by default. Use `--execute-inline` for a
deliberate foreground LLM run. `--show-words`, `--view`, and `--stats` remain
read-only and execute immediately.

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

The implementation lives in `src/exports/wireword/`; these legacy commands
remain available as convenience wrappers. The canonical package command is
`PYTHONPATH=src python -m exports.wireword`.

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
vieversys.py --languages en           # Generate English audio
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
gegute.py --populate --languages ja ko        # Only these target languages
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
