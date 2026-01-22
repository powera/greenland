# Greenland

This document provides guidance for working with the Greenland codebase.

**Last Updated:** 2026-01-22
**Python Version:** 3.9+

---

## Table of Contents

1. [Project Overview](#project-overview)
2. [Quick Start](#quick-start)
3. [Repository Structure](#repository-structure)
4. [Core Modules](#core-modules)
5. [Database Architecture](#database-architecture)
6. [Development Workflows](#development-workflows)
7. [Testing](#testing)
8. [Common Tasks](#common-tasks)
9. [Important Paths](#important-paths)

---

## Project Overview

**Greenland** is a multi-faceted Python project focused on:

1. **Linguistic Database System (WordFreq)** - Multi-language word frequency and translation database with LLM-powered analysis supporting 14 languages
2. **LLM Benchmarking Suite** - Framework for testing and comparing language model capabilities
3. **Web-based Database Editor (Barsukas)** - Flask interface for managing the linguistics database

### Key Statistics

- **~57,000 lines** of Python code
- **14 languages** supported: English, Lithuanian, Chinese, French, German, Spanish, Portuguese, Korean, Swahili, Vietnamese, Japanese, Italian, Dutch, Swedish
- **14 autonomous agents** for database maintenance and quality assurance
- **SQLite-based** persistent storage with comprehensive ORM models

### Core Technologies

- **SQLAlchemy 2.0+** - Database ORM
- **Flask 3.0+** - Web framework
- **Pydantic 2.0+** - Data validation
- **Jinja2 3.1+** - Template engine
- **pytest 7.0+** - Testing framework

---

## Quick Start

### Environment Setup

```bash
# Install core dependencies
pip install -e .

# Install development dependencies
pip install -e ".[dev]"

# Install ML dependencies (optional)
pip install -e ".[ml]"
```

### Running Tests

```bash
# Run all tests
python run_tests.py

# Run tests in specific directory
python run_tests.py src/wordfreq
```

### Interactive Shell

```bash
# Python shell with preloaded linguistic tools
PYTHONPATH=src python -i src/interactive.py
# Provides: cl (LinguisticClient), rv (LinguisticReviewer), session, prcs (WordProcessor)
```

### Web Interfaces

```bash
# Barsukas - Database Editor (port 5555)
PYTHONPATH=src python src/barsukas/app.py
# Or use the launch script:
src/barsukas/launch.sh
```

---

## Repository Structure

```
greenland/
├── src/                        # All source code
│   ├── wordfreq/              # Linguistic database system ⭐ PRIMARY MODULE
│   │   ├── storage/           # Database layer (ORM, models, CRUD)
│   │   ├── translation/       # LLM-based translation and form generation
│   │   ├── frequency/         # Word frequency analysis
│   │   ├── dictionary/        # Word list management and export
│   │   ├── prompts/           # LLM prompt templates
│   │   ├── tools/             # CLI utilities (difficulty overrides, etc.)
│   │   ├── patterns/          # Sentence pattern definitions
│   │   ├── trakaido/          # Trakaido app integration
│   │   ├── templates/         # HTML templates for wordfreq
│   │   └── data/              # Data files (linguistics.sqlite, IPA dict)
│   │
│   ├── agents/                # Autonomous data quality agents ⭐
│   │   ├── pradzia.py         # Database initialization
│   │   ├── lokys.py           # English lemma validation
│   │   ├── dramblys.py        # Missing words detector
│   │   ├── bebras.py          # Database integrity checker
│   │   ├── voras.py           # Translation validator
│   │   ├── vilkas.py          # Word forms checker
│   │   ├── sernas.py          # Synonym/alternative form generator
│   │   ├── papuga.py          # Pronunciation validator
│   │   ├── zvirblis.py        # Example sentence generator
│   │   ├── povas.py           # HTML report generator
│   │   ├── ungurys.py         # WireWord export agent
│   │   ├── elnias.py          # WireWord bootstrap export
│   │   ├── buivolas.py        # Pattern-based sentence generator
│   │   ├── lape.py            # Grammar facts generator
│   │   ├── sarka.py           # Natural conversation generator
│   │   ├── strazdas.py        # eSpeak-NG audio generation
│   │   └── vieversys.py       # OpenAI TTS audio generation
│   │
│   ├── barsukas/              # Flask web interface for DB editing
│   │   ├── app.py             # Flask application entry point
│   │   ├── routes/            # Blueprint routes
│   │   ├── templates/         # Jinja2 HTML templates
│   │   └── static/            # CSS and JavaScript
│   │
│   ├── clients/               # Unified LLM client system
│   │   ├── unified_client.py  # Multi-provider LLM interface
│   │   ├── types.py           # Schema definitions
│   │   ├── batch_queue.py     # Batch processing
│   │   ├── openai_client.py   # OpenAI provider
│   │   ├── anthropic_client.py # Anthropic provider
│   │   ├── gemini_client.py   # Google Gemini provider
│   │   ├── ollama_client.py   # Ollama local models
│   │   └── lmstudio_client.py # LM Studio local models
│   │
│   ├── benchmarks/            # LLM benchmark suite
│   │   ├── lib/               # Benchmark framework (exemplars, generators, runners)
│   │   ├── server/            # Benchmark web server
│   │   ├── verbalator/        # LLM query web interface
│   │   ├── datastore/         # Benchmark results storage
│   │   ├── schema/            # Database schema
│   │   ├── run_benchmark.py   # Benchmark runner
│   │   ├── validation.py      # Input validation utilities
│   │   └── 0015_spell_check/, 0016_antonym/, etc.
│   │
│   ├── lib/                   # Shared libraries
│   │   ├── sentence_generation.py  # Sentence generation utilities
│   │   ├── advanced_queries.py     # Advanced query helpers
│   │   └── advanced_moderation.py  # Content moderation
│   │
│   ├── util/                  # General utilities
│   │   ├── prompt_loader.py   # Prompt template loading
│   │   ├── flesch_kincaid.py  # Readability calculations
│   │   ├── wiki_loader.py     # Wikipedia corpus processing
│   │   └── stopwords.py       # Stopword lists
│   │
│   ├── wireword/             # WireWord format export utilities
│   ├── langtools/            # Language processing tools
│   ├── audioshoe/            # Audio generation drivers (eSpeak, Piper, Coqui)
│   ├── tests/                # Test files
│   └── constants.py           # Centralized path configuration ⭐ IMPORTANT
│
├── prompts/                  # LLM prompt templates (top-level)
├── scripts/                  # Utility scripts (bootstrap, migrations)
├── data/                      # Static data files
│   ├── release/               # Release data files (wordlists, sentences)
│   ├── trakaido_wordlists/    # Difficulty-leveled wordlists
│   └── greenland_input/       # Input data files
│
├── templates/                 # Jinja2 templates for reports
├── public_html/              # Static web assets (CSS, JS, images)
├── docs/                     # Documentation
│   ├── difficulty_overrides.md
│   ├── API.md                 # API documentation
│   └── barsukas_agents.md     # Agent integration docs
├── audio/                    # Audio files and processing
├── hooks/                    # Git hooks (pre-commit for black)
│
├── pyproject.toml            # Project configuration
├── requirements.txt          # Python dependencies
├── run_tests.py              # Test runner
└── .gitignore
```

### Key Directories Explained

- **`src/wordfreq/`** - The heart of the project. Contains linguistic database, LLM translation clients, frequency analysis, and word list management
- **`src/agents/`** - Autonomous agents named after Lithuanian animals that maintain database quality
- **`src/barsukas/`** - Web UI for database editing (named after Lithuanian for "badger")
- **`src/clients/`** - Abstraction layer supporting OpenAI, Anthropic, Google, Ollama, and local models
- **`src/constants.py`** - **CRITICAL**: All path configuration lives here. Always check this file first when working with file paths

---

## Core Modules

### 1. WordFreq - Linguistic Database System

**Primary Purpose:** Comprehensive multi-language word frequency database with LLM-powered linguistic analysis.

**Key Components:**

#### `src/wordfreq/storage/`
Database layer with SQLAlchemy ORM:
- **`models/schema.py`** - Core data models (WordToken, Lemma, DerivativeForm, LemmaTranslation, Sentence, GrammarFact, etc.)
- **`database.py`** - Database session management and operations
- **`connection_pool.py`** - Thread-safe connection pooling
- **`crud/`** - CRUD operations organized by entity

#### `src/wordfreq/translation/`
LLM-based translation and linguistic form generation:
- **`client.py`** - Main LLM client for linguistic queries
- **`processor.py`** - Batch processing workflows
- **`generate_*_forms.py`** - Language-specific generators:
  - Lithuanian (verb conjugation, noun declension)
  - French (verb conjugation)
  - German (noun declension)
  - Spanish/Portuguese (verb conjugation)
  - English (verb conjugation)

#### `src/wordfreq/prompts/`
LLM prompt templates organized by task:
- `definitions/`, `pronunciation/`, `word_forms/`, `verb_conjugations/`, etc.
- Each contains `context.txt` and `prompt.txt`
- Loaded via `src/util/prompt_loader.py`

#### `src/wordfreq/frequency/`
Word frequency analysis:
- **`corpus.py`** - Corpus loading and processing
- **`analysis.py`** - Frequency ranking (harmonic mean across multiple corpora)
- **`importer.py`** - Import frequency data

#### `src/wordfreq/dictionary/`
Word list management and export:
- **`export_wordlist.py`** - Export tools
- **`reviewer.py`** - Interactive review interface

#### `src/wordfreq/tools/`
CLI utilities:
- **`word_categorizer.py`** - LLM-based word categorization
- **`manage_difficulty_overrides.py`** - Per-language difficulty management (see `docs/difficulty_overrides.md`)

### 2. Agents - Autonomous Data Quality System

**Philosophy:** Each agent is named after a Lithuanian animal and performs specific database maintenance tasks autonomously.

**Agent Design Principles:**
- **Autonomous**: No user interaction during execution
- **Idempotent**: Safe to run multiple times
- **Modes**: `--check` (read-only), `--fix` (repair), `--dry-run` (preview)
- **Reporting**: JSON output and console logging

**Agent Roster:**

| Agent | Animal | Purpose |
|-------|--------|---------|
| **pradzia** | Beginning | Database initialization and corpus management |
| **lokys** | Bear | English lemma validation |
| **dramblys** | Elephant | Missing words detector |
| **bebras** | Beaver | Database integrity checker (including sentence-word linking) |
| **voras** | Spider | Translation validator and populator |
| **vilkas** | Wolf | Word forms checker (conjugations, declensions) |
| **sernas** | Boar | Synonym and alternative form generator |
| **papuga** | Parrot | Pronunciation validation/generation |
| **zvirblis** | Sparrow | Example sentence generator |
| **buivolas** | Water Buffalo | Simple pattern-based sentence generator with batch translation |
| **lape** | Fox | Grammar facts generator (measure words, gender, etc.) |
| **strazdas** | Thrush | eSpeak-NG audio generation |
| **vieversys** | Lark | OpenAI TTS audio generation |
| **povas** | Peacock | HTML report generator |
| **ungurys** | Eel | WireWord export agent |
| **elnias** | Deer | WireWord bootstrap export |
| **sarka** | Magpie | Natural conversation sentence generator |

**Running Agents:**

```bash
cd src/agents

# Check mode (read-only report)
python voras.py --mode coverage

# Fix mode (make repairs)
python dramblys.py --fix --limit 20

# Check all word forms
python vilkas.py --check all

# Dry run (preview changes)
python sernas.py --dry-run
```

### 3. Barsukas - Web Database Editor

**Purpose:** Flask-based web interface for managing the linguistics database.

**Features:**
- Browse and edit lemmas, translations, difficulty levels
- AI-powered translation validation (Voras agent integration)
- WireWord export functionality
- Operation logging for all changes
- Read-only mode option

**Access:** `http://127.0.0.1:5555` (localhost only)

**Key Files:**
- `src/barsukas/app.py` - Flask application entry point
- `src/barsukas/routes/` - Blueprint routes:
  - `lemmas.py` - Lemma CRUD operations
  - `translations.py` - Translation management
  - `agents.py` - Agent integration
  - `exports.py` - WireWord export routes
  - `sentences.py` - Sentence management
  - `audio.py` - Audio generation routes
  - `api.py` - API endpoints
  - `rapid_review.py` - Rapid review interface
- `src/barsukas/templates/` - Jinja2 HTML templates
- `src/barsukas/static/` - CSS and JavaScript

### 4. Clients - Unified LLM Interface

**Purpose:** Abstraction layer for multiple LLM providers.

**Supported Providers:**
- **OpenAI** (GPT models)
- **Anthropic** (Claude models)
- **Google** (Gemini models)
- **Ollama** (local models)
- **LM Studio**
- Batch processing support

**Key Files:**
- `src/clients/unified_client.py` - Unified interface
- `src/clients/types.py` - Pydantic schema definitions
- `src/clients/batch_queue.py` - Batch processing queue

**Usage Pattern:**

```python
from clients.unified_client import UnifiedClient

client = UnifiedClient(model="gpt-4")
response = client.query(prompt="Translate 'hello' to French")
```

### 5. Benchmarks - LLM Evaluation Suite

**Purpose:** Framework for evaluating language model capabilities.

**Structure:**
- Individual benchmarks: `0015_spell_check/`, `0016_antonym/`, `0020_definitions/`, etc.
- `datastore/` - SQLite-based storage for results
- `schema/` - Database schema definitions

**Running Benchmarks:**

```bash
python -m lib.run_benchmark
```

---

## Database Architecture

### Primary Database: `linguistics.sqlite`

**Location:** `src/wordfreq/data/linguistics.sqlite` (see `src/constants.py:WORDFREQ_DB_PATH`)

**Core Tables:**

#### Word Storage
- **`word_tokens`** - Specific word spellings with frequency data
- **`lemmas`** - Base word meanings with definitions, translations, POS types
- **`derivative_forms`** - Links tokens to lemmas with grammatical info

#### Translations
- **`lemma_translations`** - Multi-language translations (Spanish, German, Portuguese)
- Some languages stored directly in `lemmas` table columns: Chinese, French, Korean, Swahili, Vietnamese

#### Difficulty Levels
- **`lemma_difficulty_overrides`** - Per-language difficulty levels (see `docs/difficulty_overrides.md`)
  - Allows different difficulty for same word in different languages
  - Level `-1` excludes word from that language
  - Coalesces with default `lemmas.difficulty_level`

#### Sentences
- **`sentences`** - Example sentences
- **`sentence_translations`** - Sentence translations
- **`sentence_words`** - Links sentences to vocabulary (many-to-many)

#### Grammar
- **`grammar_facts`** - Grammatical information
  - Synonyms
  - Alternative forms
  - Pronunciations (IPA)
  - Measure words (Chinese)

#### Frequency Data
- **`corpus`** - Corpus metadata
- **`word_frequency`** - Frequency data from multiple corpora

#### Audit
- **`operation_logs`** - Complete audit trail for all database changes

**Key Features:**
- Thread-safe connection pooling
- Hybrid translation storage (columns vs. separate table)
- Per-language difficulty overrides with coalescing
- Comprehensive operation logging

### Secondary Database: `benchmarks.db`

**Location:** `src/benchmarks/schema/benchmarks.db` (see `src/constants.py:SQLITE_DB_PATH`)

Stores benchmark results and model metadata.

---

## Development Workflows

### Branch Strategy

This project uses feature branches with a `claude/` prefix pattern:
- Branch names: `claude/claude-md-{session-id}`
- **CRITICAL:** Always develop on the designated branch
- Push to origin with `-u` flag: `git push -u origin <branch-name>`

### Git Workflow

```bash
# Check current branch
git status

# Create and checkout feature branch (if needed)
git checkout -b claude/feature-name-{session-id}

# Stage and commit changes
git add .
git commit -m "Description of changes"

# Push to remote
git push -u origin claude/feature-name-{session-id}
```

### Code Style

**Black Formatting:**
- Line length: **100 characters**
- Target: Python 3.9
- Run: `black src/`

**Type Hints:**
- Required for all function definitions (enforced by mypy)
- Run: `mypy src/`

**Import Organization:**
- Standard library imports first
- Third-party imports second
- Local imports last
- Alphabetical within each group

### Testing Philosophy

- **Test Discovery:** `run_tests.py` auto-discovers tests in `src/` and `tests/`
- **Naming:** Test files: `test_*.py`, Test functions: `test_*`
- **Colocation:** Tests can be colocated with source code or in separate `tests/` directory
- **Pytest:** Use pytest fixtures and markers

**Running Tests:**

```bash
# All tests
python run_tests.py

# Specific directory
python run_tests.py src/wordfreq

# Specific file
python run_tests.py src/wordfreq/test_storage.py
```

---

## Testing

### Test Organization

```
src/
├── wordfreq/
│   ├── test_storage.py
│   ├── test_frequency.py
│   └── storage/
│       └── test_models.py
└── tests/
    ├── clients/
    │   └── test_unified_client.py
    └── lib/
        └── test_validation.py
```

### Test Runner

**Primary:** `python run_tests.py`

**Features:**
- Auto-discovers all `test_*.py` files
- Accepts directory arguments
- Runs pytest underneath
- Colored output

### Writing Tests

**Pattern:**

```python
import pytest
from wordfreq.storage.models.schema import Lemma

def test_lemma_creation():
    lemma = Lemma(
        guid="N01_001",
        word="test",
        definition="A test word"
    )
    assert lemma.guid == "N01_001"
    assert lemma.word == "test"

@pytest.fixture
def sample_lemma():
    return Lemma(guid="N01_001", word="test")

def test_with_fixture(sample_lemma):
    assert sample_lemma.word == "test"
```

### Database Testing

**Pattern:** Use in-memory SQLite for tests

```python
from sqlalchemy import create_engine
from wordfreq.storage.models.schema import Base

@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
```

---

## Common Tasks

### Adding a New Lemma

```python
from wordfreq.storage.database import get_session
from wordfreq.storage.models.schema import Lemma
from wordfreq.storage.crud.operation_log import log_operation

with get_session() as session:
    lemma = Lemma(
        guid="N01_999",
        word="example",
        definition="An illustrative instance",
        part_of_speech="noun",
        difficulty_level=5
    )
    session.add(lemma)
    session.flush()

    log_operation(
        session=session,
        operation_type="insert",
        table_name="lemmas",
        record_id=lemma.id,
        details={"word": "example"}
    )
    session.commit()
```

### Generating Word Forms with LLM

```python
from wordfreq.translation.client import LinguisticClient

client = LinguisticClient(model="gpt-4")
forms = client.generate_verb_conjugations(
    verb="courir",
    language="French"
)
```

### Running Translation Validation

```bash
# Check translation coverage
cd src/agents
python voras.py --mode coverage

# Validate and populate missing translations
python voras.py --mode validate --fix --limit 50
```

### Exporting WireWord Format

```bash
# Export for specific language and level
cd src/agents
python ungurys.py --language zh --level 1-5

# Bootstrap export (all levels)
python elnias.py --language zh
```

### Managing Difficulty Overrides

```bash
# Set override for specific word
python src/wordfreq/tools/manage_difficulty_overrides.py set N01_123 zh 2 \
  --notes "Common in Chinese"

# Exclude from language
python src/wordfreq/tools/manage_difficulty_overrides.py set N01_456 de -1 \
  --notes "Not relevant for German"

# View overrides
python src/wordfreq/tools/manage_difficulty_overrides.py view N01_123

# List all overrides for language
python src/wordfreq/tools/manage_difficulty_overrides.py list zh

# Import from CSV
python src/wordfreq/tools/manage_difficulty_overrides.py import overrides.csv
```

### Checking Database Integrity

```bash
# Run integrity checks
cd src/agents
python bebras.py --check

# Fix integrity issues
python bebras.py --fix

# Check sentence-word linking
python bebras.py --check --mode sentence_linking
```

### Generating Example Sentences

```bash
# Generate sentences for words
cd src/agents
python zvirblis.py --fix --limit 20

# Check existing sentences
python zvirblis.py --check
```

### Creating HTML Reports

```bash
# Generate comprehensive reports
cd src/agents
python povas.py --output reports/
```

---

## Important Paths

All paths are defined in **`src/constants.py`**. Always reference this file.

### Key Constants

```python
# Project structure
SRC_DIR                  # /home/user/greenland/src
PROJECT_ROOT             # /home/user/greenland

# Databases
WORDFREQ_DB_PATH         # src/wordfreq/data/linguistics.sqlite
SQLITE_DB_PATH           # src/benchmarks/schema/benchmarks.db

# Directories
KEY_DIR                  # keys/ (gitignored - API keys)
TEMPLATES_DIR            # templates/ (Jinja2 templates)
OUTPUT_DIR               # ../greenland_output (external to repo)

# WordFreq specific
WORDFREQ_TEMPLATE_DIR    # src/wordfreq/templates/
IPA_DICT_PATH           # src/wordfreq/data/en_US_ipadict.txt

# Benchmarks
BENCHMARK_DATA_DIR       # src/benchmarks/
SCHEMA_DIR              # src/benchmarks/schema/

# Wikipedia corpus (external)
WIKI_CORPUS_BASE_PATH    # /Volumes/kelvin/wikipedia/2022_MAY
```

### Gitignored Paths

From `.gitignore`:
- `keys/` - API keys
- `src/benchmarks/schema/benchmarks.db` - Benchmarks database
- `src/wordfreq/data/linguistics.sqlite` - Linguistics database
- `src/clients/data/batch_tracking.sqlite` - Batch tracking
- `src/wordfreq/output/` - Generated outputs
- `input/` - Local input data
- `data/working` - Gitstore local working files

**Important:** These databases are gitignored. When setting up a new environment, you may need to initialize or copy existing databases.
