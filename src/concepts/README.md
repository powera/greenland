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

Runtime settings, including the model and backend, are passed with
`storage.backend.config.DataSourceConfig`. Tests and rule-only runs must set
`GREENLAND_DISABLE_LLM=1`; Wikimedia calls should be mocked unless a developer
has explicitly approved a live request.
