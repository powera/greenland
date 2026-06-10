# docs

Design documents and reference documentation.

- `API.md` — read-only REST API endpoints (lemma search, detail, metadata)
- `barsukas_agents.md` — agent dependency graph and pipeline workflow
  (`barsukas_agents.gv` is the Graphviz source)
- `barsukas_prometheus_metrics.md` — Prometheus metrics exposed by Barsukas
- `difficulty_overrides.md` — per-language difficulty level overrides
- `sentence_sync_design.md` — design for syncing sentences between SQLite and
  `data/release`
- `word2vec_pgvector_plan.md` — plan for word embeddings with PostgreSQL
  pgvector
