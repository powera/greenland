# WordFreq

A system for linguistic analysis, word frequency tracking, and multi-language translations for the Greenland project.

## Directory Structure

### `data/`
Source data files for word frequency analysis:
- `*.json` - Word frequency data from various corpora (19th/20th century books, cooking recipes, etc.)
- `subtlex.txt` - SUBTLEX subtitle corpus frequencies
- `wiki_vital.json` - Wikipedia vital articles word frequencies
- `compare.py` - Scripts for comparing frequency data across corpora
- `wikipedia_data.py` - Wikipedia corpus processing utilities

### `dictionary/`
Word list export and review tools:
- `export_wordlist.py` - Export words to plain text lists
- `export_by_pos.py` - Export words grouped by part of speech
- `reviewer.py` - Interactive word review and verification interface

### `frequency/`
Frequency analysis and corpus management:
- `analysis.py` - Word frequency analysis and ranking calculations
- `importer.py` - Import frequency data from external sources
- `corpus.py` - Corpus loading and processing
  - `load_all_corpora()` - Load all corpus data into the database
- `tools/create_wordfreq_simple.py` - Simplified frequency list generation

### `output/`
Generated output files from exports and analysis (not tracked in git)

### `prompts/`
LLM prompt templates for linguistic analysis:
- `definitions/` - Word definition generation prompts
- `chinese_translation/` - Chinese translation prompts
- `pos_subtype/` - Part-of-speech subtype classification prompts
- `pronunciation/` - Pronunciation generation prompts
- `word_forms/` - Word form generation prompts
- `word_analysis/` - Comprehensive word analysis prompts
- `word_categorizer/` - Word categorization prompts
- `lithuanian_noun_declensions/` - Lithuanian noun declension prompts

Each prompt directory contains:
- `context.txt` - System context for the LLM
- `prompt.txt` - User prompt template with placeholders

### `storage/`
Database models and connection management:
- `database.py` - Database operations and queries
- `connection_pool.py` - Thread-safe database connection pooling
- `models/` - SQLAlchemy ORM models for the database schema
  - `schema.py` - Core database models (WordToken, Lemma, DerivativeForm, etc.)
  - `enums.py` - Enumeration types for database fields
  - `translations.py` - Translation model structures
  - `query_log.py` - LLM query logging

### `templates/`
HTML templates for web-based word browsing:
- `pos_index.html` - Part-of-speech index page
- `pos_type.html` - POS type listing page
- `pos_subtype.html` - POS subtype detail page
- CSS and JavaScript for interactive features

### `tools/`
Specialized utilities:
- `word_categorizer.py` - Categorize words from frequency lists using LLM analysis

### `trakaido/`
Trakaido language learning system integration:
- `utils/` - Core utilities for trakaido word management
  - `word_manager.py` - Add, update, and manage trakaido words
  - `cli.py` - Command-line interface
  - `data_models.py` - Data structures for word data
  - `text_rendering.py` - Display and formatting utilities
- `migrate_static_data.py` - Import static word lists into the database

### `translation/`
LLM-based linguistic analysis and translation:
- `client.py` - Main client for querying LLMs for word analysis
- `processor.py` - Batch processing workflows
- `noun_forms.py` - Lithuanian noun form data structures
- `wiki.py` - Wiktionary scraping for Lithuanian declensions
- `generate_lithuanian_noun_forms.py` - Generate Lithuanian noun declensions

## Key Concepts

### Database Schema
The system uses a relational model with these core entities:
- **WordToken** - Individual word forms (tokens) with frequency data
- **Lemma** - Base word meanings with definitions and translations
- **DerivativeForm** - Links tokens to lemmas with grammatical information
- **Corpus** - Source corpora for frequency data
- **WordFrequency** - Frequency counts per word per corpus

### Frequency Rankings
Words are ranked by:
- Individual corpus frequencies
- Harmonic mean across multiple corpora
- Combined frequency rank (aggregate score)

### LLM Integration
All LLM queries go through `clients.unified_client.UnifiedLLMClient` and use prompt templates from the `prompts/` directory. Prompts are loaded via `util.prompt_loader.get_context()` and `get_prompt()`.

## Database Location
The default SQLite database is at `src/wordfreq/data/linguistics.sqlite` (or as configured in `constants.WORDFREQ_DB_PATH`).
