# Word2Vec / pgvector Suggestion System Plan

This plan tracks implementation for semantic suggestion candidates that support
future **manual synonym-adding** workflows.

## Scope

- Build Postgres + pgvector storage and retrieval for lemma embeddings.
- Add backend services for embedding refresh and nearest-neighbor suggestion.
- Add backfill and workqueue support.
- Do **not** modify Barsukas UI yet.
- Do **not** run database update/backfill yet.
- Keep feature behind an explicit opt-in flag (`--use_word2vec` / `USE_WORD2VEC=true`).

## Rollout Steps

1. Schema + model setup
2. Core embedding module
3. CRUD + vector query support
4. Backfill tool
5. Workqueue integration
6. Barsukas API/UI integration (future)
7. Manual synonym action wiring (future)
8. Flag-gated rollout controls

## Status

### ✅ Completed in this change

1. **Schema + model setup**
   - Added `LemmaEmbedding` model/table definition.
   - Added `PGVector` SQLAlchemy type helper.
   - Added Postgres extension/index bootstrap (`CREATE EXTENSION IF NOT EXISTS vector` and vector indexes).

2. **Core embedding module**
   - Added `src/words/word2vec.py`.
   - Added strict backend guard: raises on non-Postgres backends.
   - Added OpenAI embedding fetch, per-lemma refresh, and batch rebuild functions.
   - Added nearest-candidate suggestion function for manual workflows.

3. **CRUD + vector query support**
   - Added `src/storage/crud/lemma_embedding.py` with:
     - upsert
     - nearest-neighbor vector query
     - lemma batch fetch support for refresh jobs

4. **Backfill tool**
   - Added `src/storage/migrations/backfill_lemma_embeddings.py`.
   - CLI supports language/model/source/limit options.
   - Explicitly enforces Postgres mode.

5. **Workqueue integration**
   - Added `words.embeddings` task type.
   - Added `src/workqueue/handlers/words/embeddings.py`.
   - Registered handler in workqueue registry and exports.
   - Added pipeline ordering entry.

8. **Flag-gated rollout controls**
   - Added `use_word2vec` to `DataSourceConfig`.
   - Added `--use-word2vec/--use_word2vec` to Barsukas launchers and worker.
   - Added `--use-word2vec/--use_word2vec` to shared agent CLI args.
   - Enforced runtime guard in `words.word2vec` to require explicit opt-in.

### ⏳ Not yet done (by design)

6. Barsukas route/template integration for displaying suggestion candidates.
7. Manual “add as synonym” UX/action from ranked candidates.
