# Pending imports

A **pending import** is a term somebody wants in the database that nobody has
decided about yet. Four things stage them:

* the frequency check (`dramblys --check frequency --stage`),
* the document parser (`genys`),
* the sentence import path, when linking cannot find a lemma for a word,
* a human, through the Barsukas word-list form.

One thing resolves them: approval. The code lives in
`src/words/pending_imports/`; it used to live in `src/agents/dramblys/`, where
it was reachable only by importing an animal-named agent that had nothing else
to do with it.

## What a term becomes

`PendingImport.target_kind` names the table a term ends up in. The vocabulary
is closed — a term that is none of the three is rejected rather than given a
fourth kind.

| `target_kind` | Becomes | LLM call on approval? | Notes |
|---|---|---|---|
| `lemma` (default) | `Lemma` + derivative forms | Yes | Gets a GUID, a difficulty level, and a place in `data/release`. |
| `name` | `Name` | No | Proper nouns. No difficulty, skipped in a sentence's level rollup. |
| `concept` | `Concept` | No | Encyclopedia topics. Created with title + summary; the body is generated later by the concept generator. |

Two supporting columns are only meaningful for their own kind: `name_kind`
(one of `NAME_KINDS`) and `concept_type` (free-form, e.g. `event`).

### How the kind is decided

`words.pending_imports.classification` answers in two tiers, cheap first:

1. **Rule tier** (`suggest_target_kind`) — no LLM call, run by every staging
   path. An existing `Name`, `Concept`, or `Lemma` with the same text settles
   it outright. Otherwise it reads capitalization: an inner capital or several
   capitalized words is proper anywhere, while a capital that the start of the
   example sentence would have forced is not evidence. A verb/adjective/adverb
   reading is vocabulary whatever its capitalization.
2. **LLM tier** (`classify_pending_import`) — one structured call, made from
   the Barsukas "Stage" step, which was already calling a model. It is the only
   thing that can reliably separate a name from a concept, and it fills in
   `name_kind` and `concept_type`. A failed call falls back to the rule tier
   rather than blocking the stage.

A reviewer can override either tier from the pending-import detail page
(`POST /pending-imports/<id>/set-kind`).

## The link back to sentences

A sentence that stages a word records a `SentencePendingImport` row: the
sentence, the pending import, and the English gloss it was waiting on. This is
what lets the approval of a staged word find the sentences that needed it, and
what lets `sentences.import_workflow` tell "already staged" from "not staged
yet".

That back-link used to live in `SentenceWordHint.pending_import_id`, which was
wrong in three ways that all showed up as flakiness:

* hints are unique on `(sentence_id, position)` and are written by four
  components that do not coordinate, so two writers appending a slot in one
  transaction could collide;
* a hint already resolved to a lemma could not *also* record that the sentence
  was waiting on a staged word, so stage `STAGE` never completed for that
  sentence;
* the foreign key had no `ON DELETE` behavior, so every path that deleted a
  pending import had to remember to detach the hints first, and a hint left
  pointing at nothing was worse than an error — `STAGE` counted it as staged,
  so the sentence was never staged again.

Hints now mean what their docstring always said they meant: which lemmas a
sentence was built to exercise. Legacy hint rows are still *read* (so an older
database keeps working) and are cleaned up when the pending row they reference
is deleted.

### One exit, always

Every removal goes through `approval.delete_pending_import`, whatever the
reason — approved into a lemma, accepted as a synonym of an existing one,
promoted to a name or a concept, or rejected. It:

1. applies the outcome to the waiting sentences' word rows, so the word is
   *linked* and not merely un-staged;
2. repoints or drops legacy hint rows;
3. deletes the pending row, taking its synonym candidates and sentence links
   with it through the ORM cascades. (The ORM cascade is load-bearing: SQLite
   does not enforce foreign keys here, so `ON DELETE CASCADE` alone would leave
   orphans.)

A term approved as a concept becomes neither a lemma nor a name, so the
sentence word that staged it has nothing to point at. `unlinked_words` treats a
word that is a known concept as settled — otherwise the sentence would stage
the term again on every pass and never reach a complete `LINK`.

## Migrations

Existing databases need both, in either order:

```bash
PYTHONPATH=src python src/storage/migrations/add_pending_import_target_kind.py
PYTHONPATH=src python src/storage/migrations/add_sentence_pending_imports.py
```

The first adds `target_kind` (NOT NULL, defaulting to `lemma`, which is exactly
the old behavior), `name_kind`, and `concept_type`. The second creates
`sentence_pending_imports` and backfills it from every live hint reference.
Both accept `--dry-run` and `--db-path`. A database created fresh from the
models needs neither.
