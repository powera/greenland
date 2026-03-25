# `src/words`

Word-level LLM helpers (single lemma tasks, not sentence workflows).

## What lives here

- `translation.py` — single-target and multi-target word translation prompt/query helpers.
- `synonyms.py` — synonym-family prompt/query helpers with structured JSON output.
- `verb_forms.py` — language-specific verb-form prompt/query helpers.
- `ipa_pronunciation.py` — compatibility exports for IPA generation utilities.

## Dependencies you should use

- `clients.unified_client.UnifiedLLMClient` for LLM calls.
- `storage.translation_helpers` for language code/name normalization.
- `ipa.generation` (via `ipa_pronunciation.py`) for IPA behavior.
- `util.prompt_loader` for shared prompt/context loading.

## Related modules

- Sentence-level orchestration: `src/sentences/`
