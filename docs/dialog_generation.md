# Dialog generation

How dialogs are written, stored, and reviewed, and why the flow starts in
Barsukas rather than in an agent.

## The interaction

1. **Barsukas → Conversations → New Dialog.** The author types a scene in plain
   words ("buying tomatoes at the grocery store"), picks a difficulty level and
   a rough turn count, and submits an ordinary form.
2. **The worker writes it.** The form enqueues a
   `conversations.scene.generate` task; the worker calls the LLM and stores the
   result. Generation is a multi-second call and the reviewer's next step is
   reading a stored conversation, so nothing is gained by holding the request
   open.
3. **The conversation page reports coverage.** Every English token in the dialog
   is classified against the database, and the words we do not have are listed
   with a one-click action to stage them for import.

The author's job is the scene and the review. The generator's job is the
dialog. Nothing about the pipeline requires a CLI invocation.

## Why this replaced the keyword-driven path

`agents/sarka` still exists and still works, but it is shaped around a
different question. It picks ~5 lemmas at a level, plans 12 conversations per
level so each word gets used about twice, and asks for a dialog around that
word list. Consequences:

* **There is no scene.** The LLM invents the situation from the word list, so
  the dialogs are about whatever the vocabulary suggested. There was never a
  way to ask for one.
* **The level never reached the prompt.** It selected which words were sampled
  and nothing else; the model was not told what level it was writing for.
* **Difficulty was asserted, not derived.** Stored sentences got no
  `SentenceWord` rows, and `sentence.minimum_level = level` was set from the
  request. A dialog that used a level-12 word while being generated "for level
  3" was recorded as level 3.
* **Nothing reported what was missing.** A dialog using a word we do not have
  looked exactly like one that did not.

The scene path is the same storage with those four things fixed. Sarka's bulk
mode remains the right tool for "fill out level 4 across twelve dialogs"; the
scene path is the right tool for "I want this specific situation covered".

There is also `agents/ozys`, which generates *prose* conversations as
`TextWork`/`TextVersion` rows for the story library (see `fables_design.md`).
That path is deliberately separate: its output is a text to read, not a
sequence of sentence rows to translate, level, and export. A conversation
generated there stays there.

## What gets stored

A generated scene becomes ordinary conversation data, the same shape the
WireWord export consumes:

| Row | Content |
| --- | --- |
| `Conversation` | title, theme, `scene_prompt`, `target_level`, `source_model`, and the cast in `keywords` |
| `Sentence` + `SentenceTranslation` | one per turn, English text |
| `ConversationSentence` | position and speaker |
| `SentenceWord` | one per English token, linked to a lemma, a name, or nothing |
| `Name` | any proper name the dialog cast |

`Conversation.target_level` is what was asked for; `minimum_level` is what the
dialog turned out to be, computed from the lemmas actually used. The gap
between them is shown on the review page and is information rather than an
error.

The rollup is a **percentile, not a maximum** (`dialog_difficulty_level` in
`sentences/dialog_coverage.py`). Some words being harder than the target — or
missing from the dictionary entirely — is the expected shape of a natural
dialog, so one rare word must not define the whole thing. The rules:

* the level is the **85th percentile** of the distinct leveled lemmas used,
  nearest-rank, so the result is always a level some word really has;
* it is **floored at `target_level`** — a dialog written for level 5 is level-5
  material even when its words happen to be easy;
* the floor lifts only when *every* word used is below the target, in which case
  the dialog is described by its vocabulary rather than by the request;
* a word repeated across turns counts once, so repetition alone cannot raise it.

`Sentence.minimum_level` stays the **max** over its own lemmas. A single line is
too short for a percentile to mean anything there, and that value is a hard gate:
a learner sees the line only once every word in it is known.

## Vocabulary coverage

`sentences/dialog_coverage.py` classifies each token into one of five buckets:

* **known** — a lemma at or below the target level;
* **above level** — a lemma harder than the target level; enough of these raise
  the computed minimum level, a few do not;
* **name** — a registered `Name`, or one the generator reported in this scene's
  cast;
* **grammatical** — function words, numerals, and anything that is never a
  dictionary headword;
* **missing** — a real word we do not have yet.

Only the last bucket is offered for staging. Inflected forms resolve through
stored `DerivativeForm` rows, and fall back to undoing regular English
morphology (`langtools.en.utils.candidate_base_forms`) so "tomatoes" finds
"tomato" even for a lemma whose forms have not been generated. Function words
that happen not to be lemmas yet are reported as grammatical rather than
missing: that is a gap in the function-word data, not a word to import.

Coverage is recomputed on every page view rather than stored, so a dialog's
report improves on its own as the dictionary fills in.

The missing bucket is expected to be large at first. That is the point of the
flow: the dialogs say what the scene needs, and the words they reach for that
we lack are exactly the words worth adding next. Staging one creates a
`PendingImport` carrying the dialog line as context, and the existing
disambiguation and synonym-candidate review decides what becomes a lemma.

## Names

"George" in *George likes skiing* is a person, but not one the encyclopedia
would ever have an entry for. Names are therefore a third kind of entry beside
lemmas and concepts, with their own table (`storage/models/name_entity.py`):

* not a **lemma** — no difficulty level, no definition, not in `data/release`,
  and excluded from the `minimum_level` rollup, because a learner does not
  study "George" and a dialog full of names is not a harder dialog;
* not a **concept** — no Wikidata Q-id, no encyclopedia entry, and unlike
  concepts they live in the main writable database, because sentences reference
  them.

What they do carry is a per-language rendering: Lithuanian needs `Džordžas`,
Chinese needs `乔治`. That is why this is storage and not a prompt rule — the
rendering has to be the same in every sentence that casts the character, and
translation and audio both read it.

The generator reports its cast as structured data rather than leaving names to
be recovered by string-matching the dialog afterwards, and the cast is
registered with `get_or_create_name`, so a recurring character reuses one row
and one set of renderings. When the generator misses one, the review page has
an "It's a name" action that registers it and relinks the dialog's words.

Names are browsable and editable at `/names`.

## Where the code lives

| Path | Role |
| --- | --- |
| `src/sentences/dialog_scene.py` | request, prompt building, LLM call, reply parsing |
| `src/sentences/dialog_coverage.py` | token classification and the coverage report |
| `src/workqueue/handlers/conversations/scene.py` | generation → stored rows |
| `src/barsukas/routes/conversations.py` | the new-dialog form, staging, name registration |
| `src/barsukas/routes/names.py` | the names registry UI |
| `src/storage/models/name_entity.py` | `Name` / `NameTranslation` |
| `prompts/conversations/scene/` | context and prompt templates |

New databases pick up the schema through `create_all`; existing ones need
`PYTHONPATH=src python src/storage/migrations/add_names.py` (add `--postgres`
for production), which creates the name tables and adds
`sentence_words.name_id`.

## Known gaps

* **Translation is a separate step.** A generated dialog is English only; its
  sentences go through the ordinary translation pipeline afterwards, which does
  not yet consult `NameTranslation` when rendering a name into the target
  language. Until it does, renderings are curated but not consumed.
* **Conversation export is still disabled** in `exports/wireword` (it was turned
  off when there were no conversations to export). Turning it back on is a
  separate decision about what reaches Trakaido.
* **Irregular forms depend on stored derivative forms.** "came" resolves to
  "come" only when the `DerivativeForm` row exists; the de-inflection fallback
  covers regular morphology only, by design.
