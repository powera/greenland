# Parallel element types and idioms — design

## Status and goal

Implementation status: Phase 0 characterization is complete. The shared structural
interfaces and idiom SQLAlchemy/CRUD layer are now implemented; Barsukas and
idiom export support remain intentionally deferred.

Greenland models several kinds of linguistic **elements**: lemmas, concepts,
phrases, sentences, names, and conversations. Idiom will become another kind.
The types have deliberately different SQLAlchemy models and domain rules, but
some consumers—especially Barsukas—need to work with useful groups of them.

The design therefore uses **small, composable interfaces**. It does not add an
adapter for every model, a central element registry, or a universal SQL table.
SQLAlchemy already removes much of the storage boilerplate, and the remaining
model-specific querying is usually clearer than a framework that hides it.

The target sequence is:

1. define the interfaces and their semantics;
2. make existing models implement only the interfaces that honestly fit;
3. let Barsukas and other consumers share code against those interfaces;
4. add idiom through the same interfaces, with idiom-specific equivalents;
5. add idiom generation only after mechanical persistence and review work.

## Domain boundaries that remain

| Type | Identity | Language-bearing data | Important unique behavior |
| --- | --- | --- | --- |
| Lemma | GUID + lexeme/sense | headword translations and forms | exactly one lexeme; POS, morphology, frequency, difficulty |
| Concept | slug and optional Q-id | encyclopedia body | separate concepts backend, sources, wiki links |
| Phrase | GUID + curated label | one fixed expression per language | fixed multiword expression, learner level and subtype |
| Sentence | GUID | one sentence per language | token links, grammar, computed level |
| Name | normalized text + kind | stable rendering per language | may contain one or several words; no GUID or difficulty |
| Conversation | database id | ordered sentence references | speakers, scene, aggregate level |
| Idiom | GUID + source-language expression/sense | zero or more equivalents per language | meaning is shared; equivalents are not direct translations |

Parallel treatment must not:

- put all types into a sparse “everything” table;
- make every model inherit a giant base with irrelevant nullable columns;
- call every language-bearing value a translation when it may be a rendering,
  version, or idiomatic equivalent;
- force concepts into the writable linguistic database;
- give names learner difficulty or conversations standalone translations;
- move domain algorithms such as inflection or token analysis into shared code.

## Shared interfaces

### Why interfaces rather than adapters

Most common behavior is a read-only view of an object already loaded through
SQLAlchemy: display its text, link to it, show whether it is verified, or render
language values. A structural Python `Protocol` describes that view directly.
The model can implement it with existing attributes or a small property.

This keeps the query where it belongs. A lemma list still performs a lemma
query, concept search still uses the concepts backend, and sentence pages still
load sentence relationships. Once loaded, those objects can be passed to shared
Barsukas presenters typed against an interface.

Use abstract base classes only when an implementation is genuinely shared (for
example, timestamp column declarations). Do not add an ORM inheritance hierarchy
merely to satisfy these interfaces.

### Base `Element`

Add a dependency-light module such as `storage/elements/interfaces.py`:

```python
from typing import Protocol

class Element(Protocol):
    @property
    def element_type(self) -> str: ...

    @property
    def display_text(self) -> str: ...
```

`Element` is intentionally tiny. It answers only “what kind of thing is this?”
and “what should a human call it?”. Database identity is not included because
an integer id is meaningful only together with its model/backend. Callers that
need a durable reference use:

```python
@dataclass(frozen=True)
class ElementRef:
    element_type: str
    element_id: int
```

`ElementRef` can gradually replace ambiguous `(target_type, target_id)` pairs in
new task/logging code without rewriting existing persisted values.

### Orthogonal super-categories

Super-categories are interfaces, not positions in one class hierarchy. A model
may implement several independently:

```python
class WordElement(Element, Protocol):
    """Exactly one lexical word/headword, not merely text containing one token."""

    @property
    def word_text(self) -> str: ...


class MultiwordElement(Element, Protocol):
    """A meaningful expression containing more than one lexical word."""

    @property
    def expression_text(self) -> str: ...


class GuidElement(Element, Protocol):
    guid: str | None


class VerifiableElement(Element, Protocol):
    verified: bool


class LeveledElement(Element, Protocol):
    @property
    def level(self) -> int | None: ...


class LanguageValueElement(Element, Protocol):
    @property
    def language_values(self) -> Sequence[LanguageValue]: ...


class CompositeElement(Element, Protocol):
    @property
    def children(self) -> Sequence[ElementRef]: ...
```

These names state semantic promises, not incidental database shape:

- `Lemma` is a `WordElement`, even when its human-facing label includes a
  disambiguation such as `light (color)`. `word_text` remains `light`.
- `Name` is an `Element`, but not necessarily a `WordElement`: “George” is one
  word while “Fresh Mart” is not. If single-word names later need common
  behavior, expose an explicit predicate/projection rather than lying in the
  model's static interface.
- `Phrase` and `Idiom` are `MultiwordElement`s. A one-word idiom can be allowed
  as a domain exception without redefining it as a dictionary headword.
- `Sentence` is textual, but not a `MultiwordElement`: the latter promises a
  reusable expression, not any string with spaces.
- `Conversation` is a `CompositeElement` of sentence references.
- `Concept` may only need `Element` and `VerifiableElement`; that is useful and
  is not a failure of abstraction.

More interfaces can be added when two real consumers need them. Avoid speculative
categories and boolean capability bags. Static typing then prevents a function
that needs a GUID or word from accepting a concept or conversation accidentally.

### Language values are another interface family

“Has language values” does not imply “has one direct translation per language”.
Use a common read projection:

```python
@dataclass(frozen=True)
class LanguageValue:
    id: int
    language_code: str
    text: str
    value_kind: str
    verified: bool
    status: str | None = None
    status_note: str | None = None
```

Existing models project their rows as follows:

- lemma → `value_kind="headword"`;
- phrase → `value_kind="translation"`;
- sentence → `value_kind="version"`;
- name → `value_kind="rendering"`;
- idiom → `value_kind` equal to `idiomatic`, `near_equivalent`, or `paraphrase`.

The projection permits zero-to-many values per language. Phrase, sentence, and
name persistence may continue enforcing one row per language, while idioms do
not. All supported-language validation must continue to come from
`storage.translation_helpers`.

Writes should use narrower interfaces because their rules differ:

```python
class SingleLanguageValueEditor(Protocol):
    def set_language_value(self, input_value: LanguageValueInput) -> LanguageValue: ...
    def clear_language_value(self, language_code: str) -> None: ...


class MultipleLanguageValueEditor(Protocol):
    def add_language_value(self, input_value: LanguageValueInput) -> LanguageValue: ...
    def update_language_value(
        self, value_id: int, input_value: LanguageValueInput
    ) -> LanguageValue: ...
    def delete_language_value(self, value_id: int) -> None: ...
```

These can be small service objects around a session rather than methods on ORM
rows. They do not commit; the route or agent owns its transaction. There is no
requirement for lemma and concept CRUD to share code merely because both are
`Element`s.

## How Barsukas uses the interfaces

Barsukas keeps explicit blueprints and model-specific queries. Shared presenter
and form helpers accept the narrowest useful interface:

- a result-card presenter accepts `Element`;
- a vocabulary badge accepts `WordElement`;
- a GUID link/copy component accepts `GuidElement`;
- verification controls accept `VerifiableElement`;
- a level badge accepts `LeveledElement`;
- the language coverage table accepts `LanguageValueElement`;
- a child list accepts `CompositeElement`.

For example, a lemma route can expose its loaded model as a `WordElement`, and
Barsukas may use word-only components without adding `if element_type ==
"lemma"`. A unified search result can be merely `Element`; it does not acquire
word controls until it is narrowed to `WordElement`.

Jinja should receive explicit view models produced from interfaces rather than
performing protocol detection itself. This keeps templates simple and gives
mypy a chance to check the presenter code:

```python
@dataclass(frozen=True)
class ElementCard:
    element_type: str
    display_text: str
    detail_url: str


def build_word_card(word: WordElement, detail_url: str) -> ElementCard: ...
```

Shared templates should be partials for genuinely shared interactions, such as
language values or verification metadata. Each element type retains its list and
detail shell plus unique sections. Do not introduce a dynamic `/<type>/<id>`
catch-all route. All edits remain ordinary POST form submissions.

Route URLs do not belong on storage models. A Barsukas resolver maps an
`ElementRef` or concrete type to its explicit blueprint URL. That small web-only
mapping is preferable to a global domain registry.

## Refactoring sequence

Each phase should preserve public behavior and be independently reversible.

### Phase 0 — characterize current behavior

Add tests for phrase, sentence, name, and lemma display and language values:

- missing-id and list/get behavior;
- existing one-value-per-language constraints;
- upsert and blank-input deletion semantics;
- verification/status preservation;
- no implicit commit by storage helpers;
- read-only Barsukas POST behavior;
- JSONL and release round trips where supported.

Capture route names and export shapes as compatibility fixtures.

### Phase 1 — interfaces and projections

Introduce `Element`, `ElementRef`, the first proven super-category protocols,
and `LanguageValue`. Add the smallest properties needed by existing models.
Start in this order:

1. lemma + phrase, proving `WordElement` versus `MultiwordElement`;
2. name, proving that not every short label is a word;
3. sentence, proving language versions plus special domain behavior;
4. conversation, proving composition without direct translations;
5. concept, proving that the base interface works across backends.

Add compile-time assignment tests and ordinary tests for property semantics.
There is no registration requirement and no generic writer in this phase.

### Phase 2 — Barsukas presenters

Extract read-only cards, verification metadata, GUID/level displays, and language
coverage presenters against their narrow protocols. Migrate phrase and name
pages first, then matching portions of lemma and sentence pages. Do not force
concept or conversation pages through components that do not fit them.

Ask the developer to browser-test every affected Barsukas page before deleting
old template code.

### Phase 3 — language-value form composition

Extract the common rendering/form mechanics while retaining separate storage
services for single-value and multiple-value models. Return typed changes so a
shared operation-log helper can record old/new values without embedding logging
inside form loops.

Keep compatibility functions such as `set_phrase_translation` until all callers
migrate. Type-specific tests remain authoritative for differing cardinality,
pronunciation, status, and domain rules.

### Phase 4 — backend and export cleanup only where useful

Do not create a universal backend manifest solely for symmetry. JSONL and export
code should use an element interface only where it removes a real branch or
supports a real cross-type consumer. Existing serialized keys and release output
must remain unchanged during the refactor.

A type that is not exported needs no fake exporter. Concepts and names can still
participate in Barsukas `Element` views without participating in WireWord.

## Idiom stage

### Semantics and interfaces

An idiom is anchored in a **source language and expression**, with a shared
meaning/sense. Other languages contain **equivalents**, not translations. A
language may have no equivalent, one equivalent, or several equivalents with
different register or region notes. A literal gloss is explanatory and must
never be substituted for an equivalent.

`Idiom` implements `Element`, `MultiwordElement`, `GuidElement`,
`VerifiableElement`, `LeveledElement`, and `LanguageValueElement`. It does not
implement `WordElement`. Its editing service implements
`MultipleLanguageValueEditor`.

Example distinctions:

- source expression: “kick the bucket” (`en`);
- meaning: “to die”;
- literal Lithuanian gloss: optional explanation of the English words;
- Lithuanian equivalent(s): natural Lithuanian idioms, possibly zero or many;
- fallback: a non-idiomatic paraphrase explicitly marked as such.

### Schema

Add dedicated tables rather than making idiom a phrase subtype:

```text
idioms
  id, guid, source_language_code, expression, meaning,
  usage_note, register, region, difficulty_level,
  source_model, confidence, verified, notes, timestamps

idiom_equivalents
  id, idiom_id, language_code, expression, equivalence_kind,
  literal_gloss, usage_note, register, region,
  source_model, confidence, verified, timestamps
```

Constraints and indexes:

- unique `(source_language_code, expression, meaning)` on idioms, unless real
  data demonstrates a need for a normalized-expression companion column;
- unique `(idiom_id, language_code, expression)` on equivalents;
- `equivalence_kind` is closed: `idiomatic`, `near_equivalent`, `paraphrase`;
- source expression lives on the idiom, not as a magic English equivalent;
- zero equivalents is a valid, visible coverage state;
- use the dedicated immutable `M01` GUID family, which is routed as `idiom` by
  the storage GUID resolver.

A separate equivalents table is necessary because the generic language-value
interface permits multiple values while current phrase/name/sentence tables do
not. The interface unifies consumption without weakening storage constraints.

### Barsukas behavior

Barsukas gets explicit `/idioms` routes and idiom-specific shell templates. It
reuses element, GUID, verification, level, and language-value presenters. The
detail page must:

- keep source expression and meaning visually separate;
- group equivalents by language;
- show equivalence kind and notes persistently;
- explicitly show “no idiomatic equivalent recorded”;
- allow several equivalents through ordinary POST forms;
- never offer “copy English into missing languages”.

### Generation pipeline

Generation is deliberately later:

1. create and review idioms/equivalents manually;
2. prove persistence, Barsukas, JSONL, and export with
   `GREENLAND_DISABLE_LLM=1`;
3. define structured output separating equivalent, paraphrase, literal gloss,
   register, and “none exists”;
4. include the source expression, shared meaning, and usage context in prompts;
5. persist candidates unverified through the ordinary editing service;
6. record model/confidence per equivalent;
7. export only after human review.

Never chain language-to-language generated output. Generate every target from
the source expression **and shared meaning**, so an error in one language cannot
contaminate another.

### Export shape

Do not squeeze idioms into lemma WireWord records:

```json
{
  "guid": "M01_001",
  "source": {"language": "en", "expression": "kick the bucket"},
  "meaning": "to die",
  "equivalents": {
    "lt": [
      {
        "expression": "…",
        "kind": "idiomatic",
        "literalGloss": "…",
        "usageNote": null
      }
    ]
  }
}
```

Arrays are required even when there is one equivalent. Missing language keys
mean “not assessed”; assessed-with-no-equivalent must be represented explicitly
so consumers distinguish linguistic absence from unfinished work. Coordinate
final field names and GUID prefixes with Trakaido before freezing the contract.

## Acceptance criteria

The parallelization is sufficient for idioms when:

- existing models implement only truthful, small interfaces;
- `WordElement` consumers accept lemmas without accepting phrases, sentences,
  multiword names, concepts, or conversations;
- Barsukas shared code is typed to the narrowest super-category it needs;
- no central registry or capability bag is required to render an element;
- existing database contents, URLs, JSONL, and exports remain unchanged;
- shared language-value reads allow zero-to-many rows per language;
- single-value writers retain their current database constraints;
- idiom-specific meaning/equivalence rules remain in idiom code.

## Decisions intentionally deferred

- Representation of “assessed, no equivalent”: dedicated coverage row versus a
  coverage/status table.
- Literal-gloss language coverage.
- Automatic idiom generation prompts and model choice.
- Component-lemma links for idiom search/difficulty; a later junction table can
  provide these without blocking idiom CRUD.
