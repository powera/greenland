# `src/sentences`

The application layer for sentence and conversation workflows. Sentence logic
belongs here; animal-named modules under `src/agents/` are compatibility CLI
entry points and work finders.

## Generation and translation

- `generation.py` coordinates pattern, basic LLM, and vocabulary-guided example
  generation.
- `pattern_generation.py`, `llm_generation.py`, and
  `guided_generation.py` implement those three strategies.
- `translation.py` builds translation/decomposition prompts and persists their
  structured results.
- `translation_coverage.py` finds missing translations and provides both rich
  and text-only translation helpers.
- `lemma_translation_cli.py` is the queue-first implementation behind the
  legacy `agents/zvirblis.py` command.
- `generation_cli.py` is the queue-first implementation behind
  `python -m agents.buivolas`.

## Import, analysis, and linking

- `translate_and_decompose.py` runs the shared multi-phase sentence pipeline.
- `decomposition.py` and `dependencies.py` contain prompt/schema logic.
- `candidate_lookup.py` and `analysis.py` resolve tokens against known lemmas.
- `persistence.py`, `link_writer.py`, `pending_staging.py`, and `promotion.py`
  store links and stage unresolved vocabulary.
- `import_workflow.py` implements per-sentence import;
  `workqueue/handlers/sentences/import_document.py` performs document splitting
  and queues those imports.
- `verification.py` audits translations and lemma links.

## Conversations

- `conversation_planning.py` selects vocabulary for bulk, level-oriented
  conversations and definition narratives.
- `conversation_generation.py` generates and stores those planned items.
- `conversation_cli.py` is the queue-first implementation behind the legacy
  `agents/sarka.py` command.
- `dialog_scene.py` and `dialog_coverage.py` power the Barsukas scene-oriented
  workflow described in `docs/dialog_generation.md`.

## Workqueue contract

The CLIs discover work and enqueue capability-named tasks. The worker imports
thin adapters from `workqueue/handlers/sentences/` and
`workqueue/handlers/conversations/`; execution calls the services in this
package directly.

Canonical tasks owned here include:

- `sentences.patterns.generate`
- `sentences.examples.generate`
- `sentences.translate`
- `sentences.translate.simple`
- `sentences.import`
- `conversations.generate`
- `conversations.definitions.generate`
- `conversations.scene.generate`

The legacy CLIs enqueue by default. `--execute-inline` is available only for
debugging and deliberate one-off runs.

Use `storage.translation_helpers` for language-code handling and pass runtime
settings through `storage.backend.config.DataSourceConfig`.
