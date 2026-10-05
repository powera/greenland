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

"Where" says where the real work happens: **queue** means the CLI finds work and
enqueues capability-named tasks (Barsukas workers execute them); **inline**
means the CLI does the work itself; **shim** means the code moved and the
animal name is only a compatibility wrapper.  "UI" marks agents that Barsukas
can launch or that back a Barsukas page.

| Agent | Lithuanian | Purpose | Where | UI | LLM |
|-------|-----------|---------|-------|----|-----|
| **bebras** | beaver | Integrity checks/fixes; translation verification; sentence-word linking | inline | yes | verify/link only |
| **lokys** | bear | English lemma/definition/disambiguation validation | inline | yes | yes |
| **dramblys** | elephant | Missing-word detection, pending-import queue (stage/approve/reject) | inline | yes | `--fix` only |
| **jonvabalis** | firefly | Reviews pending imports that propose a new head word | inline | no | yes |
| **voras** | spider | Translation coverage/population | queue, batch | yes | yes |
| **vilkas** | wolf | Word forms (lt, fr, de, es, es-419, pt, en) | queue, batch | yes | partly (mechanical first) |
| **papuga** | parrot | Pronunciations (IPA, simplified phonetic) | queue, batch | yes | yes |
| **sernas** | boar | Synonyms, abbreviations, expanded forms | queue | yes | yes |
| **lape** | fox | Grammar facts (measure words, gender, declension class, ...) | queue, batch | yes | yes |
| **gegute** | cuckoo | Idioms: generate, populate equivalents, audit equivalents | queue | yes | yes |
| **zvirblis** | sparrow | Translate existing sentences linked to lemmas | shim → `sentences/`, queue, batch | yes | yes |
| **buivolas** | buffalo | English example sentences (pattern / LLM / guided) | shim → `sentences/`, queue | yes | pattern: no |
| **sarka** | magpie | Bulk vocabulary-driven conversations | shim → `sentences/`, queue | yes | yes |
| **genys** | woodpecker | Parse a document into sentences and stage unknown words | inline | via workqueue | yes |
| **erelis** | eagle | False lemma links (lemma's translation absent from sentence translation) | inline | no | no |
| **ozys** | billy goat | Story-library texts (retellings, learner conversations) | inline | yes (Texts) | yes |
| **vovere** family | squirrel | Concept encyclopedia: generate / rank red links / create from Q-ids | inline, batch | yes (Concepts) | yes |
| **vieversys** | lark | Cloud TTS audio (OpenAI, Polly, Azure, Google, Gemini) | inline, queue | yes | TTS |
| **strazdas** | thrush | Local TTS audio (eSpeak-NG, Qwen3-TTS) | inline | yes | no |
| **gandras** | stork | Import S3 staging audio manifests into review records | inline | via helpers | no |
| **seskas** | ferret | Multi-model verb-conjugation consensus (local LM Studio models) | inline | no | yes (local) |
| **ungurys** | eel | WireWord export | shim → `exports.wireword` | yes | no |
| **elnias** | deer | Bootstrap export (minimal format) | shim → `exports.bootstrap` | yes | no |
| **povas** | peacock | POS-subtype HTML reports | shim → `exports.pos_reports` | yes | no |
| **gyvate** | snake | App string catalog export (import-only, no CLI) | shim → `exports.strings` | via `exports` | no |
| **veidrodis** | mirror | Template string catalogs (import-only, no CLI) | shim → `exports.strings` | no | no |

`agents/common/batch.py` (`status`, `complete`) checks and applies OpenAI batch
jobs submitted by any agent's `--batch` path.

## Usefulness review (October 2026)

**Core, actively used.**  voras, vilkas, papuga, lape, sernas, gegute and
zvirblis are the lemma/sentence enrichment pipeline: all are launched from
Barsukas, enqueue capability-named tasks, and (except sernas and gegute) have
a `--batch` path.  dramblys owns the pending-import queue that Barsukas review
pages and `api.lemmas.add_word` feed.  bebras `--check-integrity` backs the
Barsukas integrity page.  vieversys is the production audio path.

**Useful, narrower.**
- jonvabalis automates the slice of the pending-import queue (a few thousand
  rows) whose proposed head word is new.  Defaults to 10 rows per run on
  purpose; read the `--output` before raising `--limit`.
- genys is the document-import path (also run as the
  `sentences.import.document` task).
- gandras is needed whenever audio is generated on another machine.
- strazdas is the free/local audio path; quality is below vieversys.
- ozys and the vovere family serve the story library and concept
  encyclopedia; Barsukas Texts/Concepts pages call the same code.
- lokys's checks are still available, but Barsukas calls the underlying
  checks per-lemma (`/api/llm/lokys/...`); the bulk CLI is a candidate to be
  absorbed by a lemma-review batch job (see "Batching an agent").

**Low value / candidates for retirement.**
- seskas depends on local LM Studio models, which the project no longer
  expects to run; its only output in the tree is
  `src/langtools/de/generated_conjugations.py`.
- erelis has no Barsukas or workqueue integration and no tests; it is a cheap
  rule-based report, mostly useful for zh.
- bebras sentence mode (`--sentence`/`--file`) predates the `sentences/`
  pipeline (genys, zvirblis decomposition) and duplicates it; only
  `wordfreq/tools/sentence_word_linker.py` still imports it.
- ungurys, elnias, povas, gyvate, veidrodis, buivolas, sarka and zvirblis are
  compatibility wrappers (gyvate and veidrodis are imported only by
  `tests/test_exports_compatibility.py`).  New code should import from `exports/` and
  `sentences/` directly; the wrappers can go once Barsukas's launcher and the
  tests stop naming them.

## Common Arguments

Most agents use standardized arguments from `agents/common/common_args.py`
(each agent adds only the groups it needs; check `--help`):

```
--db-path PATH      Database path (default: from environment)
--debug             Enable debug logging
--yes, -y           Skip confirmation prompts
--dry-run           Preview changes without committing
--model MODEL       LLM model (default: constants.DEFAULT_MODEL)
--throttle SECS     Delay between API calls (default: 1.0)
--limit N           Maximum items to process
--sample-rate RATE  Fraction to process (0.0-1.0)
--guid GUID         Process single item by GUID
--level N           Filter by difficulty level (single or range like "1-9")
--pos-type TYPE     Filter by part of speech
--languages LANG [LANG ...]
                    Filter by one or more language codes
--barsukas-url URL  Query a Barsukas server for cached translations
--cache-only        Use only cached translations from --barsukas-url
--persona NAME      Barsukas persona whose main database to use
                    (prod, golden, hosted, local, local-sqlite, scholar, custom)
--backend TYPE      [requires --persona custom] Storage backend: sqlite, jsonl, postgres
--data-dir DIR      [requires --persona custom] Data directory for the jsonl backend
--postgres          [requires --persona custom] Shorthand for --backend postgres
```

Select the database with `--persona`; the default (no persona) is the local
SQLite database. `--persona custom` unlocks the manual backend flags for
development setups that need to spell out the backend directly.

Lemma agents that enqueue work take `--use-workqueue`; sentence agents
(zvirblis, buivolas, sarka) enqueue by default and take `--execute-inline` for
a foreground run.  Run anything exploratory under `GREENLAND_TEST_MODE=1` or
`GREENLAND_DISABLE_LLM=1` (see the top-level CLAUDE.md).

## Agent Details

### bebras (Integrity, Verification, Sentence Links)

`bebras.py` has three modes, chosen by a leading flag; `--help` shows the
help for whichever mode is selected (sentence mode by default).

```bash
# Integrity (no LLM) - backs the Barsukas integrity page
bebras.py --check-integrity                        # All checks (default)
bebras.py --check-integrity --check orphaned       # One check
bebras.py --check-integrity --check invalid-levels # Levels outside 1-199 (except -1)
bebras.py --check-integrity --check missing-punctuation --fix
```

Checks: `orphaned`, `missing-fields`, `english-base-forms`, `no-derivatives`,
`duplicates`, `duplicate-words`, `invalid-levels`, `missing-punctuation`,
`sentence-levels`, `audio-mismatches`, `pronunciation-fields`, `all`.  `--fix`
repairs english-base-forms, missing-punctuation, sentence-levels,
audio-mismatches and pronunciation-fields.

```bash
# Translation verification (LLM)
bebras.py --verify words --limit 100
bebras.py --verify sentences --limit 50
bebras.py --verify pronunciations --help

# Sentence-word linking (LLM; legacy - prefer genys / the sentences pipeline)
bebras.py --sentence "I eat a banana" --languages lt zh
bebras.py --file sentences.txt --languages lt zh
```

`submit-batch-words` / `submit-batch-sentences` are deprecated; queue
verification with `python -m verification words|sentences`.

### lokys (English Validation)

```bash
lokys.py                              # Check all English lemmas
lokys.py --sample-rate 0.1 --yes      # Check 10% sample
lokys.py --confidence-threshold 0.8   # Adjust confidence threshold
lokys.py --check-type definitions --level 1-5 --limit 50
```

`--check-type` is one of `lemma`, `definitions`, `disambiguation`, `both`
(default: all checks).

### dramblys (Missing Words / Import)

```bash
# Check mode
dramblys.py --check frequency         # Find high-frequency missing words
dramblys.py --check orphaned          # Find derivatives without parents
dramblys.py --check subtypes          # Check POS subtype coverage
dramblys.py --top-n 10000             # Check top N frequency words

dramblys.py --check-wordlist words.txt  # Which words in a file are missing

# Fix mode (process with LLM)
dramblys.py --fix --limit 20 --yes    # Process 20 missing words

# Stage instead of creating (no LLM until approval)
dramblys.py --stage --limit 50
dramblys.py --stage-words @words.txt  # One word per line, #-comments ignored
dramblys.py --add-subtype --pos-type noun --pos-subtype animals --stage-only

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

### jonvabalis (Pending-Import Review)

Reviews pending imports created by `api.lemmas.add_word` whose proposed
English head word is not yet a lemma ("world" was queried, the row proposes
"realm").  For each row the model answers `duplicate` (reject),
`distinct` (approve with the model's head word, definition, subtype,
translations and example) or `unsure` (left for a human); verdicts below 0.8
confidence are left queued.  Approval and rejection go through the same
`words.pending_imports.approval` path as Barsukas.

```bash
GREENLAND_TEST_MODE=1 jonvabalis.py --dry-run    # List rows, no LLM calls
jonvabalis.py --limit 10 --output review.json    # Default batch is 10
jonvabalis.py --pending-id 2924 --pending-id 2925
```

Suggested levels are only reported in `--output`; lemmas are stored without a
level until the anchors are trustworthy.

### voras (Translations)

```bash
voras.py --coverage                    # Report translation coverage (default)
voras.py --populate --languages fr es --limit 50
voras.py --populate --guid N07_008 --languages fr
voras.py --regenerate --use-workqueue --yes
voras.py --populate --languages fr --batch                   # OpenAI batches
```

### vilkas (Word Forms)

Supports: Lithuanian (lt), French (fr), German (de), Spanish (es, es-419),
Portuguese (pt), English (en).  `--task` names are `<lang>-<pos>-<forms>`
(e.g. `lt-adverb-forms`, `es-419-verb-conjugations`) or `all`.

```bash
vilkas.py --task all --coverage
vilkas.py --task lt-noun-declensions --populate --use-workqueue
vilkas.py --task fr-verb-conjugations --populate --guid V03_007
vilkas.py --task en-noun-forms --populate --use-wiktionary
vilkas.py --task fr-verb-conjugations --populate --batch     # OpenAI batches
```

### papuga (Pronunciations)

```bash
papuga.py --coverage                   # Report missing pronunciations (default)
papuga.py --populate --use-workqueue
papuga.py --populate --languages fr es --base-forms-only --use-workqueue
papuga.py --coverage --all-languages
papuga.py --populate --languages fr --batch                  # OpenAI batches
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
lape.py --task nouns --languages fr de --populate --batch      # OpenAI batches, half price
```

`--batch` sends every fact type except `english_principal_parts` through the
OpenAI Batch API; results are written as each batch completes (see "Batching
an agent" below).

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

Wrapper around `exports.bootstrap`.  Languages: fr, ko, lt, zh, zh-tw.

```bash
elnias.py                             # Export bootstrap data (Lithuanian)
elnias.py --language zh               # Export for Chinese
elnias.py --include-unverified        # Include unverified translations
```

### strazdas (Local TTS Audio)

Generates audio locally (no API cost) into `AudioQualityReview` rows with
`pending_review` status.  `--tts-backend espeak` (default, all languages) or
`qwen` (Qwen3-TTS, CJK + FIGS + PT).

```bash
strazdas.py --language lt                        # Coverage/generation for lt
strazdas.py --language lt --mode populate-only   # Generate missing only
strazdas.py --language zh --tts-backend qwen
strazdas.py --list-voices                        # List available voices
strazdas.py --language lt --voices Ona Jonas     # Specify voice names
strazdas.py --language lt --upload-s3            # Also upload to S3 staging
```

Modes: `check-existing`, `populate-only`, `regenerate`, `coverage`.

### vieversys (Cloud TTS Audio)

The production audio path.  `--tts-engine` is one of `openai` (default),
`polly`, `azure`, `google`, `gemini`.  Also runs as a workqueue task
(`workqueue/handlers/vieversys.py`) from Barsukas's audio pages.

```bash
vieversys.py --languages lt --mode coverage
vieversys.py --languages lt --mode populate-only --limit 50
vieversys.py --languages lt --voices alloy nova
vieversys.py --languages zh --tts-engine azure --upload-s3
vieversys.py --languages lt --generate-sentences --sentence-limit 20
```

`--auto-approve` marks generated audio approved and copies it to prod; leave
it off when the audio should go through review.  `--generate-manifests` is
deprecated.

### seskas (Verb Conjugation Consensus)

Asks several local LM Studio models (default `qwen3.5-9b-lms`, `phi-4-lms`,
`gemma-3-12b-lms`) for the same conjugation table and writes the consensus to
a Python module.  Requires those local models to be running.

```bash
seskas.py --language lt --verbs-file data/verbs/lt.txt
seskas.py --language es --verbs-file /tmp/es_verbs.txt --output src/langtools/es/generated_conjugations.py
seskas.py --language pl --verbs-file /tmp/pl_verbs.txt --model-paths qwen3-4b-lms phi-4-lms gemma-3-12b-lms
seskas.py --language lt --verbs-file /tmp/lt_verbs.txt --on-existing merge
```

### erelis (False Lemma Matches)

Rule-based (no LLM): flags sentences whose linked lemma's translation does not
appear in the sentence's translation.  Read-only report.

```bash
erelis.py --language zh               # Detect false lemma matches in Chinese
erelis.py --language zh --limit 100   # Limit number of sentences checked
erelis.py --language zh --guid V03_007
erelis.py --language zh --sentence-id 42 --verbose
erelis.py --language zh --stats       # Counts only
erelis.py --language zh --json
```

### gandras (Audio Manifest Import)

Imports S3 staging manifests (audio generated elsewhere) into local review
records.  No LLM.

```bash
gandras.py --mode list                # Show available S3 manifests
gandras.py --mode report --language lt   # Match statistics, no writes
gandras.py --mode download --language lt --voice ruta
gandras.py --mode download --language lt --fetch-audio --output-dir audio/
```

`download` imports metadata only unless `--fetch-audio` is given (MP3s are
served from S3).  Manifests marked rejected are skipped unless
`--import-rejected`.

### genys (Document Import)

```bash
genys.py --input document.txt --language en
genys.py --input document.txt --language zh --store-sentences
genys.py --input statute.txt --language en --tags legal
genys.py --input document.txt --language en --store-sentences --annotate-dependencies
```

Unknown words go to the pending-import queue (see dramblys).  The same code
runs as the `sentences.import.document` workqueue task.

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

### ozys (Story Library Texts)

Writes the text of an *authored* text work (fable, folk tale, fairy tale,
myth, legend, conversation) and stores it as a `TextVersion`.  Refuses
canonical works (poems, songs, speeches), whose texts are transcribed.  The
Barsukas Texts page calls the same agent.

```bash
ozys/ozys.py --slug The_Three_Billy_Goats_Gruff
ozys/ozys.py --slug At_the_Doctors_Office --difficulty 2 --dry-run
```

### vovere family (Concept Encyclopedia)

Command lines over `src/concepts/`.  These make live Wikidata/Wikipedia calls;
confirm before running them.

```bash
vovere/vovere.py --title "Art Deco" --summary "..." --source URL --model MODEL
vovere/voverukas.py --limit 30                     # Rank red links (read-only)
vovere/voverukas.py --limit 10 --resolve-qids      # Also cache Q-ids
vovere/voverukas.py --limit 10 --batch --model MODEL
vovere/voveraite.py Q8768 Q8743                    # Report seeds, no writes
vovere/voveraite.py Q8768 --create --model MODEL   # Create inline
vovere/voveraite.py Q8768 Q8743 --batch --model MODEL
vovere/voveraite.py Q103632 --sub --category chess_concept
```

- **vovere** generates one concept body from a title/summary/sources.
- **voverukas** ranks `[[wiki links]]` with no concept yet; `--create` /
  `--batch` turn the top results into concepts.
- **voveraite** creates concepts (or sub-concepts with `--sub`) from explicit
  Q-ids.

### common/batch.py (OpenAI Batch Results)

```bash
python -m agents.common.batch status --help
python -m agents.common.batch complete --help   # Apply finished batches
```

The Barsukas batch poller does the same automatically; use this when Barsukas
is not running.

## Creating New Agents

See `STYLE.md` for architecture patterns and conventions. Key points:

1. Use Lithuanian animal name that metaphorically represents the function
2. Use `agents/common/common_args.py` for standardized CLI arguments
3. Use `words/lemma_selection.py` (`get_lemmas_for_agent`) for lemma queries
4. Put the implementation in a domain package (`words/`, `sentences/`,
   `exports/`, `concepts/`) and keep the agent a thin CLI over it
5. Support a read-only/coverage mode, `--dry-run`, and (for LLM work)
   `--use-workqueue` or `--batch` rather than only inline execution
6. Be idempotent (safe to run multiple times)
7. Require confirmation for destructive operations (unless `--yes`)

## Batching an agent

`workqueue/llm_batch.py` runs an LLM job either live or as OpenAI batches with
the same code.  A job is one to three stages; each stage is two functions:

* `prepare(session, state, ctx)` returns an `LLMCall` (prompt, context,
  schema), a `Ready` answer that needs no model, or `Done` to stop.  It never
  writes.
* `apply(session, state, data, ctx)` writes from the model's answer and
  returns `Done`, or `Next(state)` to carry the item to the next stage.

Stages are barriers: stage N+1 is prepared and submitted, automatically, only
after every item of the run has finished stage N, so a stage-2 prompt can read
what stage 1 wrote for all items.  Progress lives on the `BatchQueue` rows in
the batch-tracking database.

To batch an agent:

1. Split its LLM step into prepare/apply functions in the domain module
   (`words/grammar_fact_tasks/` is the example), keeping its live path working
   on top of the same functions.
2. Declare a `Job` beside the agent's workqueue handler
   (`workqueue/handlers/words/grammar_facts.py`: `GRAMMAR_FACT_JOB`) and add it
   to `LLM_JOBS` in `workqueue/registry.py`.  The Barsukas batch poller and
   `python -m agents.common.batch complete` find it there; no dispatcher edits.
3. Add a `--batch` path to the CLI that builds item states and calls
   `start_batch_run` (dry run first to show counts, then confirm).

When the LLM call sits deep inside existing code (vilkas's generators try a
mechanical paradigm first), run that code in `prepare` with
`clients.deferring_client.DeferringClient`: it raises `DeferLLMCall` carrying
the exact call instead of making it, and code in between need only re-raise it.
A `prepare` that writes as it goes sets `Job.prepare_writes`.

Batched today, all through `workqueue/llm_batch.py`:

- lape (grammar facts);
- vilkas (forms);
- papuga (pronunciations, two stages: forms, then the translation from the
  filled base form);
- voras (translations);
- zvirblis and the Barsukas sentence batches (two stages: Phase 1 translation,
  then Phases 2+3 candidate lookup and decomposition; the optional Phase-4
  dependency pass is not part of the job).

Rows submitted before an agent moved to a staged job carry no run id; the
completion dispatchers send those to the agent's legacy applier until none are
left in flight.

Next candidates, best first:

1. lape lemma facts and `english_principal_parts`; sernas; sense prominence;
   dramblys's pending-import classification: one call per item each.
2. A lemma-review job (all of a lemma's data, "what's wrong?"), which would
   also absorb lokys's checks; it needs a findings table to write to first.
