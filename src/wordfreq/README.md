# WordFreq

Corpus generation, word-token frequency analysis, and external difficulty tiers
for the Greenland project.

Related code that used to live here has moved: database models are in
`src/storage/`, agents in `src/agents/`, and prompt templates in the
top-level `prompts/` directory (loaded via `util.prompt_loader`).

## Directory Structure

### `corpora/`
Corpus generation: downloaders and builders for the Gutenberg, SCOTUS,
Europarl, OpenStax, WPA and Wikipedia corpora, each writing
`data/wordfreq/<corpus>.json`. See `corpora/README.md`, which also has the
"Regenerating every corpus" runbook (about 12.5 minutes, offline).

### `frequency/`
Frequency analysis and corpus management:
- `corpus.py` — corpus loading and processing (`load_all_corpora()`)
- `importer.py` — import frequency data from external sources
- `combined_rank.py` — aggregate frequency rank calculations

### `tiers/`
Difficulty tier annotations from external sources (CEFR, Cambridge YLE,
Basic English). Each source supplies a `TierImporter`; imports run via
`runner.run_import`.

### Word-level linguistic workflows

Definition and translation queries, the linguistic client, and word-form
workflows live in `src/words/` (form generation and storage in `words/forms/`).
Sentence linking and vocabulary budgets live in `src/sentences/`;
language-specific difficulty rules and override managers in
`src/words/difficulty/`. Maintenance CLIs live in `src/scripts/`.

### `data/`
Curriculum themes, fixed cohorts, and family-relation section definitions.

### Top-level modules
- `lexeme_frequency.py` — lexeme-level frequency rollups over external
  lexeme annotations

Hosted JSONL startup enrichment lives in
`src/storage/backend/jsonl/frequency_loader.py`; it uses these corpus loaders
and rank calculations to populate the backend's in-memory database.

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
