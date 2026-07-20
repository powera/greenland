# Trakaido iOS: Activity Features Not Present in the Web Interface

This document describes learning-activity features of the Trakaido iOS/macOS
(Swift) app that do not exist in the React web interface, plus behavioral
differences in shared activities. It is intended as background for Greenland
developers generating wireword data: several of these differences affect how
exported data (disambiguators, audio, sentences) is presented to learners.

Stat-tracking, sync, onboarding, and platform infrastructure (widget, iCloud,
Core Data) are deliberately out of scope. For the full cross-platform activity
matrix, see `docs/journey-mode-activities-comparison.md` in the trakaido repo.

## iOS-Only Activities

### Listen and Repeat (pronunciation practice)

The iOS app has a speaking activity with no web equivalent: the learner hears
a word or sentence and repeats it aloud, and the app grades the attempt with
on-device speech recognition (`SpeechRecognitionService`, `SpeechGrader`).

- Injected probabilistically into Journey mode (~8% of eligible turns) when
  the word has audio, the system has a speech recognizer for the target
  language, and microphone permission is not denied. It is not part of the
  shared tier configs.
- Grading is deliberately lenient: normalized Levenshtein similarity against
  the target and its alternatives, with parentheticals dropped. The primary
  goal is getting the learner to speak, not precise scoring.
- Lithuanian has no system recognizer, so Lithuanian sessions use the Polish
  recognizer plus a rule-based phonetic mapping (`SpeechPhonetics`); results
  are flagged as approximate in the UI.

See `docs/ios-pronunciation-scoring.md` in the trakaido repo for the full
design.

### Sentence Spelling Quiz

A fill-in-the-blank spelling activity for sentences (`sentence-spelling-quiz`
in the Swift `ActivityType` enum). The web app has the word-level Spelling
Quiz but not the sentence variant.

### Keyboard Training for iPhone

An iPhone-specific activity (plus an explanatory interstitial) that builds
confidence typing target-language words on the iOS keyboard: the word is
shown (with pinyin ruby text for Chinese) and the learner types it using the
native keyboard. Files: `KeyboardTrainingForIphoneActivityView.swift`,
`KeyboardTrainingForIphoneInterstitialView.swift`. Nothing comparable exists
on the web, where a hardware keyboard is assumed.

### Wi-Fi Audio Interstitial

A Journey interstitial shown when the user is on cellular with Wi-Fi-only
audio downloads enabled, offering to allow cellular downloads or continue
without audio. The interstitial is declared in the shared journey config
(so it appears in the web app's generated config file), but only the Swift
app implements a view for it — it never renders on the web.

## Behavioral Differences in Shared Activities

### Disambiguators are hidden on answer buttons

The iOS multiple-choice answer buttons strip trailing parenthetical
disambiguators before display — "mouse (computer)" renders as "mouse"
(`displayText` in `MultipleChoiceActivityView.swift`). The web app shows the
full string including the parenthetical.

**Implication for Greenland data:** on iOS, a multiple-choice option set must
remain answerable when parentheticals are invisible. Two words whose English
glosses differ only by disambiguator (e.g. "mouse (animal)" vs. "mouse
(computer)") render identically as choices, so distractor generation and
gloss choices should avoid relying on the parenthetical to distinguish
options.

Both platforms already strip parentheticals when checking typed answers, so
this only affects display.

### Auto-advance is always on in standalone practice modes

On the web, standalone modes (Multiple Choice, Typing, Listening, Spelling
Quiz, Sentence Completion, Drill) only advance automatically when the user's
auto-advance setting is enabled; otherwise a Next button is shown.

On iOS, the standalone mode views auto-advance unconditionally after each
answer. The delay is derived from the answer audio's duration (so the learner
hears the full pronunciation), capped at 10 seconds, and the multiple-choice
activity shows a failsafe Continue button if advancing stalls. Category
Choice is the one iOS mode with its own in-mode auto-advance toggle
(default on).

Journey mode behaves the same on both platforms: correct answers always
auto-advance, and a shared "auto-advance after incorrect answers" setting
controls the rest.

### Audio pre-caching and offline audio

The web app fetches audio on demand at playback time. The iOS app pre-caches
audio for upcoming words (including fetching the next activity's audio during
the auto-advance delay) and supports downloading audio for offline use, with
a Wi-Fi-only download setting. In practice this means audio-driven activities
(Listening, Spelling Quiz, Multi-Word Sequence) start instantly and work
offline on iOS.

### Haptic feedback

iOS activities give haptic feedback on correct/incorrect answers and at
celebration moments (milestones, level advancement). Not available in the
web app.

## Sources

Findings are from the trakaido repo (`SwiftApp/Trakaido/` vs. `react/`),
particularly `Models/ActivityTypes.swift`, `Utilities/ActivitySelection.swift`,
`Utilities/ActivityHelpers.swift`, the `Views/Modes/` and `Views/Activities/`
directories, and `docs/journey-mode-activities-comparison.md`.

**Last Updated:** 2026-07-20
