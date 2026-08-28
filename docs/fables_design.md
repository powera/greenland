# Fables ("Story Library") - Design

This document designs a **story library** alongside the concepts encyclopedia:
a place to store the *text itself* of a fable, folk tale, conversation, song,
poem, or book excerpt, separate from the encyclopedia entry *about* it. The
flagship case is the fable/folk tale -- "The Three Billy Goats Gruff" -- where
today the only thing the system could hold is an encyclopedia article about
the story's history and cultural impact, when what a language learner
actually wants to read is a retelling of the story.

We want **both**, as two different objects:

- The **Concept** (existing) stays the encyclopedia entry: origin, history,
  variants, cultural impact, adaptations -- and the *analysis*, including a
  fable's moral and its interpretation. Nothing about concepts changes.
- The **text work** (new) is the story itself: a retelling of the fable, a
  constructed conversation, the text of a poem, the lyrics of a song, an
  excerpt of a book.

The two kinds of text work behave differently, and the design's central axis
is this split:

- **Authored works** (fables, folk tales, myths, conversations): the text is
  *ours*. For traditional stories there is no single canonical text -- the
  story exists as a tradition with many tellings, and we author our own
  retelling (typically LLM-generated, then edited). Conversations are original
  compositions with no tradition behind them at all. Either way we own the
  text and can regenerate, simplify, and rewrite it freely.
- **Canonical works** (songs, poems, speeches, books, quotes): there *is* one
  authoritative text. It is transcribed, not generated; it must never be
  "regenerated"; and storing it raises licensing questions that authored
  texts do not (see Licensing).

The system is now implemented; see Implementation Status at the end for the
file map, implementation notes, and what remains.

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
short-form text (fables, conversations, nursery rhymes, simple poems) is
prime reading material.

## Non-Goals (for now)

- **No change to concepts.** Concepts remain encyclopedia entries; no new
  columns, no new `concept_type` values, no change to wiki-link semantics or
  the Voverukas rank graph (text works have no wiki links and never seed it).
- **English only.** All stored texts are English for now. The schema carries
  a `lang` column so nothing needs remodeling if that changes, but no
  non-English generation, translation, or intake is designed here.
- **No `data/release` export.** Like concepts, text works stay outside the
  lemma/GUID/release machinery. A future Trakaido "reading" export is a
  separate design (see Future Work) and only then would GUID questions arise.
- **No archive ambitions.** The library is a curated shelf, not a corpus of
  songs/books/poems (see Scope below). Having an encyclopedia entry for a
  song never implies its lyrics get stored.
- **No quote intake yet.** Quotes are a planned later citizen and the schema
  prepares for them now (see Quotes), but no quote UI, agent, or intake flow
  is part of phase 1.
- **No audio.** TTS narration of retellings is attractive (the audio client
  stack exists) but out of scope.

## Scope: a curated shelf, not an archive

For authored types the scope question mostly answers itself: we write a
telling because we want learners to read it, and each telling is deliberate
work. For canonical types the temptation is archival ("store the lyrics of
every song that has a sub-concept"), and that is explicitly not the goal.
The honest position is that the dividing line is **not fully clear yet**
(tracked as an open question); the working criteria for storing a canonical
text are:

1. **Learner value first**: short, self-contained, readable on one page --
   a nursery rhyme, a famous short poem, a well-known speech passage. Never
   a whole book (`book_excerpt` is the type for a reason).
2. **Cultural currency**: the text is something a learner plausibly
   encounters or references; roughly the same prominence judgement that
   separates main concepts from sub-concepts, applied to texts.
3. **License-clean** (see Licensing): if we cannot store the body, we
   usually should not create the work at all -- metadata-only canonical
   works are for the rare case where the *decision* is worth recording.
4. **Default is no**: filing a song/book as a (sub-)concept is routine
   encyclopedia curation; adding its text to the library is a separate,
   deliberate act.

## Design Overview

Two new tables in the concepts database (same `Base`, same backend, same
"outside the lemma machinery" posture as `Concept`):

1. **`text_works`** -- one row per story/conversation/song/poem: identity,
   type, attribution, and the Q-id links to the encyclopedia. No body text
   here.
2. **`text_versions`** -- the actual texts: one row per (work, language,
   difficulty) rendering. An authored work has only non-canonical versions
   (our texts); a canonical work has exactly one version marked canonical
   (the authoritative text).

Splitting work from version is what makes the fable case and the canonical
case the *same system* instead of two: "canonical" is a property of one
version, not a different kind of table. It also gives difficulty-targeted
retellings (and, later, other languages) a home without remodeling -- the
same story can have a reference telling and an easier telling as versions of
one work, not two works.

### Text types: a closed, partitioned vocabulary

Mirroring the tracked/excluded partition used for sub-concept categories, the
type vocabulary is hardcoded and partitioned by authority:

```python
# storage/models/text_work.py

# Types whose text is OUR OWN: generated/edited freely, no version may be
# marked canonical, no license needed.
AUTHORED_TEXT_TYPES: tuple[str, ...] = (
    "fable",         # Aesop-style traditional tale
    "folk_tale",     # Three Billy Goats Gruff, Gingerbread Man
    "fairy_tale",    # literary-tradition tales retold from the tradition
    "myth",          # Icarus, Prometheus
    "legend",        # King Arthur-type traditional narratives
    "conversation",  # original constructed dialogue (cafe, doctor, airport)
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
    "quote",          # reserved: no intake in phase 1 (see Quotes)
)

ALL_TEXT_TYPES: tuple[str, ...] = AUTHORED_TEXT_TYPES + CANONICAL_TEXT_TYPES
```

Notes on the boundary:

- The split is about **textual authority, not genre**. A specific literary
  fairy tale with a fixed text (a particular Andersen story) is
  `short_story`/`book_excerpt` (canonical); "Cinderella" as a tale type is
  `fairy_tale` (authored retelling). When both readings exist they are two
  different works with two different Q-ids, which is exactly how Wikidata
  models it (tale-type Q-id vs. specific-publication Q-id).
- `conversation` sits in the authored group because it shares every behavior
  that matters (we write it, we regenerate it, no license) even though it is
  an original composition rather than a retelling. Most conversations have
  no Q-id and no encyclopedia entry, which the schema permits.
- `nursery_rhyme` is canonical even though rhymes have variants: there is a
  dominant fixed wording, and we should not "retell" a rhyme.
- Authority is **derived from the type** (`is_authored_text_type(t)`), not a
  separate column -- one source of truth, no way for a row to contradict
  itself.

### Schema: `text_works`

```python
class TextWork(Base):
    """A story/conversation/song/poem whose text we store (in text_versions).

    The encyclopedia entry ABOUT the work stays a Concept/SubConcept; this row
    is the anchor for the work's actual text(s).
    """

    __tablename__ = "text_works"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Canonical underscore-joined slug, reusing normalize_concept_slug().
    # Separate namespace from concepts: wiki links never target works, so a
    # slug may freely coexist in concepts/sub_concepts/text_works.
    slug: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)

    # Required type from ALL_TEXT_TYPES; authority (authored vs canonical) is
    # derived from it. Indexed for the library's type filter.
    text_type: Mapped[str] = mapped_column(String, nullable=False, index=True)

    # Wikidata Q-id of the work ITSELF, when it has one. Resolves through
    # concept_wikidata_index to whichever entry (main concept or sub-concept)
    # covers the topic. Nullable -- conversations and obscure tales have
    # none. Unique: one library anchor per work Q-id.
    qid: Mapped[Optional[str]] = mapped_column(String, unique=True, nullable=True, index=True)

    # Wikidata Q-id of the ATTRIBUTED person/source (poet, singer, speaker;
    # for quotes, the person quoted). Non-unique by design: many works hang
    # off one person. This is the quote-readiness column (see Quotes) and is
    # useful for every canonical type from day one.
    attribution_qid: Mapped[Optional[str]] = mapped_column(String, nullable=True, index=True)

    # Display attribution line ("Robert Frost", "trad. Norwegian"). The
    # structured link is attribution_qid; this is what pages render.
    attribution: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # One-sentence description ("A troll under a bridge meets three goats.").
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Review metadata (house conventions).
    verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    added_at / updated_at  # server defaults, as elsewhere
```

Deliberately absent: `body` (lives on versions), `tags`, `parent_work_id`
(collections like "Aesop's Fables" are concepts, not works), and any further
quote-specific fields. Each can be added later as a nullable column.

### Schema: `text_versions`

```python
class TextVersion(Base):
    """One rendering of a work: a specific language x difficulty text.

    For authored works every version is ours (is_canonical always False).
    For canonical works exactly one version is the authoritative text
    (is_canonical=True, transcribed, license recorded).
    """

    __tablename__ = "text_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    work_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("text_works.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )

    # Language of THIS text, using the language codes from
    # storage.translation_helpers (never a local mapping). English-only for
    # now ("en" everywhere); the column exists so going multilingual later is
    # data, not a migration.
    lang: Mapped[str] = mapped_column(String, nullable=False, index=True)

    # True only for the single authoritative text of a canonical-type work.
    is_canonical: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Target difficulty for learner-oriented versions, same integer scale as
    # lemma difficulty levels. NULL for the canonical text and for the plain
    # reference telling (neither is difficulty-targeted).
    difficulty_level: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # The text itself. Markdown, NO [[wiki links]] -- these are stories, not
    # encyclopedia entries, and they never feed the rank graph. Nullable so a
    # canonical work whose text we cannot store (license) can still exist as
    # a metadata-only version (see Licensing).
    body: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # --- provenance: exactly one of the two flavors is populated ---
    # Authored/generated versions (mirrors Concept conventions):
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
   is in `CANONICAL_TEXT_TYPES`. Authored-type works can never have one.
2. **At most one version per (work, lang, difficulty_level)** slot, treating
   NULL difficulty as its own slot. This is CRUD-enforced rather than a
   `UniqueConstraint` because SQLite treats NULLs as distinct in unique
   indexes; a plain composite index supports the lookups.
3. **Canonical versions require `license`** and are edit-locked in the UI
   except for transcription fixes; they are never fed to a generator.

### Linking to the encyclopedia: Q-ids, not the index pointers

`concept_wikidata_index` keeps its strict `concept_id XOR sub_concept_id`
shape -- a text work is **not** a third mutually exclusive target, because a
work *coexists* with its encyclopedia entry rather than replacing it (Three
Billy Goats Gruff should have both a concept and a retelling; a song keeps
its `media_song` sub-concept and gains lyrics). So the links are plain Q-id
columns on `text_works`, resolved through the index at read time -- the same
pattern `ConceptLemmaLink.qid` already uses to stay decoupled from the
concepts backend.

Two links, two directions:

- `qid` (unique): *this work's* encyclopedia identity. A concept/sub-concept
  detail page shows a "Read the story" / "Text available" box with one
  indexed lookup.
- `attribution_qid` (non-unique): *whose words these are*. A person's concept
  page can list every poem, speech, and (later) quote attributed to them with
  one indexed lookup the other way.

Filing order is free: work first, encyclopedia entry first, or only ever one
of the two. Nothing requires the other to exist -- conversations typically
have neither Q-id. Wiki links (`[[...]]`, `[[Q...]]`) continue to resolve
only to concepts/sub-concepts; a red link never becomes "wanted" or
"existing" because of a text work, and the encyclopedia and the library keep
separate slug namespaces by construction.

### Story vs. analysis

The retelling tells the story; the encyclopedia explains it. In particular a
fable's **moral** and its interpretation live in the `Concept` body (the
analysis), not as structured data on the text work. A telling may of course
end the way the tale traditionally ends, but the library never grows a
`moral` column, and the generation prompt is explicitly barred from
appending an analytic moral paragraph -- that is concept material.

### Licensing (canonical works)

Authored texts are our own -- retellings are generated from the tale as a
tradition (not translated from someone's copyrighted retelling), and
conversations are original -- so authored versions carry no license field
and no restrictions.

Canonical texts are someone's fixed words:

- A canonical version with a stored `body` **must** carry `license`
  (public-domain, an explicit free license, or developer-authored) and
  `text_source`. Song lyrics in particular are usually still in copyright.
- Per the Scope rules, an unstorable text usually means the work is simply
  not filed; a metadata-only canonical version (body NULL, license reason in
  `notes`) is the exception for recording a deliberate "looked at it,
  cannot/will not store it" decision.
- Simplified adaptations of in-copyright works are derivative and are not
  made.

### Alternatives considered

- **Single `fables` table with one body column** -- rejected. It either
  forces songs/poems into a table named for retellings or forces a second
  near-identical table later; and difficulty-targeted tellings (or any
  future second language) would need a churny migration to exactly this
  work/version split. The split costs one join now and saves a remodel
  later.
- **A third pointer on `concept_wikidata_index`** -- rejected. The index's
  CHECK constraint encodes "one encyclopedia home per Q-id"; a work is not an
  encyclopedia home, and making the constraint three-way would wrongly forbid
  a story from having both an article and a text.
- **Fables as a `concept_type` (or a body-on-concept "story mode")** --
  rejected. It would overload `Concept.body`'s meaning, drag story text into
  the rank graph and wanted-pages machinery, and conflate the story with its
  analysis (moral etc.), which this design deliberately separates.
- **A separate future `quotes` table** (earlier revision of this design) --
  dropped in favor of preparing here: with `attribution_qid` carrying the
  many-per-person anchor and `qid` staying unique for the rare quote that has
  its own Q-id, a quote is just a small canonical work, and a second
  table would duplicate versions, licensing, and the Barsukas surface.
- **Storing retellings per-sentence in the sentences machinery** -- rejected
  for authoring; narrative flow is the point. Mining sentences *out* of
  finished texts stays open as future work.
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
  create/update paths enforce the three invariants above, validate
  `text_type` against `ALL_TEXT_TYPES` (rejecting `quote` until its intake
  phase lands) and `lang` via `translation_helpers` (accepting only "en" for
  now).
- Queries: `list_text_works(search, text_type, limit, offset)` +
  `count_text_works` with the concepts search semantics (slug + summary +
  attribution, space/underscore equivalence); `get_text_work_by_qid` (CRUD)
  for the concept-page cross-link box; `list_text_works_attributed_to(qid)`
  for the person-page listing.
- Service: `create_text_work_from_qid(session, qid, text_type)` mirroring
  `create_concept_from_qid` -- resolve the seed (title, summary), create the
  work, no version yet. Idempotent on `qid`. Per project policy, flows that
  resolve Q-ids make live Wikidata calls and need developer confirmation.

### 2. Generation agent: Ožys (`agents/ozys/ozys.py`)

New agent, named for the billy goat -- a nod to the story that motivated the
system ("lapė" is already taken by the grammar-facts agent). Scope is
**authored versions only**; it refuses canonical-type works outright.

- Input: a `TextWork` (authored type) + optional `difficulty_level`
  (`lang` fixed to "en" for now); prompts live under `prompts/fables/`
  (`retelling/` for the traditional-tale types, `conversation/` for
  dialogues -- each a `context.txt` + `prompt.txt` pair via
  `util.prompt_loader`, as Vovere does with `prompts/concepts/entry/`).
- The retelling prompt asks for a *telling*, not an article: narrative
  voice, dialogue, ending the way the tale ends -- and explicitly forbids
  encyclopedic framing ("The Three Billy Goats Gruff is a Norwegian fairy
  tale..."), analytic moral paragraphs (analysis is concept material), and
  wiki links. The conversation prompt takes the work's `summary` as the
  scenario brief and asks for a natural short dialogue.
- Unlike Vovere it does not fetch source URLs in phase 1: the tale as a
  tradition is in-model knowledge, and the work's `summary` pins which story
  is meant. A `--source` option can be added later for obscure tales.
- Writes the result as a `TextVersion` with `source_model`/`confidence`
  provenance; regeneration overwrites only unverified versions.

### 3. Barsukas UI (`barsukas/routes/texts.py` + templates)

- **Library list** (`/texts`): search + type filter (ordinary GET form,
  select grouped into Authored / Canonical optgroups), showing per-work
  version chips.
- **Work detail** (`/texts/<slug>`): summary, attribution, encyclopedia
  cross-links (work Q-id and attribution Q-id through the index), version
  table, and per-version reader view. Authored works get a "Generate
  telling" button (ordinary POST form); canonical works instead get "Add
  canonical text" (paste + `text_source` + required `license` select).
- **New-work form** (`/texts/new`): Q-id (preferred; seeds title/summary) or
  manual title (the only route for conversations), plus the type select.
- **Concept & sub-concept detail pages**: a small "Texts" box when
  `text_works.qid` matches, and an "Attributed texts" list when
  `attribution_qid` matches (person pages) -- the only touch on existing
  pages.
- House style throughout: ordinary form submits, no AJAX, no inline CSS/JS;
  verify in the developer's local browser (no tests required for Barsukas).

### 4. Explicitly untouched

- Voverukas rank graph and wanted lists (works have no wiki links and no
  encyclopedia slugs).
- `data/release`, GUIDs, lemma machinery, sentences.
- Vovere/Voveraite (concept generation and intake are unchanged; Voveraite
  should not grow a `--text` mode until intake batches of works actually
  exist).

## Schema rollout

Normal model initialization creates `text_works` and `text_versions` when they
are missing. No dated migration is needed because there is no data backfill;
populating the library is curation, not migration.

## Rollout Steps

The code for steps 1-4 is implemented; see Implementation Status below.
Generating the starter set of tellings (LLM cost, developer-run) and step 5
remain.

1. **Schema**: models + vocabulary (including the reserved `quote` type and
   `attribution_qid`), CRUD with the three invariants, migration, unit tests
   (`src/tests/storage/test_text_works.py`).
2. **Service**: `create_text_work_from_qid`, queries, cross-link lookups.
3. **Ožys**: prompts + agent + CLI; English tellings for a starter set of
   fables/folk tales and a few conversations.
4. **Barsukas**: library list/detail/forms, concept-page cross-link boxes.
5. **Later, each a separate design**: quote intake, target languages,
   Trakaido export, audio.

## Future Work

- **Quote intake.** The schema is ready (see Quotes below); what remains is
  the curation surface: a per-person quote list view, a lightweight add form
  (body + attribution_qid + source), slug conventions for quote titles
  (first words), and a policy for sourcing/verifying wording. Deliberately
  its own phase so the library ships without waiting on it.
- **Difficulty-targeted tellings.** Same work, easier telling, using the
  lemma difficulty integers; pairs with a **vocabulary coverage report**
  (share of tokens findable in release lemmas at level <= N) as a
  Barsukas-visible metric per version -- the first real bridge between the
  library and the lemma database, and the killer feature for Trakaido.
- **Other languages.** The `lang` column is waiting; the open pipeline
  question (generate directly vs. adapt from the verified English telling)
  is deferred until English content proves out.
- **Trakaido reading export.** A new file family (not lemmas, not
  sentences); would need its own GUID-prefix decision and release design.
- **Audio narration.** TTS via the existing audio clients, per version.
- **Sentence mining.** Extracting example sentences from tellings into the
  sentences machinery.

### Quotes: prepared now, built later

Quotes stress the model in one specific way, and the schema absorbs it now
so their later arrival is additive:

- A quote is canonical (fixed wording, license/provenance matter) but
  **many-per-anchor**: dozens of quotes attach to one person, while
  `text_works.qid` is deliberately `UNIQUE`. The resolution is
  `attribution_qid`: the person anchor is non-unique by design, `qid` stays
  reserved for the rare quote that has its own Wikidata identity, and most
  quote rows simply leave `qid` NULL.
- A quote row is then an ordinary small work: `text_type="quote"`, slug from
  the first words, one canonical version whose body is a line or two,
  `text_source` saying where the wording was verified.
- The type string is in the vocabulary from day one (so nothing downstream
  hardcodes an assumption that canonical works are page-length), but CRUD
  rejects it until the intake phase, so no half-supported quotes appear
  meanwhile.
- What quotes are *not*: `conversation` is ours and invented; `quote` is
  someone's actual recorded words. The authored/canonical partition already
  encodes that difference.

## Open Questions

1. **Where exactly is the canonical-works dividing line?** The Scope
   criteria (learner value, cultural currency, license-clean, default-no)
   are a working position, not a settled one. Suggestion: keep the criteria
   advisory, let the first few dozen curation decisions accumulate in
   `notes`, and revisit once real cases exist -- the same way the
   main/sub-concept prominence line was settled by judgement rather than
   rule.
2. **Difficulty scale.** Reuse the lemma difficulty integers as assumed
   here, or adopt CEFR labels for texts? Reusing the existing scale keeps
   the future vocabulary-coverage bridge trivial, so that is the default.
3. **Conversation topical anchors.** Conversations have no Q-id, but a
   "conversation at the doctor's office" is *about* a topic that may have a
   concept. Is `attribution_qid` misuse for that (probably yes), a future
   `topic_qid` column, or just `notes`? Default: leave unanchored for now.
4. **Lemma links.** Titles like "Gingerbread Man" are not headwords, but
   some one-word titles could be. `ConceptLemmaLink` already links lemma to
   Q-id independently of this system, so no action -- noted only to record
   that no `TextWorkLemmaLink` is planned.

## Implementation Status

Rollout steps 1-4 are implemented (July 2026, this branch). Step 5 items
(quote intake, other languages, Trakaido export, audio) remain future
designs, and the starter set of tellings has not been generated yet.

### File map

| Piece | Where |
|-------|-------|
| Schema + vocabulary | `src/storage/models/text_work.py` (`TextWork`, `TextVersion`, `AUTHORED_TEXT_TYPES` / `CANONICAL_TEXT_TYPES` / `TEXT_TYPE_GROUPS`, `SUPPORTED_TEXT_VERSION_LANGS`); re-exported from `storage/models/__init__.py` |
| CRUD + invariants | `src/storage/crud/text_work.py` |
| Queries | `src/storage/queries/text_work.py` |
| Service | `src/storage/text_work_service.py` (`create_text_work_from_qid` -> `TextWorkCreationResult`) |
| Migration | `src/storage/migrations/add_text_works.py` |
| Agent | `src/agents/ozys/` (`OzysAgent` + CLI) |
| Prompts | `prompts/fables/retelling/` and `prompts/fables/conversation/` (`context.txt` + `prompt.txt`) |
| Barsukas | `src/barsukas/routes/texts.py` (blueprint `texts`, `/texts`) + `templates/texts/{list,form,detail,version_form}.html`; Texts cross-link boxes in `concepts/detail.html` and `concepts/sub_detail.html`; `render_text_body` in `barsukas/helpers/wikilinks.py`; nav entry in `base.html` |
| Tests | `src/tests/storage/test_text_works.py` (12 tests) |

### Implementation notes (where the code refines the draft above)

- **Quote deferral is a first-class mechanism**: `INTAKE_DEFERRED_TEXT_TYPES
  = ("quote",)` plus `is_intake_deferred_text_type()`. CRUD, the service, and
  the Barsukas type select all consult it, so enabling quote intake later is
  a one-line vocabulary change plus the dedicated curation surface.
- **Nullable-field updates**: `update_text_work` / `update_text_version` use
  an `_UNSET` sentinel so `qid`, `attribution_qid`, and `difficulty_level`
  can be explicitly cleared (None) as distinct from "not supplied".
- **Cascade**: `TextWork.versions` uses ORM `cascade="all, delete-orphan"`,
  so deleting a work deletes its versions even on SQLite sessions without FK
  enforcement (the FK also declares `ondelete="CASCADE"` for Postgres).
- **Naming**: the by-Q-id lookup landed as `get_text_work_by_qid` (CRUD),
  not the draft's `get_text_work_for_qid`.
- **Service idempotency** covers both spines: an existing work with the Q-id
  *and* an existing work with the seeded title both report `exists`.
- **Ožys**: prompt templates take `{title}`, `{summary}`, and
  `{difficulty_instruction}` (empty when untargeted); generation is a single
  user message (no source fetching -- the tale as a tradition is in-model
  knowledge). Canonical types raise `ValueError`; verified versions are
  refused by both the CLI and the Barsukas route, and regeneration
  overwrites only unverified slots. The CLI already accepts `--difficulty`,
  so difficulty-targeted tellings need only prompt-quality work, not
  plumbing. `--dry-run` prints without storing.
- **Licenses**: the Barsukas license select is a closed list
  (`CANONICAL_LICENSE_CHOICES`: public-domain, CC0, CC-BY, CC-BY-SA,
  developer-authored); the schema itself accepts any string, so widening is
  a UI-only change.
- **Migration**: idempotent create-if-missing for both tables. Note that
  `storage.backend.create_session` runs `Base.metadata.create_all`, so on a
  fresh local SQLite the tables appear on first use and the migration is a
  formality; it matters for production PostgreSQL
  (`PYTHONPATH=src python src/storage/migrations/add_text_works.py --postgres`).

### Verification

- The 12 unit tests cover the vocabulary partition, work CRUD guards (type
  validation, quote deferral, slug/Q-id uniqueness and normalization, type
  change pinned by a canonical version), all three version invariants,
  delete cascade, the query layer, and service idempotency (seed fetch
  monkeypatched -- no live Wikidata calls).
- The full storage and barsukas suites pass unchanged.
- The `/texts` flows were driven end-to-end with the Flask test client:
  creating both work kinds, license enforcement, single-canonical
  rejection, generate-refused-for-canonical, version editing and slot
  moves, list filters/search, work deletion, and the concept-page Texts
  box. A local-browser pass over `/texts` is still owed per the Barsukas
  convention.

### Seeding content (developer-run; LLM cost)

```
PYTHONPATH=src python src/agents/ozys/ozys.py \
    --slug The_Three_Billy_Goats_Gruff --model gpt-5.4-mini [--dry-run]
```

Works are created first in Barsukas (`/texts/new`, Q-id preferred) or via
`create_text_work_from_qid`; Ožys then fills the English reference telling
per work.
