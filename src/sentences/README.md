# `src/sentences`

Sentence-level translation, decomposition, and lemma-discovery helpers.

## What lives here

- `translation.py` — sentence translation orchestration + DB persistence.
- `decomposition.py` — prompt/schema builders for translate+decompose workflows.
- `analysis.py` — candidate lemma discovery from sentence token forms.
- `patterns/` — reusable sentence-pattern definitions for generated content.

## Dependencies you should use

- `storage.models.schema` for ORM models used by sentence workflows.
- `storage.translation_helpers` for language normalization and language metadata.
- `clients.unified_client.UnifiedLLMClient` for LLM interactions.
- `util.prompt_loader` for sentence prompt/context templates.

## Related modules

- Word-level helpers: `src/words/`
