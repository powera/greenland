# `src/concepts`

Concept application workflows live here. Animal-named modules under
`src/agents/vovere/` are command-line orchestration and compatibility entry
points; storage modules remain responsible for SQLAlchemy models and CRUD.

## Q-id creation pipeline

The pipeline coordinator is `concepts.pipeline.create_concept_from_qid`. Its
stages are deliberately importable and testable on their own:

- `concept.seed.wikidata_query` -> `concepts.seed.wikidata_query`: acquire a
  normalized `WikidataConceptSeed` from Wikimedia.
- `concept.generate.entry` -> `concepts.generate.entry`: fetch usable source
  text and generate an encyclopedia entry.
- `concept.validate` -> `concepts.validate`: reject invalid, already-filed, or
  duplicate concepts before writes.
- `concept.persist` -> `concepts.persist`: create and link the concept using an
  existing database session.

## Discovery, intake, and batch generation

Beyond the single-Q-id pipeline, four modules carry what the `vovere`-family
CLIs used to hold inline:

- `concepts.discovery`: rank red links (`[[wiki links]]` with no concept yet)
  over the concept link-graph, and resolve or create the ranked topics.
  Read-only unless the caller asks for resolution or creation.
- `concepts.seed.qids`: Q-id intake -- resolve explicit Q-ids or titles, create
  concepts from them, and file them as sub-concepts. Idempotent throughout.
- `concepts.seed.wikidata_query`: seed lookup for one Q-id, plus class-query
  construction (`build_class_query`, `PRESET_CLASS_QIDS`) and execution for
  bulk sub-concept intake.
- `concepts.generate.batch`: prepare and submit one OpenAI Batch job for many
  concept bodies, and complete a finished batch from the stashed seeds.

`concepts.seed.__init__` deliberately re-exports only the seed-query stage:
`concepts.seed.qids` builds on `concepts.pipeline`, which imports the seed
package, so eager re-export would be circular.

Runtime settings, including the model and backend, are passed with
`storage.backend.config.DataSourceConfig`. Tests and rule-only runs must set
`GREENLAND_DISABLE_LLM=1`; Wikimedia calls should be mocked unless a developer
has explicitly approved a live request.
