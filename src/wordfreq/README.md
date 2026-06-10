# WordFreq

Core linguistic database system: word frequency tracking, difficulty tiers,
and LLM-based translation and analysis for the Greenland project.

Related code that used to live here has moved: database models are in
`src/storage/`, agents in `src/agents/`, and prompt templates in the
top-level `prompts/` directory (loaded via `util.prompt_loader`).

## Directory Structure

### `frequency/`
Frequency analysis and corpus management:
- `corpus.py` — corpus loading and processing (`load_all_corpora()`)
- `importer.py` — import frequency data from external sources
- `combined_rank.py` — aggregate frequency rank calculations

### `tiers/`
Difficulty tier annotations from external sources (CEFR, Cambridge YLE,
Basic English). Each source supplies a `TierImporter`; imports run via
`runner.run_import`.

### `translation/`
LLM-based linguistic analysis: word translation, definitions, pronunciation,
POS subtype classification, and form generation (`client.py`,
`processor.py`, `generate_forms_*.py`, `wiktionary_forms.py`).

### `dictionary/`
Word list export and review tools (`export_wordlist.py`, `reviewer.py`).

### `tools/`
CLI utilities: difficulty override management, release reports,
sentence/word linking, vocabulary budgets, country and family-relation
overrides, Chinese conversion, word categorization.

### `data/`
Python data modules and corpus comparison helpers (`compare.py`,
family-relations generators).

### `templates/`
HTML templates for web-based POS browsing.

### Top-level modules
- `golden_loader.py` — load frequency and tier data into the JSONL backend's
  in-memory database
- `lexeme_frequency.py` — lexeme-level frequency rollups over external
  lexeme annotations

## Key Concepts

- **Frequency rankings** — words are ranked per corpus, by harmonic mean
  across corpora, and by combined aggregate rank.
- **LLM integration** — all LLM queries go through
  `clients.unified_client.UnifiedLLMClient`, with prompt templates loaded
  from `prompts/` via `util.prompt_loader.get_context()` / `get_prompt()`.

## Database Location

The default SQLite database is at `data/wordfreq/linguistics.sqlite` (or as
configured in `constants.WORDFREQ_DB_PATH`). See `src/storage/README.md` for
the schema.
