# Grammar activity field audit

Read-only audit, 2026-10-22. Client source: sibling `trakaido` repository,
React web and Swift iOS. This describes the checked-out source, not a verified
App Store build or deployed CDN snapshot. Spanish with Sabi uses the same Swift
source files as Lithuanian Trakaido; product configuration differs
(`SwiftApp/Config/README.md`).

The activity requirements are documented in
[Word data required by grammar activities](grammar_activities.md).

## Lape2 batch coverage

Batch `batch_6ad7c1f23eb88190b9fc6d978ff6ab9f`, run `432f81e1c998`,
selected levels 16–30: 461 requests, 11,713 requested facts.

The tracking database records 460 completed requests, all applied with a
`written` outcome: 11,574 facts written, 122 answers rejected, and 1,411
mechanical forms added. One request (`much`, D09_006) failed with OpenAI's
`invalid_prompt` policy error. No retries were performed.

Current planner coverage for levels 16–30: 73 pending questions across 27
actionable lemmas, plus 66 previously uncertain questions. Thus 98.8% of the
original requested facts landed. Current levels 1–30 coverage has 196 pending
questions across 48 actionable lemmas and 94 previously uncertain questions;
this is a current snapshot and includes intervening database changes.

## Existing client documentation

In the sibling repository:

- `docs/grammar-mode.md`: grammar lessons, quiz statistics, first-sentence
  patterns by level, hints/tables, and pronoun drills.
- `docs/journey/activity-types.md`: Journey activity selection and platform
  availability, including pattern sentences and conjugation/declension.
- `docs/wireword-data-format.md`: wireword format.
- `SwiftApp/Config/README.md`: shared Trakaido/Sabi product code.

These documents provide activity descriptions but do not provide a complete,
current activity-to-linguistic-field contract. Some source comments incorrectly
claim wireword has no gender field. No separate agent is needed to locate the
activities; the consumer gaps below are directly visible in source.

## Data flow and consumers

Greenland's `src/exports/wireword/export_wireword.py` exports target-language
GrammarFact rows into `grammar_metadata`, including arbitrary fact keys. Forms
are exported separately in `grammatical_forms`. React `Types/Word.ts` and Swift
`Models/Word.swift` can retain these metadata dictionaries. Availability in the
database therefore does not establish use by an activity or publication to clients.

| Activity / field | Checked client behavior | Gap or requirement |
|---|---|---|
| First sentences: target noun gender | React `Utilities/sentenceQuiz.ts:88` and Swift `Models/SentenceQuiz.swift:138` read `grammar_metadata.grammatical_gender`, accepting masculine/feminine. | Already wired; nouns without an accepted value are skipped. French web patterns share the React reader. |
| First sentences: noun plurals/cases and adjective agreement | Shared sentence catalogs read `grammatical_forms`; target noun plural uses `plural` or `nominative_plural`. Adjectives require gender/number forms; Lithuanian patterns additionally use cases. | Form backfills benefit these activities after refreshed exports reach clients. |
| Lithuanian number agreement | React `Utilities/grammarPhraseQuiz.ts:221` and Swift `Models/QuizNounData.swift:98` infer gender from noun endings. Require nominative/genitive plural forms. | Do not consume the stored gender fact; prefer explicit gender and define missing-data behavior. |
| Lithuanian preposition cases | Same noun catalogs require genitive, accusative and instrumental singular forms. | Consume forms, but do not check countability or number paradigm. |
| Declension case identification | React `Utilities/declensionQuiz.ts` and Swift `Views/Activities/DeclensionQuizRunnerView.swift` read noun case/number forms. Both add the base target as nominative singular. | Need explicit handling for plural-only nouns; base spelling is not proof of a singular form. |
| Conjugation practice | Client conjugation flows consume exported verb paradigms. | Classification facts alone are not complete conjugation tables. |
| Per-language countability | No `countability` consumer found in the checked React or Swift application source. Spanish/Lithuanian sentence modules instead use hardcoded `MASS_NOUNS` sets. | Read English and target countability independently; specify handling for `both` and mismatches. |
| Number paradigm (`number_type`) | No consumer found in checked React/Swift source. | Gate singular/plural frames using stored classifications, including plural-only nouns. |
| English noun plurals | React `Utilities/sentenceQuiz.ts:185` and Swift `Models/SentenceQuiz.swift:193` use local irregular lists and suffix rules. | Do not read database English plurals. Need an explicit source-language forms contract; target-only grammar metadata is insufficient. |
| Chinese `measure_words` | Chinese grammar activities are not implemented yet. | Outside the current activity scope; not an existing activity wiring gap. |
| English adjective/adverb `gradability` | No consumer found in checked React/Swift source. | Records comparison strategy (e.g. redder/reddest); relevant to a future comparison activity, not today's noun sentence drills. |
| Pronoun practice and grammar lessons | Authored pronoun data and separate lesson JSON. | Not driven by Lape2 noun/adjective facts. |

The separate Barsukas runtime sentence-pattern renderer already documents
explicit English/target countability and classifier requirements in
`docs/sentence_patterns.md`. That is a Greenland consumer, not proof that the
Trakaido/Sabi generators use the same logic.

## Follow-up scope

1. Define the source/target facts and forms contract, especially English
   plurals and countability alongside target metadata.
2. Replace ending-based gender selection and grammatical mass/number lists
   with explicit facts; keep semantic suitability filters separate.
3. Handle plural-only base entries in declension and sentence catalogs.
4. Refresh and inspect wireword exports, then verify client loading and
   representative activities. This audit did not export, upload, build iOS,
   retry model requests, or modify sibling-repository code.
