# WordFreq

A system for linguistic analysis, word frequency tracking, and multi-language translations for the Greenland project.

## Directory Structure

### `agents/`
Autonomous agents for data quality and maintenance tasks. See [agents/README.md](agents/README.md) for details.

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

## CLI Tools & Scripts

### Data Analysis
- **`data/compare.py`** - Compare word frequency rankings across multiple corpus files
  - Usage: `python compare.py file1.json file2.json [--csv] [--top 50]`
  - Outputs harmonic mean rankings and maximum rank differences

### Dictionary Export
- **`dictionary/export_wordlist.py`** - Export words to plain text lists
- **`dictionary/reviewer.py`** - Interactive word review and verification interface

### Word Categorization
- **`tools/word_categorizer.py`** - Categorize words from frequency lists using LLM analysis
  - Usage: `python word_categorizer.py "category" [--limit 1000] [--save-json output.json]`
  - Example: `python word_categorizer.py "animals" --limit 500`

### Trakaido System
- **`trakaido/utils.py`** - Main entry point for trakaido word management
  - Usage: `python utils.py <command> [options]`

  **Commands:**
  - `utils.py add <word> [--lithuanian LT] [--level N]` - Add new word with LLM analysis
  - `utils.py update <guid|word> [--model MODEL]` - Update existing word entry
  - `utils.py set-level <guid|word> <level> [--reason REASON]` - Set difficulty level
  - `utils.py move-words <from_level> <subtype> <to_level>` - Bulk move words by level and subtype
  - `utils.py list [--level N] [--subtype TYPE]` - List words with optional filters
  - `utils.py subtypes` - List all POS subtypes with word counts
  - `utils.py export json [--output PATH]` - Export to JSON format
  - `utils.py export wireword [--output PATH]` - Export to WireWord API format
  - `utils.py export lang-lt [--output-dir DIR]` - Export to lang_lt directory structure
  - `utils.py export text <subtype> [--output PATH]` - Export simple text for specific subtype
  - `utils.py export all` - Export to all formats at once

- **`trakaido/dict_generator.py`** - Generate structure and dictionary files for trakaido wordlists
  - Usage: `python dict_generator.py [--language lithuanian|chinese] [--level N] [--subtype SUBTYPE]`
  - Generates Python files with word data organized by difficulty level and subtype

- **`trakaido/json_to_database.py`** - Import trakaido data from JSON into the database
  - Usage: `python json_to_database.py [path/to/nouns.json] [--no-update-difficulty]`
  - Migrates English/Lithuanian word pairs with GUIDs and difficulty levels

- **`trakaido/verb_converter.py`** - Convert verbs to wireword export format
  - Usage: `python verb_converter.py [--output path.json] [--verbose]`
  - Generates JSON with Lithuanian verb conjugations organized by level

### Translation
- **`translation/generate_lithuanian_noun_forms.py`** - Generate Lithuanian noun declensions
  - Batch generation of all 14 declension forms (7 cases × 2 numbers) for Lithuanian nouns

### Autonomous Agents
See [agents/README.md](agents/README.md) for autonomous data quality and maintenance agents.

## Database Location
The default SQLite database is at `src/wordfreq/data/linguistics.sqlite` (or as configured in `constants.WORDFREQ_DB_PATH`).
