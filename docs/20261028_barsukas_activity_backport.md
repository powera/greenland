# Barsukas activity back-port — October 28, 2026

## Scope and safety

Task 2 is the implementation task. Changes are confined to Barsukas code,
templates and this progress document. No production database writes, content
generation, remote APIs, release edits, commits or sibling-repository edits.
Other planning tasks are independent.

## Source inventory

Inspected the sibling Trakaido repository's React activities and utilities,
Swift activity views, and shared activity documentation. Relevant sources:

- `react/Activities/`: vocabulary list, flashcards, multiple choice, typing,
  spelling, listening, sentence completion, category choice, conjugation review,
  declension, grammar questions, numbers, emoji choice, blitz and breaks.
- `react/Utilities/numberCatalog.ts`, `numberActivityGenerator.ts`,
  `pronounQuiz.ts`, `declensionQuiz.ts`, `grammarPhraseQuiz.ts` and the
  language-specific sentence quiz utilities.
- `SwiftApp/Trakaido/Views/Activities/`: corresponding activities plus
  pronoun runner, grammar phrase runner, emoji count, listen-and-repeat,
  pattern sentences, Block World and keyboard training.
- `docs/journey/activity-types.md` and Greenland's
  `docs/grammar_activities.md`.

The existing Barsukas previews covered spelling, category choice, sentence
completion, multiple choice, listening, flashcards, typing, two principal verb
forms and rule-built sentence patterns. These were not full client parity:
for example listening/typing adaptations, audio auto-play, client-authored
pronouns and grammar reference tables differed.

## Implemented

The activities index links to ten new content inspection/practice pages under
`/trakaido/activities/inspect/<kind>`. Pages share level/language preferences,
use ordinary form submits, and retain answers and content inspection links.
Only the current question is stored in Flask's session cookie. No practice
results or linguistic data are persisted.

| Preview | Implemented behavior | Deliberate limits / follow-up |
| --- | --- | --- |
| Declension | Explicit case/number forms, grouped identical surfaces, every matching case accepted, explicit number-type restrictions | No invented nominative from a base translation; cases without explicit forms are excluded |
| Conjugation | Type an explicitly stored verb form; slot displayed; exact-form reviewed audio where available | No synthesized periphrastic constructions, person tables or client-specific multi-step table UI |
| Pronouns | Type translations of stored pronoun lemmas | Not parity with five client pronoun categories or client-authored Lithuanian/Spanish supplemental case/possessive paradigms |
| Numbers | Shared stable GUID catalog for 0–20, tens, 100/1000, first–tenth | Production vocabulary/level eligibility governs availability; no invented intermediate number words |
| Number arithmetic | Sums/differences with operands and results in the cardinal catalog; answer in target words | No intermediate result without a catalog entry; typing rather than client multiple-choice rotation |
| Emoji choice | Stored concept emoji with distinct translation distractors | Does not claim every stored emoji is unambiguous; content is inspectable |
| Emoji count | Count repeated stored pictures and type a catalog number word (1–10) | This is visual counting only, not a numeral+noun agreement construction |
| Listen and repeat | Reviewed base recording, visible target, replay and explicit self-assessment instructions | No microphone capture or speech recognition; native speech grading remains platform-specific |
| Vocabulary list | Sampled translations, reviewed base audio and links to lemma records | Bounded sample, not an exported release completeness report |
| Grammar phrases | Existing language rule renderers, accepted alternates, missing-fact reasons, links to constituent source data | English prompts; Greenland renderer coverage differs from client-authored catalogs; no assertion of exact client parity |

The existing listening selector now requires approved/approved-with-issues
base recordings and excludes derivative-form recordings. Previously a lemma's
inflected-form recording or a recording awaiting review/replacement could be
chosen as the lemma prompt.

## Remaining parity work

This is a concrete first back-port, not completion of every client feature.

1. Port the authored pronoun supplements and category catalogs with their
   context/gender/case distinctions, avoiding duplicate language mappings.
2. Compare each client grammar phrase family against Greenland's existing
   rule renderer; port missing families and reference-table inspection while
   preserving explicit fact eligibility. Reusing the renderer prevents a
   second set of grammar rules but does not establish family-by-family parity.
3. Port Block World prompt/scene evaluation to an inspectable web preview;
   its authored spatial catalog and scene interaction need separate handling.
4. Bring existing preview behavior up to client parity: recorded audio for
   flashcards/multiple choice/typing, sentence listening, conjugation reference
   tables, number question direction/multiple-choice variants and contextual
   pronoun questions. The older previews largely remain as they were.
5. Consider blitz as a timing wrapper after content correctness. Breaks,
   adaptive scheduling/statistics, native keyboard training, haptics and native
   speech recognition are not linguistic content previews.

For each completed preview, missing audio is shown rather than manufactured.
An audio record with an approved status does not prove its local file exists
or that a release references it; Task 1 audits the broader production path.

## Verification

All Python validation used `GREENLAND_TEST_MODE=1 PYTHONPATH=src`.

- Black: modified Python formatted.
- Mypy on modified files: normal invocation encountered six existing errors
  in imported `src/words/mechanical_batch.py`, with none in changed files.
- `./run_tests.sh affected`: the affected map chose the entire suite because
  its base comparison included 1,070 files, including unmapped directories.
  Result: **4,116 passed, 7 skipped**, plus the separate **15-test smoke pass**.
- Temporary, uncommitted seeded SQLite verification exercised all ten new
  GET pages, the activity index and unknown-kind 404. It also exercised
  conjugation answer submission and both accepted cases for a syncretic noun
  form. No repository tests were added, following Barsukas instructions.

Browser visual review and playback against actual local audio still need the
developer's local browser check, as required by `src/barsukas/AGENTS.md`.

### Final implementation refinements and checks

- Pronoun practice also exposes explicitly stored pronoun case/form slots;
  alternative forms in a slot are accepted together, as in conjugation.
- Existing vocabulary previews now offer a shared, expandable candidate-pool
  table with lemma links, approved recordings and explicit missing-audio labels.
- Emoji distractors exclude concepts sharing the displayed emoji.
- Typed answers normalize Unicode, case, whitespace, curly apostrophes and
  terminal sentence punctuation while preserving accents.
- Changed-file mypy with `--follow-imports=silent`: **passes, 3 files**. The
  normal invocation's six failures are confined to the existing imported
  `words/mechanical_batch.py`.
- Explicit final `./run_tests.sh all`: **4,116 passed, 7 skipped**, 56.95s.
- Repeated temporary seeded route/form verification after refinements: passes.
- `git diff --check`: passes. No commit created.

The Block World source inspection additionally confirms that shapes, colors
and sizes have shared concept GUIDs and that eligible emoji objects are drawn
from the wordlist through a countable-object group whitelist. A future port
should reuse that catalog and its language packs rather than reducing spatial
instructions to arbitrary translated strings.
