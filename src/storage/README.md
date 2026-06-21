# storage

Database access layer for the linguistic database (default:
`data/wordfreq/linguistics.sqlite`). Provides the SQLAlchemy schema, CRUD
operations, query helpers, and a pluggable backend abstraction.

## Layout

- `models/` — SQLAlchemy ORM schema (`Lemma`, `WordToken`, `DerivativeForm`,
  `Sentence`, grammar facts, enums) plus GUID prefix definitions. Also
  `Concept` — encyclopedia-style entries (e.g. "World War II") kept outside the
  lemma/GUID/data-release machinery; see `models/concept.py`.
- `crud/` — create/read/update/delete functions for lemmas, tokens, sentences,
  translations, grammar facts, and embeddings
- `queries/` — read-only query helpers (lemma lookup, POS filtering, statistics)
- `backend/` — pluggable storage backends (SQLite, JSONL) and
  `DataSourceConfig`, the standard way to pass db/model configuration around
- `migrations/`, `migrate.py` — schema migrations and release-data export
- `translation_helpers.py` — all language code constants and conversion
  functions; import from here instead of defining local mappings
- `connection_pool.py` — thread-safe session pooling
- `legacy.py` — backward-compatibility wrapper for the old `Word` model

## Conventions

Pass configuration via `storage.backend.config.DataSourceConfig` rather than
passing `db_path` or `model_name` directly.
