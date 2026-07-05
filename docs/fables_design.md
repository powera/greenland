# Fables ("Story Library") - Design

This document designs a **story library** alongside the concepts encyclopedia:
a place to store the *text itself* of a fable, folk tale, song, poem, or book
excerpt, separate from the encyclopedia entry *about* it. The flagship case is
the fable/folk tale -- "The Three Billy Goats Gruff" -- where today the only
thing the system could hold is an encyclopedia article about the story's
history and cultural impact, when what a language learner actually wants to
read is a retelling of the story.

We want **both**, as two different objects:

- The **Concept** (existing) stays the encyclopedia entry: origin, history,
  variants, cultural impact, adaptations. Nothing about concepts changes.
- The **text work** (new) is the story itself: a retelling of the fable, the
  text of a poem, the lyrics of a song, an excerpt of a book.

The two kinds of text work behave differently, and the design's central axis
is this split:

- **Retold works** (fables, folk tales, myths): there is *no single canonical
  text* -- the story exists as a tradition with many tellings. We author our
  own retelling (typically LLM-generated, then edited), we own it, and we can
  regenerate, simplify, and translate it freely.
- **Canonical works** (songs, poems, speeches, books): there *is* one
  authoritative text. It is transcribed, not generated; it must never be
  "regenerated"; and storing it raises licensing questions that retellings do
  not (see Licensing).

Design is deliberately implementation-free for now; this doc is the artifact.

## Problem

Today "The Three Billy Goats Gruff" can only enter the system as a `Concept`.
The Vovere generation prompt produces encyclopedia prose, so the result is an
article about the tale type, its Norwegian origins, and its place in
children's literature -- useful, but not the story. There is no table where a
retelling could live: `Concept.body` is defined as an encyclopedia entry,
`Lemma` is lexical, and `data/release/sentences` holds isolated sentences,
not connected narrative.

The same gap exists for canonical texts. A song or a poem can be filed today
as a sub-concept (`media_song`, `media_book` are existing sub-concept
categories) or as a main concept if prominent, but the lyrics or the poem
text itself has nowhere to go.

For a language-learning pipeline this matters: connected, familiar,
short-form narrative (fables, nursery rhymes, simple poems) is prime reading
material, and the eventual goal is retellings *in the target language* at
controlled difficulty.

## Non-Goals (for now)

- **No change to concepts.** Concepts remain encyclopedia entries; no new
  columns, no new `concept_type` values, no change to wiki-link semantics or
  the Voverukas rank graph (text works have no wiki links and never seed it).
- **No `data/release` export.** Like concepts, text works stay outside the
  lemma/GUID/release machinery. A future Trakaido "reading" export is a
  separate design (see Future Work) and only then would GUID questions arise.
- **No target-language generation in phase 1.** The schema supports
  per-language, per-difficulty versions from day one, but the first rollout
  only exercises the English reference telling.
- **No quotes yet.** Short attributed quotations ("famous quotes") are a
  plausible later citizen of this system; the design keeps the door open (see
  Future Work: Quotes) but adds nothing for them now.
- **No audio.** TTS narration of retellings is attractive (the audio client
  stack exists) but out of scope.

## Design Overview

Two new tables in the concepts database (same `Base`, same backend, same
"outside the lemma machinery" posture as `Concept`):

1. **`text_works`** -- one row per story/song/poem: identity, type, and the
   Q-id link to the encyclopedia. No body text here.
2. **`text_versions`** -- the actual texts: one row per (work, language,
   difficulty) rendering. A fable has only non-canonical versions (our
   retellings); a canonical work has exactly one version marked canonical
   (the authoritative text) plus, optionally, learner-oriented versions.

Splitting work from version is what makes the fable case and the canonical
case the *same system* instead of two: "canonical" is a property of one
version, not a different kind of table. It also gives the multilingual /
difficulty dimension a home from day one -- the same story naturally has an
English reference telling, a Lithuanian A2 telling, and a Lithuanian B1
telling, and those are versions of one work, not three works.

### Text types: a closed, partitioned vocabulary

Mirroring the tracked/excluded partition used for sub-concept categories, the
type vocabulary is hardcoded and partitioned by authority:

```python
# storage/models/text_work.py

# Types whose text is OUR OWN retelling: no canonical text exists, bodies are
# generated/edited freely, and no version may be marked canonical.
RETOLD_TEXT_TYPES: tuple[str, ...] = (
    "fable",        # Aesop-style, usually with a moral
    "folk_tale",    # Three Billy Goats Gruff, Gingerbread Man
    "fairy_tale",   # literary-tradition tales retold from the tradition
    "myth",         # Icarus, Prometheus
    "legend",       # King Arthur-type traditional narratives
)

# Types with a single authoritative text: exactly one version is canonical,
# it is transcribed rather than generated, and licensing must be recorded.
CANONICAL_TEXT_TYPES: tuple[str, ...] = (
    "poem",
    "song",           # lyrics
    "nursery_rhyme",
    "speech",
    "short_story",
    "book_excerpt",   # a self-contained passage, never a whole book
)

ALL_TEXT_TYPES: tuple[str, ...] = RETOLD_TEXT_TYPES + CANONICAL_TEXT_TYPES
```

Notes on the boundary:

- The split is about **textual authority, not genre**. A specific literary
  fairy tale with a fixed text (a particular Andersen story) is
  `short_story`/`book_excerpt` (canonical); "Cinderella" as a tale type is
  `fairy_tale` (retold). When both readings exist they are two different
  works with two different Q-ids, which is exactly how Wikidata models it
  (tale-type Q-id vs. specific-publication Q-id).
- `nursery_rhyme` is canonical even though rhymes have variants: there is a
  dominant fixed wording, and we should not "retell" a rhyme.
- Authority is **derived from the type** (`is_retold_text_type(t)`), not a
  separate column -- one source of truth, no way for a row to contradict
  itself.

### Schema: `text_works`

```python
class TextWork(Base):
    """A story/song/poem whose text (in one or more versions) we store.

    The encyclopedia entry ABOUT the work stays a Concept/SubConcept; this row
    is the anchor for the work's actual text(s) in text_versions.
    """

    __tablename__ = "text_works"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Canonical underscore-joined slug, reusing normalize_concept_slug().
    # Separate namespace from concepts: wiki links never target works, so a
    # slug may freely coexist in concepts/sub_concepts/text_works.
    slug: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)

    # Required type from ALL_TEXT_TYPES; authority (retold vs canonical) is
    # derived from it. Indexed for the library's type filter.
    text_type: Mapped[str] = mapped_column(String, nullable=False, index=True)

    # Wikidata Q-id of the work, when it has one. This is the ONLY link to the
    # encyclopedia: it resolves through concept_wikidata_index to whichever
    # entry (main concept or sub-concept) covers the topic. Nullable -- a work
    # may have no Q-id (an obscure local tale) and no encyclopedia entry at
    # all. Unique: one library anchor per Q-id.
    qid: Mapped[Optional[str]] = mapped_column(String, unique=True, nullable=True, index=True)

    # Attribution line for canonical works ("Robert Frost", "trad. Norwegian").
    # Display-only; the structured link to a person stays the concept graph.
    attribution: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # One-sentence description ("A troll under a bridge meets three goats.").
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Review metadata (house conventions).
    verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    added_at / updated_at  # server defaults, as elsewhere
```

Deliberately absent: `body` (lives on versions), `tags`, `parent_work_id`
(collections like "Aesop's Fables" are concepts, not works), and any
quote-specific fields. Each can be added later as a nullable column.

### Schema: `text_versions`

```python
class TextVersion(Base):
    """One rendering of a work: a specific language x difficulty text.

    For retold works every version is ours (is_canonical always False).
    For canonical works exactly one version is the authoritative text
    (is_canonical=True, transcribed, license recorded); learner-oriented
    translations may sit beside it as non-canonical versions.
    """

    __tablename__ = "text_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    work_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("text_works.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )

    # Language of THIS text, using the language codes from
    # storage.translation_helpers (never a local mapping).
    lang: Mapped[str] = mapped_column(String, nullable=False, index=True)

    # True only for the single authoritative text of a canonical-type work.
    is_canonical: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Target difficulty for learner-oriented versions, same integer scale as
    # lemma difficulty levels. NULL for the canonical text and for the plain
    # English reference telling (neither is difficulty-targeted).
    difficulty_level: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # The text itself. Markdown, NO [[wiki links]] -- these are stories, not
    # encyclopedia entries, and they never feed the rank graph. Nullable so a
    # canonical work whose text we cannot store (license) can still exist as
    # a metadata-only version (see Licensing).
    body: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # --- provenance: exactly one of the two flavors is populated ---
    # Retold/generated versions (mirrors Concept conventions):
    source_model: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    # Canonical/transcribed versions:
    text_source: Mapped[Optional[str]] = mapped_column(String, nullable=True)   # where transcribed from
    license: Mapped[Optional[str]] = mapped_column(String, nullable=True)       # e.g. "public-domain"

    verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    added_at / updated_at
```

Version-level invariants, enforced in the CRUD layer (the same posture as the
sub-concepts one-target guard on pre-migration SQLite):

1. **At most one canonical version per work**, and only when the work's type
   is in `CANONICAL_TEXT_TYPES`. Retold-type works can never have one.
2. **At most one version per (work, lang, difficulty_level)** slot, treating
   NULL difficulty as its own slot. This is CRUD-enforced rather than a
   `UniqueConstraint` because SQLite treats NULLs as distinct in unique
   indexes; a plain composite index supports the lookups.
3. **Canonical versions require `license`** and are edit-locked in the UI
   except for transcription fixes; they are never fed to a generator.

### Linking to the encyclopedia: Q-id, not the index pointers

`concept_wikidata_index` keeps its strict `concept_id XOR sub_concept_id`
shape -- a text work is **not** a third mutually exclusive target, because a
work *coexists* with its encyclopedia entry rather than replacing it (Three
Billy Goats Gruff should have both a concept and a retelling; a song keeps
its `media_song` sub-concept and gains lyrics). So the link is simply
`text_works.qid`, resolved through the index at read time -- the same pattern
`ConceptLemmaLink.qid` already uses to stay decoupled from the concepts
backend.

Consequences:

- Concept and sub-concept detail pages can show a "Read the story" /
  "Text available" box with one indexed lookup (`text_works.qid == row.qid`).
- The work detail page links back to whatever the index resolves the Q-id to
  (main concept, sub-concept, or nothing yet).
- Filing order is free: work first, encyclopedia entry first, or only ever
  one of the two. Nothing requires the other to exist.
- Wiki links (`[[...]]`, `[[Q...]]`) continue to resolve only to
  concepts/sub-concepts. A red link never becomes "wanted" or "existing"
  because of a text work; the encyclopedia and the library have separate
  slug namespaces by construction.

### Licensing (canonical works)

Retellings are our own text -- generated from the tale as a tradition, not
translated from someone's copyrighted retelling -- so retold versions carry
no license field and no restrictions.

Canonical texts are someone's fixed words:

- A canonical version with a stored `body` **must** carry `license`
  (public-domain, an explicit free license, or developer-authored) and
  `text_source`. Song lyrics in particular are usually still in copyright.
- A canonical work whose text we cannot store is still worth filing: the
  `TextWork` row plus a body-less canonical version records the decision and
  the metadata, exactly parallel to how excluded sub-concepts record "we
  looked at this and are deliberately not doing it".
- Learner *translations we author ourselves* of a public-domain canonical
  text are fine (non-canonical versions). Simplified adaptations of
  in-copyright works are derivative and are not made.

### Alternatives considered

- **Single `fables` table with one body column** -- rejected. It either
  forces songs/poems into a table named for retellings or forces a second
  near-identical table later; and the moment a Lithuanian telling is wanted,
  a one-body table needs a churny migration to exactly this work/version
  split. The split costs one join now and saves a remodel later.
- **A third pointer on `concept_wikidata_index`** -- rejected. The index's
  CHECK constraint encodes "one encyclopedia home per Q-id"; a work is not an
  encyclopedia home, and making the constraint `concept XOR sub_concept XOR
  work` would wrongly forbid a story from having both an article and a text.
- **Fables as a `concept_type` (or the body-on-concept "story mode")** --
  rejected. It would overload `Concept.body`'s meaning, drag story text into
  the rank graph and wanted-pages machinery, and still leave nowhere for a
  second language or difficulty level.
- **Storing retellings per-sentence in the sentences machinery** -- rejected
  for authoring; narrative flow is the point. Mining sentences *out* of
  finished retellings stays open as future work.
- **A generic `authority` column instead of deriving from `text_type`** --
  rejected; two sources of truth that can disagree, for no modeling gain.

## Integration Points

### 1. Storage (`storage/models/text_work.py`, `storage/crud/text_work.py`, `storage/queries/text_work.py`)

- New model module holding both classes and the type vocabulary; reuses
  `normalize_concept_slug` / `concept_slug_to_title` from
  `storage.models.concept` rather than duplicating slug logic.
- CRUD: `create_text_work`, `get_text_work_by_slug`, `get_text_work_by_qid`,
  `update_text_work`, `delete_text_work` (cascades versions);
  `create_text_version`, `update_text_version`, `delete_text_version` -- the
  create/update paths enforce the three invariants above and validate
  `text_type` against `ALL_TEXT_TYPES` and `lang` via `translation_helpers`.
- Queries: `list_text_works(search, text_type, limit, offset)` +
  `count_text_works` with the concepts search semantics (slug + summary,
  space/underscore equivalence); `get_text_work_for_qid` for the
  concept-page cross-link box.
- Service: `create_text_work_from_qid(session, qid, text_type)` mirroring
  `create_concept_from_qid` -- resolve the seed (title, summary), create the
  work, no version yet. Idempotent on `qid`. Per project policy, flows that
  resolve Q-ids make live Wikidata calls and need developer confirmation.

### 2. Generation agent: Lapė (`agents/lape/lape.py`)

New agent, named for the fox -- the classic fable protagonist. Scope is
**retold versions only**; it refuses canonical-type works outright.

- Input: a `TextWork` (retold type) + target `lang` + optional
  `difficulty_level`; prompts live at `prompts/fables/retelling/`
  (`context.txt` + `prompt.txt` via `util.prompt_loader`, as Vovere does with
  `prompts/concepts/entry/`).
- The prompt asks for a *telling*, not an article: narrative voice, dialogue,
  the moral where the genre has one -- and explicitly forbids encyclopedic
  framing ("The Three Billy Goats Gruff is a Norwegian fairy tale...") and
  wiki links.
- Unlike Vovere it does not fetch source URLs in phase 1: the tale as a
  tradition is in-model knowledge, and the work's `summary` pins which story
  is meant. A `--source` option can be added later for obscure tales.
- Writes the result as a `TextVersion` with `source_model`/`confidence`
  provenance; regeneration overwrites only unverified versions.
- Phase 1 CLI generates the English reference telling
  (`lang=en, difficulty_level=NULL`); the same plumbing later serves
  target-language and difficulty-targeted runs (see Future Work).

### 3. Barsukas UI (`barsukas/routes/texts.py` + templates)

- **Library list** (`/texts`): search + type filter (ordinary GET form,
  select grouped into Retold / Canonical optgroups), showing per-work
  language/version chips.
- **Work detail** (`/texts/<slug>`): summary, encyclopedia cross-link
  (via Q-id through the index), version table, and per-version reader view.
  Retold works get a "Generate telling" button (ordinary POST form);
  canonical works instead get "Add canonical text" (paste + `text_source` +
  required `license` select).
- **New-work form** (`/texts/new`): Q-id (preferred; seeds title/summary) or
  manual title, plus the type select.
- **Concept & sub-concept detail pages**: a small "Texts" box when
  `text_works.qid` matches -- the only touch on existing pages.
- House style throughout: ordinary form submits, no AJAX, no inline CSS/JS;
  verify in the developer's local browser (no tests required for Barsukas).

### 4. Explicitly untouched

- Voverukas rank graph and wanted lists (works have no wiki links and no
  encyclopedia slugs).
- `data/release`, GUIDs, lemma machinery, sentences.
- Vovere/Voveraite (concept generation and intake are unchanged; Voveraite
  should not grow a `--text` mode until intake batches of works actually
  exist).

## Migration

`src/storage/migrations/add_text_works.py`, following the
`add_sub_concepts.py` pattern (idempotent, backend-agnostic, `--postgres` /
`--dry-run`): create `text_works` and `text_versions` if missing; fresh
databases get both from `Base.metadata.create_all`. No index changes, no
backfill -- populating the library is curation, not migration.

## Rollout Steps

1. **Schema**: models + vocabulary, CRUD with the three invariants,
   migration, unit tests (`src/tests/storage/test_text_works.py`).
2. **Service**: `create_text_work_from_qid`, queries, cross-link lookup.
3. **Lapė**: prompts + agent + CLI, English reference tellings for a starter
   set of fables/folk tales.
4. **Barsukas**: library list/detail/forms, concept-page cross-link box.
5. **Later, each a separate design**: target-language generation, Trakaido
   export, audio, quotes.

## Future Work

- **Target-language and difficulty-targeted tellings.** The schema slots are
  ready. The interesting question is pipeline shape: generate directly in the
  target language, or translate/adapt from the verified English reference?
  Recommendation to explore first: adapt from the reference telling so the
  story stays fixed while language complexity varies.
- **Vocabulary-controlled retellings.** The killer feature for Trakaido:
  constrain a telling to lemmas at or below a difficulty level, plus a
  coverage report (share of tokens findable in release lemmas) as a
  Barsukas-visible metric per version. This is the first real bridge between
  the library and the lemma database.
- **Trakaido reading export.** A new file family (not lemmas, not
  sentences); would need its own GUID-prefix decision and release design.
- **Audio narration.** TTS via the existing audio clients, per version.
- **Sentence mining.** Extracting aligned example sentences from parallel
  tellings into the sentences machinery.

### Future Work: Quotes

Quotes ("famous quotations") were flagged as a likely later addition, and
they stress the model in ways worth recording now, so that nothing in this
design blocks them:

- A quote is canonical (fixed wording -- authority-wise it fits
  `CANONICAL_TEXT_TYPES`), but unlike the other canonical types it is
  **many-per-anchor**: dozens of quotes attach to one person or one book,
  while `text_works.qid` is deliberately `UNIQUE`. So quotes are **not** just
  a new `text_type`; forcing them in would mean dropping that uniqueness and
  polluting work-level identity (most quotes have no Q-id and no sensible
  slug of their own).
- The likely shape is a separate lightweight `quotes` table (body, attributed
  Q-id, optional source-work reference, license/provenance), closer in spirit
  to `sub_concepts` than to `text_works` -- cheap rows hanging off the shared
  Q-id spine, browsable per anchor.
- What this design already provides for that future: the Q-id-column linking
  pattern (no index changes needed), the licensing posture for canonical
  words, and the retold/canonical vocabulary quotes can reuse for
  validation. What it deliberately does not do is widen `text_works` to
  "anything textual" -- works are page-length, individually-titled objects,
  and keeping that narrow is what keeps both systems simple.

## Open Questions

1. **Reference-language policy.** Is the English telling always the master
   from which other languages adapt, or may a Lithuanian telling be authored
   first for tales where that is more natural? (Affects only the Lapė
   pipeline, not the schema.)
2. **Fable morals.** Store the moral inside the body (last line, as told) or
   as a structured column for app display? Recommendation: in the body for
   phase 1; a nullable `moral` column on versions is a cheap later addition.
3. **Difficulty scale.** Reuse the lemma difficulty integers as assumed here,
   or adopt CEFR labels for texts? Reusing the existing scale keeps the
   future vocabulary-coverage bridge trivial, so that is the default.
4. **Lemma links.** Titles like "Gingerbread Man" are not headwords, but some
   one-word titles could be. `ConceptLemmaLink` already links lemma to Q-id
   independently of this system, so no action -- noted only to record that no
   `TextWorkLemmaLink` is planned.
