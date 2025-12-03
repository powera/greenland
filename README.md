# CLAUDE.md - AI Assistant Guide to Greenland

This document provides comprehensive guidance for AI assistants (including Claude) working with the Greenland codebase. It explains the project structure, development workflows, key conventions, and best practices.

**Last Updated:** 2025-11-13
**Python Version:** 3.9+

---

## Table of Contents

1. [Project Overview](#project-overview)
2. [Quick Start](#quick-start)
3. [Repository Structure](#repository-structure)
4. [Core Modules](#core-modules)
5. [Database Architecture](#database-architecture)
6. [Development Workflows](#development-workflows)
7. [Key Conventions & Patterns](#key-conventions--patterns)
8. [Testing](#testing)
9. [Common Tasks](#common-tasks)
10. [Important Paths](#important-paths)
11. [AI Assistant Guidelines](#ai-assistant-guidelines)

---

## Project Overview

**Greenland** is a sophisticated multi-faceted Python project focused on:

1. **Linguistic Database System (WordFreq)** - Multi-language word frequency and translation database with LLM-powered analysis supporting 10 languages
2. **LLM Query Interface (Verbalator)** - HTML server for running canned LLM queries on text samples
3. **LLM Benchmarking Suite** - Framework for testing and comparing language model capabilities
4. **Web-based Database Editor (Barsukas)** - Flask interface for managing the linguistics database

### Key Statistics

- **~57,000 lines** of Python code
- **10 languages** supported: English, Lithuanian, Chinese, French, German, Spanish, Portuguese, Korean, Swahili, Vietnamese
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
python -i src/interactive.py
# Provides: cl (LinguisticClient), rv (Reviewer), session, prcs (Processor)
```

### Web Interfaces

```bash
# Barsukas - Database Editor (port 5555)
cd src/barsukas && ./launch.sh

# Verbalator - LLM Query Interface (port 9871)
python src/verbalator/server.py
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
│   │   └── tools/             # CLI utilities (difficulty overrides, etc.)
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
│   │   └── ungurys.py         # WireWord export agent
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
│   │   └── batch_queue.py     # Batch processing
│   │
│   ├── benchmarks/            # LLM benchmark suite
│   │   ├── datastore/         # Benchmark results storage
│   │   └── 0015_spell_check/, 0016_antonym/, etc.
│   │
│   ├── lib/                   # Shared libraries
│   │   ├── benchmarks/        # Benchmark framework
│   │   ├── exemplars/         # Model comparison framework
│   │   └── validation.py      # Input validation utilities
│   │
│   ├── verbalator/            # LLM query web interface
│   │   └── server.py          # HTTP server (port 9871)
│   │
│   ├── util/                  # General utilities
│   │   ├── prompt_loader.py   # Prompt template loading
│   │   ├── flesch_kincaid.py  # Readability calculations
│   │   └── wiki_loader.py     # Wikipedia corpus processing
│   │
│   └── constants.py           # Centralized path configuration ⭐ IMPORTANT
│
├── data/                      # Static data files
│   ├── gre_words/             # GRE vocabulary lists
│   └── trakaido_wordlists/    # Difficulty-leveled wordlists
│
├── templates/                 # Jinja2 templates for reports
├── public_html/              # Static web assets (CSS, JS, images)
├── docs/                     # Documentation
│   └── difficulty_overrides.md
├── audio/                    # Audio processing related
├── claude/                   # Claude-specific utilities
│   ├── config.yaml
│   ├── splitter.py
│   └── stage_files.py
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
| **povas** | Peacock | HTML report generator |
| **ungurys** | Eel | WireWord export agent |
| **elnias** | Deer | WireWord bootstrap export |
| **lape** | Fox | (Purpose to be determined) |

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

### 6. Verbalator - LLM Query Interface

**Purpose:** Simple HTTP server for running canned LLM queries on text samples.

**Features:**
- Web interface for canned prompts
- Multiple model support
- Flesch-Kincaid reading level calculation

**Entry Point:** `src/verbalator/server.py` (port 9871)

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

## Key Conventions & Patterns

### 1. Path Configuration

**CRITICAL:** All paths are defined in `src/constants.py`. **Always check this file first.**

```python
from constants import (
    WORDFREQ_DB_PATH,          # linguistics.sqlite
    SQLITE_DB_PATH,            # benchmarks.db
    TEMPLATES_DIR,             # Jinja2 templates
    OUTPUT_DIR,                # Generated outputs
    KEY_DIR,                   # API keys
)
```

### 2. Database Sessions

**Pattern:** Use context managers for sessions

```python
from wordfreq.storage.database import get_session

with get_session() as session:
    # Do database work
    lemma = session.query(Lemma).filter_by(guid="N01_001").first()
    # Session automatically commits/rolls back
```

### 3. LLM Prompt Loading

**Pattern:** Prompts stored in directories with `context.txt` and `prompt.txt`

```python
from util.prompt_loader import load_prompt

context, prompt = load_prompt("definitions")
# Loads from src/wordfreq/prompts/definitions/
```

### 4. Agent Architecture

**Pattern:** All agents follow this structure

```python
import argparse
from wordfreq.storage.database import get_session

def check_issues(session, limit=None):
    """Read-only check returning list of issues"""
    issues = []
    # Find problems
    return issues

def fix_issues(session, issues, dry_run=False):
    """Fix issues (or preview if dry_run=True)"""
    for issue in issues:
        if not dry_run:
            # Make changes
            pass

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--fix", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()

    with get_session() as session:
        issues = check_issues(session, args.limit)
        if args.fix or args.dry_run:
            fix_issues(session, issues, args.dry_run)

if __name__ == "__main__":
    main()
```

### 5. Flask Blueprint Pattern

**Pattern:** Routes organized as blueprints

```python
from flask import Blueprint, render_template

bp = Blueprint('lemmas', __name__, url_prefix='/lemmas')

@bp.route('/')
def list_lemmas():
    return render_template('lemmas/list.html')
```

Register in `src/barsukas/app.py`:

```python
from routes import lemmas
app.register_blueprint(lemmas.bp)
```

### 6. GUID System

**Pattern:** Lemmas use GUID format: `{POS}{SUBTYPE}_{COUNTER}`

Examples:
- `N01_001` - Noun, subtype 01 (common noun), counter 001
- `V01_042` - Verb, subtype 01, counter 042
- `A01_123` - Adjective, subtype 01, counter 123

### 7. Per-Language Difficulty Overrides

**Pattern:** Use effective difficulty level with coalescing

```python
from wordfreq.storage.crud.difficulty_override import get_effective_difficulty_level

effective_level = get_effective_difficulty_level(session, lemma, 'zh')
# Returns override if exists, otherwise lemma.difficulty_level
# Level -1 means excluded from that language
```

See `docs/difficulty_overrides.md` for comprehensive documentation.

### 8. Translation Storage

**Hybrid Pattern:**
- **Column-based:** Chinese, French, Korean, Swahili, Vietnamese stored in `lemmas` table columns
- **Table-based:** Spanish, German, Portuguese stored in `lemma_translations` table

Always check both when working with translations.

### 9. Operation Logging

**Pattern:** All database changes should be logged

```python
from wordfreq.storage.crud.operation_log import log_operation

log_operation(
    session=session,
    operation_type="update",
    table_name="lemmas",
    record_id=lemma.id,
    details={"field": "definition", "old": old_def, "new": new_def}
)
```

### 10. Batch LLM Processing

**Pattern:** Use batch queue for bulk operations

```python
from clients.batch_queue import BatchQueue

queue = BatchQueue(model="gpt-4")
for word in words:
    queue.add(prompt=f"Define {word}")

results = queue.execute()
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
VERBALATOR_HTML_DIR      # public_html/

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
- `src/schema/benchmarks.db` - Benchmarks database
- `src/wordfreq/data/linguistics.sqlite` - Linguistics database
- `src/clients/data/batch_tracking.sqlite` - Batch tracking
- `src/wordfreq/output/` - Generated outputs
- `claude/staging/` - Claude staging area
- `input/` - Local input data

**Important:** These databases are gitignored. When setting up new environment, you'll need to initialize or copy existing databases.

---

## AI Assistant Guidelines

### General Principles

1. **Understand Before Modifying**
   - Read relevant code and documentation first
   - Check `src/constants.py` for path references
   - Review existing patterns before creating new ones
   - Look at similar modules for consistency

2. **Follow Existing Patterns**
   - Agent pattern for autonomous tasks
   - Blueprint pattern for Flask routes
   - Session context managers for database operations
   - Prompt loading via `util/prompt_loader.py`

3. **Maintain Database Integrity**
   - Always use transactions (sessions auto-commit/rollback)
   - Log all operations via `operation_logs`
   - Check for existing records before creating
   - Use effective difficulty levels (with overrides)

4. **Test Your Changes**
   - Run `python run_tests.py` before committing
   - Add tests for new functionality
   - Check both unit and integration impacts

5. **Document Your Work**
   - Add docstrings to new functions/classes
   - Update relevant documentation files
   - Comment complex logic
   - Include usage examples

### Specific Guidance

#### When Working with Database

```python
# ✓ GOOD: Use session context manager
with get_session() as session:
    lemma = session.query(Lemma).filter_by(guid="N01_001").first()
    lemma.definition = "New definition"
    log_operation(session, "update", "lemmas", lemma.id, {...})
    # Auto-commits on success, rolls back on error

# ✗ BAD: Manual session management without context manager
session = Session()
lemma = session.query(Lemma).first()
lemma.definition = "New definition"
session.commit()  # No error handling, no logging
session.close()
```

#### When Adding New Agent

```python
# Follow this structure:
# 1. Import required modules
# 2. Define check_* function (read-only)
# 3. Define fix_* function (with dry_run support)
# 4. Define main() with argparse
# 5. Add to agent roster in this document
```

#### When Working with Translations

```python
# ✓ GOOD: Check both storage methods
def get_translation(session, lemma, language_code):
    # Check column-based storage
    if language_code == 'zh':
        return lemma.chinese
    elif language_code == 'fr':
        return lemma.french
    # ... etc

    # Check table-based storage
    translation = session.query(LemmaTranslation).filter_by(
        lemma_id=lemma.id,
        language_code=language_code
    ).first()

    return translation.translation if translation else None

# ✗ BAD: Only checking one storage method
def get_translation(session, lemma, language_code):
    translation = session.query(LemmaTranslation).filter_by(
        lemma_id=lemma.id,
        language_code=language_code
    ).first()
    return translation.translation if translation else None
    # Missed Chinese, French, Korean, etc.!
```

#### When Using LLM Clients

```python
# ✓ GOOD: Use unified client with error handling
from clients.unified_client import UnifiedClient
from clients.types import QueryResult

client = UnifiedClient(model="gpt-4")
try:
    result = client.query(prompt="...")
    if result.success:
        process_result(result.content)
    else:
        handle_error(result.error)
except Exception as e:
    log_error(e)

# ✗ BAD: Direct API calls without abstraction
import openai
response = openai.ChatCompletion.create(...)
# Not portable, no error handling, no batching support
```

#### When Adding Tests

```python
# ✓ GOOD: Descriptive names, clear assertions
def test_lemma_effective_difficulty_uses_override():
    """Test that effective difficulty prefers override over default"""
    lemma = Lemma(guid="N01_001", difficulty_level=5)
    override = LemmaDifficultyOverride(
        lemma=lemma,
        language_code="zh",
        difficulty_level=2
    )
    effective = get_effective_difficulty_level(session, lemma, "zh")
    assert effective == 2, "Should use override, not default"

# ✗ BAD: Vague names, unclear what's being tested
def test_difficulty():
    lemma = Lemma(guid="N01_001", difficulty_level=5)
    assert lemma.difficulty_level == 5
    # What about overrides? What's the actual behavior being tested?
```

### Code Review Checklist

Before submitting changes, verify:

- [ ] Code follows Black formatting (100 char line length)
- [ ] All functions have type hints
- [ ] Database operations use context managers
- [ ] Changes are logged in `operation_logs`
- [ ] Tests pass: `python run_tests.py`
- [ ] New functionality has tests
- [ ] Documentation updated (if applicable)
- [ ] Paths use `constants.py` (not hardcoded)
- [ ] Git commit messages are descriptive
- [ ] Branch name follows `claude/*` pattern

### Common Pitfalls to Avoid

1. **Hardcoding Paths**
   - ✗ `"/home/user/greenland/src/wordfreq/data/linguistics.sqlite"`
   - ✓ `from constants import WORDFREQ_DB_PATH`

2. **Ignoring Translation Storage Duality**
   - Some languages in columns, some in table
   - Always check both

3. **Forgetting Difficulty Overrides**
   - Don't use `lemma.difficulty_level` directly
   - Use `get_effective_difficulty_level()`

4. **Not Logging Operations**
   - All database changes should be logged
   - Critical for audit trail

5. **Skipping Tests**
   - Tests prevent regressions
   - Run before every commit

6. **Creating New Patterns**
   - Follow existing patterns first
   - Only introduce new patterns with good reason

### Questions to Ask

Before making changes:

1. **Does this pattern already exist?**
   - Search codebase for similar functionality
   - Reuse existing patterns

2. **What are the database implications?**
   - Will this create orphaned records?
   - Are foreign keys properly set?
   - Is this logged?

3. **How will this affect existing code?**
   - Run tests to check for regressions
   - Check for breaking changes

4. **Is this documented?**
   - Function docstrings
   - Module-level documentation
   - This CLAUDE.md file

5. **Is this tested?**
   - Unit tests for individual components
   - Integration tests for workflows

---

## Recent Development Focus

Based on recent commits:

1. **Agent Reorganization** - Moved agents from `src/wordfreq/agents` to top-level `src/agents/`
2. **Code Base Weight Rebalancing** - Refactoring for better module organization
3. **Synonym and Alternative Form Management** - Enhanced ŠERNAS agent
4. **Sentence Generation and Linking** - ŽVIRBLIS and BEBRAS improvements
5. **Measure Word Support** - Chinese nouns now support measure word property
6. **Lemma Disambiguation** - Improved UI and agent support
7. **BARSUKAS Enhancements** - Web UI improvements for synonym/alternative form removal
8. **Traditional Chinese Enforcement** - All LLM prompts now enforce Traditional Chinese characters

---

## Additional Resources

### Documentation Files

- **`docs/difficulty_overrides.md`** - Comprehensive guide to per-language difficulty system
- **`README.md`** - Project overview
- **`pyproject.toml`** - Dependencies and tool configuration

### Interactive Tools

- **`src/interactive.py`** - Python shell with preloaded linguistic tools
- **`src/barsukas/`** - Web UI for database editing
- **`src/verbalator/`** - Web UI for LLM queries

### External References

- SQLAlchemy ORM: https://docs.sqlalchemy.org/
- Flask Blueprints: https://flask.palletsprojects.com/blueprints/
- Pydantic: https://docs.pydantic.dev/
- pytest: https://docs.pytest.org/

---

## Contact & Contribution

For questions or contributions:

1. Review this CLAUDE.md file
2. Check existing code patterns
3. Run tests before submitting
4. Follow git workflow with `claude/` branch prefix
5. Ensure all changes are documented

**Remember:** This is a sophisticated linguistic research platform. Take time to understand the domain model, database schema, and existing patterns before making changes. When in doubt, ask questions and read the code.

---

**Document Version:** 1.0
**Last Updated:** 2025-11-13
**Maintained By:** Greenland Development Team
