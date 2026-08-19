# Greenland - Current Status

## Repository Overview

**Greenland** is a multilingual linguistic database system designed to create, validate, and manage comprehensive language learning data. The project serves as the data generation pipeline and quality assurance infrastructure for the Trakaido language-learning application, producing structured vocabulary, translations, audio, and grammatical content across multiple languages.

## Core Purpose

Greenland's primary mission is to generate high-quality **WireWord export files** - structured JSON data containing vocabulary entries with translations, definitions, pronunciation, audio files, example sentences, and grammatical metadata. These exports power the Trakaido mobile and web applications, enabling learners to study Lithuanian, Chinese, French, Spanish, and other languages.

## Architecture

### Database Layer

The system centers around a SQLite database (`data/wordfreq/linguistics.sqlite`) managed via SQLAlchemy ORM. The schema (in `src/storage/`) defines models for:

- Word entries with multi-language translations
- Definitions and usage examples
- Pronunciation data (IPA phonetics)
- Audio file references
- Grammatical forms (declensions, conjugations)
- Sentence-word relationships
- Synonyms and alternative forms

### Agent-Based Processing

Greenland uses a collection of **specialized processing agents** (named after Lithuanian animals) that perform bulk operations against the database, typically involving LLM calls for linguistic validation and generation:

**Core Validation & Processing:**
- **lokys** - Thin CLI wrapper for `words.validation`
- **dramblys** - Missing word detection; pending-import review CLI for `words.pending_imports`
- **vilkas** - Thin CLI wrapper for `words.inflections`
- **voras** - Thin CLI wrapper for `words.translation` / `words.translation_workflow`
- **papuga** - Thin CLI wrapper for `words.pronunciation`
- **sernas** - Thin CLI wrapper for `words.synonyms`
- **lape** - Thin CLI wrapper for `words.grammar_facts`

**Audio Generation:**
- **strazdas** - eSpeak-NG audio generation (open-source TTS)
- **vieversys** - OpenAI TTS audio generation (high-quality voices)

**Export & Utilities:**
- **ungurys** - WireWord export generation
- **bebras** - Database integrity and compatibility entry points
- **buivolas** - Discovers pattern/LLM sentence generation work
- **zvirblis** - Discovers missing sentence translations
- **sarka** - Plans bulk vocabulary-driven conversations

Sentence and conversation implementations live under `src/sentences/`.
The animal-named CLIs are queue-first wrappers; workers execute canonical
function-named tasks such as `sentences.examples.generate`,
`sentences.translate`, and `conversations.generate`.

Lemma enrichment finders enqueue canonical `words.*` capabilities with
capability-named deduplication keys. New word payloads use `lemma_id`,
`language_code` for a single language, and `languages` for a set; workers retain
older animal task names and `lang_code` payloads only for persisted-work
compatibility.

Reusable lemma enrichment logic lives under `src/words/`. Animal-named modules
under `src/agents/` contain command-line orchestration and display code only;
Barsukas and canonical workqueue handlers import the domain modules directly.

Agent CLIs use shared argument helpers from `src/agents/common/common_args.py`.
Sentence finders enqueue by default and accept `--execute-inline` for deliberate
foreground debugging.

### Web Interface (Barsukas)

`src/barsukas` provides a Flask-based web UI for human interaction with the database. This interface allows linguists and contributors to:

- Browse and search vocabulary entries
- Edit translations and definitions
- Review and approve generated content
- Manage word relationships
- Quality control and validation

Barsukas also hosts the **Trakaido activities** (`/trakaido/activities/`):
server-rendered, multi-language versions of the Trakaido web study modes
(spelling quiz, category choice, sentence completion, multiple choice,
listening, flashcards, typing, verb forms). These are stateless and take only
a level parameter — the selected level acts as a ceiling, with lower-level
words quizzed less often. Per-user stat tracking stays in the Trakaido apps
(which are migrating to Lithuanian-only); a lightweight sessionStorage-based
practice session (accuracy, streaks) is shared across the Greenland
activities client-side.

### Language Support

The system maintains comprehensive language code mappings in `src/storage/translation_helpers.py`, which serves as the single source of truth for:

- LLM field-to-language-code conversions
- Language code standardization
- Multi-lingual response parsing

Currently supported target languages include Lithuanian, Chinese (simplified), French, Spanish, German, Italian, Dutch, Portuguese, and Swedish.

## Technical Infrastructure

- **Primary Language**: Python with type hinting requirements
- **PYTHONPATH**: Set to `src/` for all script execution
- **Database**: SQLAlchemy with SQLite backend
- **LLM Integration**: `src/clients/` contains adapters for ChatGPT, Claude, and Gemini
- **Configuration**: DataSourceConfig objects (from `src/storage/backend/config.py`) pass db_path, model_name, and other settings
- **Code Quality**: Black formatting and mypy type checking enforced via pre-commit hooks

## Development Workflow

All Python scripts use absolute imports (`from agents.common_args import`) and are invoked with explicit PYTHONPATH:

```bash
PYTHONPATH=src python src/agents/dramblys.py --help
```

The project emphasizes:
- Type hints on all new code (except benchmarks)
- No variable name reuse within functions
- Absolute imports only
- Pre-commit hooks for black/mypy validation
- Tests in `src/tests/` for client code

## Data Release Pipeline

Word data is stored in `data/release/` files organized by language and GUID prefix. These files:

- Maintain sorted order by GUID
- Use GUID prefixes defined in `storage/models/guid_prefixes.py`
- Store words in lemma form with difficulty levels
- Include disambiguation when necessary
- Leave gaps for removed words (GUIDs are immutable). Retirements are recorded in
  `data/release/tombstones/guid_tombstones.jsonl`, which `storage.utils.guid` reads so a
  retired GUID is never issued to a different word

The release files are processed by export agents to generate the final WireWord JSON consumed by Trakaido applications.

## Current State

Greenland is a mature data generation and quality assurance system that has produced comprehensive multilingual datasets for production language learning applications. The agent-based architecture enables continuous improvement and expansion of linguistic content while maintaining data quality through LLM-assisted validation and human review workflows.
