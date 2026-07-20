# Trakaido iOS Activity Features Missing from the Barsukas Activities

This document compares the Trakaido iOS/macOS app (trakaido repo,
`SwiftApp/`) against the Barsukas implementation of the Trakaido activities
(`src/barsukas/routes/trakaido_activities.py` and
`templates/trakaido/activities/`), as planning input for improving the
Barsukas version. It covers activity behavior only — stat-tracking, sync,
and onboarding are out of scope.

## What Barsukas Has Today

Eight server-rendered activities: multiple choice, typing, flashcards,
listening, spelling quiz, sentence completion, category choice, and verb
forms. Each page serves a round of 10 questions built from the linguistics
database, with a dot-row progress bar, a sessionStorage practice-session
line, and a manual "Next" button. Word selection uses the level dropdown as
a ceiling, with exponentially decaying weight for lower levels. Level and
target language persist in cookies.

## iOS Activities With No Barsukas Equivalent

- **Journey mode** — the iOS app's primary mode. Rather than fixed rounds
  drawn at a chosen level, it maintains a per-word mastery tier (4 tiers,
  score-based), picks words via weighted selection favoring mistakes and
  stale words, chooses the activity type per tier (new words get
  flashcards, mastered words get harder production activities), introduces
  new words explicitly, and mixes in interstitials (motivational breaks,
  grammar lessons, level-readiness checks). Barsukas has no per-word
  progression at all — every round is a fresh random sample.
- **Listen and Repeat** — hear a word/sentence, say it aloud, graded by
  on-device speech recognition with lenient Levenshtein scoring
  (Lithuanian uses the Polish recognizer plus a phonetic mapping). A web
  version would need the browser speech APIs; nothing exists in Barsukas.
- **Sentence Spelling Quiz** — the spelling quiz (confusion-set blank
  fill-in) applied to a word inside a full sentence. Barsukas has the
  word-level spelling quiz only.
- **Multi-Word Sequence** — hear 2–4 words in sequence and pick them in
  order; tests short-term retention rather than single-word recognition.
- **Blitz mode** — timed, speed-scored rapid-fire questions.
- **Drill mode** — user picks a specific word set and cycles through
  mixed activity types against just those words.
- **Full conjugation tables** — the iOS conjugation activity presents a
  whole table (all persons, multiple tenses) to fill in, plus declension
  practice for nouns. The Barsukas "verb forms" activity is a 4-option
  multiple choice covering only 3s-present and 3s-past grammar facts.
- **Keyboard training** — iPhone-specific practice for typing
  target-language characters on the mobile keyboard; not meaningful for a
  desktop web tool, listed for completeness.

## Behavioral Gaps in the Shared Activities

### Auto-advance

iOS advances to the next question automatically after every answer; the
delay is derived from the answer audio's duration (so pronunciation plays
out fully), capped at 10 seconds, with a failsafe Continue button. In
Barsukas every activity requires clicking "Next" after each question
(flashcards excepted — they advance on self-grade). Note the Barsukas house
style avoids disappearing UX elements, so an auto-advance would likely want
to be an explicit per-page toggle rather than the iOS always-on behavior.

### Disambiguators on answer buttons

iOS strips trailing parenthetical disambiguators before display — a
"mouse (computer)" gloss renders as "mouse" on multiple-choice buttons.
Barsukas renders glosses exactly as stored in `lemma_text`, so
disambiguators appear on prompts and answer buttons. Stripping them is
cleaner but requires the option set to stay unambiguous without the
parenthetical (the iOS distractor generator filters on the stripped form).

### Audio coverage

Barsukas uses audio only in the Listening activity (auto-play on render,
manual replay). On iOS nearly every activity is voiced: multiple-choice
prompts auto-play in target→English mode, the correct answer's audio plays
on reveal in English→target multiple choice, typing, and sentence
completion, the spelling quiz plays the word when the question loads, and a
voice is chosen at random per question from the available recordings. Audio
is also pre-fetched for upcoming questions, so playback is instant.
Barsukas already has the plumbing (`AudioQualityReview` lookup,
`trakaido_audio.js`) but only wires it into one activity and always picks
the single best-status recording.

### Typing answer checking

Barsukas typing grades by exact match after NFC/case/whitespace
normalization. iOS additionally strips parenthetical disambiguators from
both sides (typing "mouse" matches "mouse (animal)"), accepts the word's
alternative translations rather than only the primary gloss, and tolerates
small typos via a Levenshtein-distance threshold on words above a minimum
length — with distinct "correct with a typo" feedback.

### Listening extras

The iOS listening activity has adaptive difficulty (four variants keyed to
the word's mastery tier, including a harder target→target format) and can
chain a follow-up multiple-choice question about the same word. Barsukas
listening is a single fixed format with a study-mode dropdown.

### Category choice

iOS supports grammatical-gender categories (masculine/feminine/neuter
nouns) in addition to semantic categories. Barsukas builds categories only
from `pos_subtype` semantic groups.

### Chinese ruby text

iOS shows pinyin above Chinese prompts and answers wherever the target
language calls for it. Barsukas templates render bare translation text with
no ruby-text support.

### Minor platform niceties

Haptic feedback on answers and celebration animations (milestones, level
advancement) are iOS-native flourishes with no Barsukas counterpart; they
matter less for a desktop database tool.

## Sources

iOS behavior: trakaido repo — `SwiftApp/Trakaido/Models/ActivityTypes.swift`,
`Utilities/ActivitySelection.swift`, `Utilities/ActivityHelpers.swift`,
`Utilities/ValidationHelpers.swift`, the `Views/Modes/` and
`Views/Activities/` directories, and
`docs/journey-mode-activities-comparison.md` /
`docs/ios-pronunciation-scoring.md`. Barsukas behavior:
`src/barsukas/routes/trakaido_activities.py`,
`templates/trakaido/activities/`, `static/js/trakaido_activities.js`,
`static/js/trakaido_audio.js`.

**Last Updated:** 2026-07-20
