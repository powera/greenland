# Conversations and narratives: design proposal

Status: draft for review, 2026-10-28. This document proposes future work; no schema,
content, generation, or client implementation is authorized by this draft.

## Purpose

Give learners something meaningful to understand and communicate: a situation with
people trying to achieve something, or a connected account with events and ideas.
Content should remain interesting when individual words are already familiar.
Vocabulary coverage is a constraint and diagnostic, not the reason characters speak.

These are independent content features. They do not require completion of the B1/B2
word-list review, audio audit, or Barsukas activity back-port. Those projects may
inform implementation choices later.

## Existing foundation and verified gaps

The current implementation already goes beyond isolated sentences:

- `src/sentences/dialog_scene.py` accepts a scene, target level, turn count and
  notes, and returns a cast and turns, each containing multiple sentences.
- `src/storage/models/schema.py` has `Conversation` and `ConversationSentence`.
  The latter stores both sentence position and `turn_index`; do not infer turns
  by merging consecutive sentences from the same speaker. Legacy NULL turn indices
  fall back to sentence position.
- `src/workqueue/handlers/conversations/scene.py` stores generated scenes;
  `src/sentences/dialog_coverage.py` supports vocabulary coverage inspection.
- `src/barsukas/routes/conversations.py` and its templates support scene creation,
  inspection, missing-word staging, name handling, verification and rejection.
- `src/storage/crud/conversation.py`, `src/sentences/translation.py` and
  `src/sentences/translate_and_decompose.py` now supply dialog context and cast to
  sentence translation. The cast formatter supplies names/traits/notes, but does
  not explicitly include curated `NameTranslation` renderings. Context is budgeted,
  with a preceding-turn fallback for long dialogs.
- `src/exports/wireword/export_wireword_conversations.py` writes ordered sentences,
  speaker labels, translations, linked lemma GUIDs/forms and sentence audio. It
  exports non-rejected conversations with *at least one* target translation; it
  does not require verification or complete translation and omits `turn_index`.
- `src/exports/wireword/service.py` disables normal conversation export in two
  service paths. `generate_manifest.py` can nevertheless discover an existing
  conversation file as an optional auxiliary artifact. Stale files need explicit
  consideration before enabling publishing.
- No conversation/narrative consumer was found in a text search of Swift/React
  application source or the inspected Kotlin sources. Treat the client experience
  as new work, rather than assuming the existing exporter has a working consumer.
- `src/verbalator/actions/narrative_structure.py` analyzes arbitrary text; this is
  not a learner narrative content model, reviewed corpus, or release pipeline.

`docs/dialog_generation.md` explains the scene workflow, but its known-gap account
of translation predates the current dialog-context implementation. Verify code
when planning changes.

## Proposed content model

Use a shared learning-text concept with explicit `conversation` and `narrative`
kinds. The final physical table arrangement needs review; do not overload
`Conversation` with silent narrators merely to avoid designing narratives.

Each piece has a stable public GUID, revision, title, kind, situation/topic,
communicative objective, source language, target curriculum level, optional
editor-reviewed CEFR band, register, provenance, and review state. Level numbers
remain curriculum identifiers; a numeric maximum is not a CEFR assessment.

Conversation metadata includes participant IDs, localized display names,
relationships and per-scene roles/goals, opening situation, complication and
intended outcome. A participant need not have a proper name. Keep scene roles
local: a recurring name's global notes cannot reliably describe its job or
relationship in this scene. Reuse the existing names registry for actual names.

Narratives include narrator/viewpoint, setting, and an outline of connected events
or ideas. A narrative may contain quoted dialog, so distinguish a spoken speaker
from the narrator. Prefer concrete short accounts first: a misunderstanding,
a changed plan, a discovery, or an explanation with a conclusion.

Represent structure at three levels:

1. Piece: the complete communication.
2. Segment: a conversational turn or narrative paragraph, with stable ID and order.
3. Sentence units: existing sentence records, lexical links and translations,
   ordered inside the segment.

Preserve existing turn boundaries during import. Sentence boundaries may differ
between languages: allow a localized segment to realize several source sentences
together, with optional alignment, rather than making one-to-one sentence mapping
a permanent language constraint. Existing sentence-aligned content remains valid.

Shared sentence reuse needs care: identical text can have different intent,
referents, register and pronunciation in different contexts. Do not automatically
merge contextual translations or audio solely because source text matches.

Separate immutable reviewed revisions from editable drafts. Associate locale review,
questions and audio with the exact text revision they were approved against.

## Authoring and review

Extend the existing Barsukas scene-first workflow, and add manual authoring/import
alongside optional queued generation. A brief states audience, situation, objective,
length, register, encouraged vocabulary and permitted new vocabulary. For narratives,
include the event/idea outline; for conversations, participant goals and outcome.

Suggested workflow:

1. Draft and inspect the whole piece in order.
2. Review coherence, naturalness, plausibility, intended meaning and difficulty.
3. Inspect lexical coverage: known lemmas/forms, proper names, unresolved words and
   above-target words. Missing words may be staged for a separate reviewed task;
   this workflow must not automatically add lemmas or reassign curriculum levels.
4. Translate with full piece context where practical, scene roles, name renderings,
   continuity notes and a maintained glossary. Show any truncated context. Review
   each locale for intent, reference, politeness and consistency across segments.
5. Author and review meaning-based tasks with evidence pointing into the piece.
6. Generate/review audio through the separately approved audio pipeline.
7. Preview exactly the learner payload and explicitly approve a locale for release.

Track source review, locale text review, activity review and audio review separately.
One `verified` flag cannot establish that every language and recording is ready.
Edits invalidate affected approvals, questions and recordings, and show the reason.
Use ordinary form POSTs and persistent status/results, following Barsukas conventions.

## Learning experience

Start with linear authored content and deterministic tasks. Open-ended live chat,
branching dialog trees, speech scoring and automatic semantic grading are later
design decisions, not prerequisites.

A first session should offer a brief situation, an uninterrupted read/listen,
meaning questions, then optional targeted replay and vocabulary exploration.
Translations are available on request; listening tasks can initially hide transcript
and reveal it explicitly. Do not make hiding text a permanent accessibility barrier.

Conversation tasks: identify each participant's goal, infer a polite refusal,
choose an appropriate response, identify what was agreed, or take one role and
respond before revealing the authored continuation. Where several responses are
plausible, do not mark a single canned response as uniquely correct.

Narrative tasks: identify the main point, order events, explain a cause, distinguish
what a character knew, or choose a supported inference. A retelling prompt can have
a model answer and self-check points without pretending to grade arbitrary speech.

Questions store stable IDs, localized prompt/choices, answer/rubric, explanation,
and evidence segment IDs. Distractors must be contradicted or unsupported by the
piece, not grammatical traps. Avoid questions answerable from one matching word
or from world knowledge without understanding the text. Review question translations
for answer leakage.

Record piece completion and comprehension separately from word recall. Replaying a
passage or viewing a translation is useful engagement, not automatically a wrong
answer. Rotate alternate reviewed pieces/variants; shuffling a few questions alone
does not prevent memorization. Alternate endings must remain separate coherent
revisions/variants with their own questions.

## Audio design requirements

The independent audio audit should evaluate these requirements; this draft does
not prescribe a generation vendor or authorize any recording calls.

- Default playback unit: a complete conversational turn or narrative paragraph.
  Sentence recordings remain useful for focused replay, but concatenating them
  cannot be assumed to sound like natural connected speech.
- Whole-piece playback may sequence segment recordings with explicit pauses.
  An optional rendered full-piece track must carry segment timing for navigation.
  Do not require full-piece and sentence and segment recordings for every item
  until their benefit and production cost have been reviewed.
- Keep a stable voice per participant within a locale/revision; narrator and quoted
  speech have explicit policy. Voice identity belongs to a rendering, not permanently
  to a person/name. Roles should remain distinguishable without stereo positioning.
- Store language variety, voice, spoken-text revision/hash, unit/context identity,
  duration, review status and asset reference. Existing text-matched audio lookup
  does not by itself guarantee scene-specific voice or prosody.
- Support play/pause, segment replay, previous/next segment, visible playback focus,
  speed control where supported, and offline/cache completeness reporting.
- Model text readiness and listening readiness separately. Text-only reading may
  be released if approved; a listening activity must not silently skip an unheard
  turn or substitute device speech without a deliberate product policy.
- Respect storage versus presentation dialect resolution using existing language
  helpers; do not invent language fallback mappings for this feature.

## Release contract proposal

Introduce an explicitly versioned optional learning-text artifact in the WireWord
manifest. Do not quietly change the old conversation format and assume clients
will understand it. Final naming, version and platform rollout need approval.

A record contains `schema_version`, stable piece GUID, revision, kind, source/target
language, localized metadata, objectives, level/coverage metadata, participant
records, ordered segments, contextual localized text, aligned sentence IDs where
available, linked lemma GUIDs/forms, reviewed activities, and audio renderings.
Stable segment IDs and explicit turn/paragraph boundaries are required. Existing
numeric database IDs may remain diagnostic metadata, not the only public identity.

An activity declares required capabilities and required audio units. Manifest entries
carry schema version, content hash, language, counts and capability information.
Clients skip unsupported optional artifacts gracefully. Enable only platforms that
have implemented and validated the contract; Kotlin parity is not a reason to run
an unauthorized build or block a separately approved Swift rollout.

Export only explicitly approved, complete locale revisions. Every segment required
by a piece must have reviewed localized text; every listening task must have its
required reviewed production audio. Reject unresolved references and stale assets.
Report exclusions with reasons. Do not export a half-translated piece simply
because one sentence has a target-language translation.

## Migration and staged delivery after approval

1. Agree on first learner experience, audio units and the contract; create small
   hand-reviewed fixtures representing a multi-sentence turn, recurring name,
   narrative paragraph, missing translation and missing audio.
2. Add stable identity/revision and locale review support without destructive
   replacement. Wrap existing conversations as conversation pieces and preserve
   sentence IDs, speaker labels and turn indices. Unknown roles, quality and
   readiness remain unknown; legacy `verified` does not imply new locale approval.
3. Add narrative authoring and Barsukas whole-piece/locale/activity/audio previews.
   Implement context-aware translation and invalidation where existing paths fall
   short; do not regenerate existing translations automatically.
4. Implement the versioned exporter and one agreed client consumer together. Keep
   old exports available during an explicit compatibility period. Prevent stale
   optional artifacts from being accidentally re-advertised by manifest generation.
5. Run a reviewed pilot with both content kinds before broad generation or publishing.

Any migration should be dated, rerunnable, use `DataSourceConfig`, and follow the
repository's backup rules. An additive migration normally uses a minor backup;
an irreversible rebuild/drop requires a major backup. No migration is run by this
design task.

## Acceptance criteria

- A conversation has distinct participant goals, responsive turns and a meaningful
  outcome; a narrative has connected events/ideas and a recoverable main point.
- Reviewers can inspect source, locale, coverage, names, questions and audio together,
  and see exact release blockers without automatically adding vocabulary.
- Multi-sentence turns and narrative paragraphs survive storage/export/client loading
  in order, with stable IDs and no speaker-based accidental merging.
- A learner can complete read/listen, comprehension and focused replay flows without
  a live model call. Translation reveal and accessibility remain available.
- At least one question requires understanding intent, cause, sequence or inference;
  every graded answer is supported by reviewed evidence.
- Missing/stale text, question references or required listening audio block that
  release capability and yield a clear diagnostic. Text-only availability is explicit.
- Editing a source or locale creates a revision/invalidation trail; stale reviewed
  audio cannot attach merely because another text row matches.
- Contract fixtures validate exporter and consumer behavior, including unknown optional
  schema versions, legacy turns and unsupported capabilities. Storage CRUD changes
  receive tests; Barsukas-specific tests follow repository policy.

## Decisions requested in review

1. Approve shared piece/segment concepts with explicit conversation/narrative kinds;
   choose the physical schema during implementation design.
2. Choose the first client/platform and whether reading and listening both ship in
   the first pilot. Recommendation: one client, both kinds, linear authored content.
3. Approve segment audio as the baseline, with sentence/whole-piece audio optional
   when justified by activity needs and the audio audit.
4. Choose whether localized segments may diverge from source sentence boundaries.
   Recommendation: yes, with optional sentence alignment and preserved meaning.
5. Choose initial content audience, length and number of pieces per kind. These are
   editorial/product choices; no corpus size or new B1/B2 vocabulary is assumed here.
6. Approve separate locale/text/activity/audio readiness and explicit release approval
   before enabling normal conversation/narrative exports.
