# English worksheets

Barsukas-only UI for printable English-to-English practice for native-speaking
K–12 learners, including self-study and advanced learners. This is general
practice, not a dyslexia intervention or a complete reading curriculum.

## Integration and layout

Barsukas installs this package with `from worksheets import register` and
`register(app)`. Open **Trakaido → English Worksheets**, or `/worksheets/`.
There is no CLI, separate server, teacher portal, or learner tracking.

- `activities/`: renderer-independent spelling and matching builders.
- `models.py`: source words, questions, and worksheets, retaining sense GUIDs.
- `sources.py`: read-only selection from the existing Barsukas database session.
- `rendering/`: PDF layout and local emoji rasterization.
- `views.py`, `templates/`: ordinary server-rendered forms and previews.

Install the normal project requirements (including ReportLab). Emoji PDFs also
need **Noto Color Emoji** (Debian/Ubuntu: `fonts-noto-color-emoji`). The default
font path is `/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf`; override it with
`WORKSHEETS_EMOJI_FONT`. Pillow, installed with ReportLab, rasterizes the emoji
locally into the PDF. No image download or live model call is made. Missing
fonts produce a form error rather than a PDF with replacement squares.

## Available activities

1. **Spelling — missing letters:** fill gaps using an English definition or emoji.
2. **Spelling — scramble:** rearrange letters using a definition or emoji clue.
3. **Matching:** match English words to independently shuffled definitions or emojis.

Choose a category, 2–20 questions, version number, and US Letter/A4. Preview
includes answers and source GUIDs for review. Download the student PDF and a
separate answer key. The same settings reproduce content while the database
remains unchanged; a changed database can change the selection.

Selection uses single alphabetic English headwords of 2–16 letters with GUIDs,
unique word spellings and unique clues. Definitions containing the answer as a
whole word are excluded. Emoji comes from existing sense-linked assignments;
entries without the requested clue are skipped. Insufficient content produces an
explicit error. Existing generic difficulty levels are not presented as English
school grades or spelling-difficulty ratings.

Review the preview for age suitability, overly revealing definitions, anagrams,
and emoji ambiguity. Existing definitions have not been rewritten for children;
emoji uniqueness does not guarantee a child will interpret each clue correctly.
The answer key records the intended sense/word; anagrams may admit alternatives.

## Desired activities and required Barsukas data

| Activity | Additional data and UI |
| --- | --- |
| Phonics and pattern sorting | English learning facts for phonemes, grapheme–sound alignment, CVC, vowel patterns, digraphs, blends, and syllables; edit/filter/bulk-review controls |
| Graded spelling | Instructional pattern membership, regularity/exceptions, documented spelling difficulty; collection and coverage views |
| Pronunciation practice | Pronunciation difficulty and sound structure linked to the relevant English pronunciation/variety |
| Word transformations | Candidate chains built from classified words, followed by human review of the intended spelling/sound changes |
| Meaning in context / best word | Sense-linked, child-suitable examples and reviewed distractors; author/review screens |
| Word parts and families | Reviewed prefix, suffix, root, and family relationships with instructional explanations |
| Reading comprehension | Authored passages and questions with correct answers and age/content suitability |
| Silent and oral fluency | Passages with word counts and difficulty; timing/accuracy/comprehension recording sheets. PDFs support manual practice, not automatic measurement |
| Sentence editing and word use | Reviewed prompts, acceptable answers, and feedback/rubrics |
| Competence collections and checks | Stage-specific competences, prerequisites, item-selection rules, and fresh assessment sets |

### Proposed storage boundary

Add registered **English learning facts**, following the grammar-facts validation,
provenance, review, and release/import conventions. Reuse existing grammatical
facts where relevant; educational difficulty and phonics annotations need not be
classified as grammar. A dedicated learning-facts table is the current proposal,
not implemented here. Choose the exact schema before adding classifications.

Facts should identify the form or pronunciation they describe rather than copy
identical spelling properties across every sense. Define CVC in terms of sound
and spelling correspondence, not simply three letters. Keep spelling difficulty
separate from pronunciation difficulty, document rating criteria, and retain
unknown values. Preserve nonderivable classifications through release round trips.

Passages, questions, ordered exercise sets, and competence definitions need
structured records rather than large fact-value blobs. Keep them linked to
existing word/sense GUIDs. Learner attempts and mastery are separate future app
state, not worksheet content.

### Longer-term learning design

Foundations, independent practice, and advanced vocabulary/precision each have
2–10 specific competences, without requiring every stage to cover the same areas.
Vocabulary is explicit throughout. Foundations and independent practice include
both silent and oral fluency, with comprehension/accuracy alongside speed.
Earlier advancement means readiness for the next experience; the final stage
supports bounded goal completion and continued study, not “finishing English.”

Later features: curated age-suitable collections, images, sample/model audio,
reviewable distractors, JSON exercise export for app reuse, and frozen worksheet
versions. Teacher accounts, assignments, and class reporting remain outside the
initial scope.
