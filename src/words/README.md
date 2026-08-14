# `src/words`

Word-level LLM helpers (single lemma tasks, not sentence workflows).

## What lives here

- `translation.py` — single-target and multi-target word translation prompt/query helpers.
- `translation_workflow.py` — translation selection, generation, storage, and
  queueing; the Voras CLI is argument parsing and display over this module.
- `translation_coverage.py` — translation coverage reporting, including the
  full report Voras prints by default.
- `inflections.py` and `form_generation.py` — inflection coverage and generation workflows.
- `pronunciation.py` and `pronunciation_generation.py` — pronunciation coverage and generation workflows.
- `grammar_facts.py` and `grammar_fact_generation.py` — grammar-fact dispatch and persistence.
- `validation.py` — lemma form, definition, and disambiguation validation.
- `lemma_selection.py` — shared lemma query and filtering utilities.
- `synonyms.py` — synonym-family prompt/query helpers with structured JSON output.
- `synonym_coverage.py` — which lemma/language pairs have never been scanned
  for synonyms and alternative forms.
- `synonym_workflow.py` — bulk generate/fix/regenerate orchestration over
  `synonyms.py`; the Šernas CLI is selection, confirmation, and rendering over
  this module.
- `verb_forms.py` — language-specific verb-form prompt/query helpers.
- `ipa_pronunciation.py` — compatibility exports for IPA generation utilities.
- `pending_imports/` — the staging queue for terms nobody has decided about
  yet, and the approval paths that turn one into a lemma, a name, or a concept.
  Used to live in `agents/dramblys/`. See `docs/pending_imports.md` for the
  three target kinds and the sentence back-link.

## Dependencies you should use

- `clients.unified_client.UnifiedLLMClient` for LLM calls.
- `storage.translation_helpers` for language code/name normalization.
- `ipa.generation` (via `ipa_pronunciation.py`) for IPA behavior.
- `util.prompt_loader` for shared prompt/context loading.

## Related modules

- Sentence-level orchestration: `src/sentences/`
- Queue payload adapters: `src/workqueue/handlers/words/`
