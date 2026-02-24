# Benchmark Index and Numbering Outline

This document captures the current benchmark lineup and proposes a numbering outline through `0200`.

## Numbering policy (draft)

- `0010`–`0099`: token-based, word-based, and simple math/transformation benchmarks.
- `0101`–`0149`: linguistics benchmarks (language, translation, morphology, sentence structure).
- `0150`–`0199`: knowledge benchmarks (facts, world knowledge, reasoning-over-facts).
- `0200`: safety classification benchmark family entry point.
- Avoid renumbering active benchmarks without explicit migration planning.

## Current implemented benchmarks

> Source of truth is the benchmark registry in `lib/utils/registry.py`.

| Code | Slug | Name | Category | Status |
|---|---|---|---|---|
| 0011 | `word_length` | Word Length | token processing | implemented |
| 0012 | `letter_count` | Letter Count | token processing | implemented |
| 0013 | `vowel_count` | Vowel Count | token processing | implemented |
| 0014 | `syllable_count` | Syllable Count | token processing | implemented |
| 0015 | `spell_check` | Spell Check | word processing | implemented |
| 0016 | `antonym` | Antonym Check | word processing | implemented |
| 0020 | `definitions` | Definitions | word processing | implemented |
| 0022 | `unit_conversion` | Unit Conversion | general knowledge | implemented |
| 0032 | `part_of_speech` | Part of Speech | word processing | implemented |
| 0033 | `lemma` | Lemma Identification | word processing | implemented |
| 0050 | `translation_en_fr` | Translation en_fr | translation | implemented |
| 0050 | `translation_en_zh` | Translation en_zh | translation | implemented |
| 0050 | `translation_sw_ko` | Translation sw_ko | translation | implemented |
| 0051 | `pinyin_letters` | Pinyin Letter Count | token processing | implemented |
| 0061 | `word_to_ipa` | Word to IPA | token processing | implemented |
| 0062 | `sentence_decomposition` | Sentence Decomposition | word processing | implemented |
| 0121 | `verb_forms` | Verb Forms | linguistics | implemented |
| 0130 | `validate_lemma_form` | Validate Lemma Form (lokys) | agent regression | implemented |
| 0131 | `validate_definition` | Validate Definition (lokys) | agent regression | implemented |
| 0132 | `validate_translation` | Validate Translation (voras) | agent regression | implemented |
| 0151 | `geography` | Geography Knowledge | knowledge | implemented (renumbered from 0120) |

### Renumber note

- `0120_geography` has been renumbered to `0151_geography`.
- This aligns geography with the new knowledge band (`0150`–`0199`).

## Proposed numbering outline (0010–0200)

This is a lightweight roadmap that preserves existing IDs and adds selective unimplemented placeholders.

### 0010–0099: token/word/simple math

#### Implemented
- `0011_word_length`
- `0012_letter_count`
- `0015_spell_check`
- `0016_antonym`
- `0020_definitions`
- `0022_unit_conversion`
- `0032_part_of_speech`
- `0033_lemma`
- `0050_translation_*`
- `0051_pinyin_letters`
- `0061_word_to_ipa`
- `0062_sentence_decomposition`

#### Suggested unimplemented additions
- `0013_vowel_count` — count vowels in a token. *(implemented)*
- `0014_syllable_count` — estimate/count syllables for single words. *(implemented)*
- `0024_percentage_math` — simple percent increase/decrease arithmetic.
- `0026_time_arithmetic` — add/subtract times and durations.
- `0034_pluralization` — singular/plural generation and validation.
- `0036_word_segmentation` — split compounds or run-on tokens into words.
- `0040_character_normalization` — Unicode/case/diacritic normalization checks.

### 0101–0149: linguistics (language/translation/sentence structure)

#### Implemented
- `0121_verb_forms`
- `0130_validate_lemma_form`
- `0131_validate_definition`
- `0132_validate_translation`

#### Suggested unimplemented additions
- `0105_reading_comprehension_short` — short paragraph QA with explicit answer spans.
- `0115_cultural_knowledge` — fact retrieval with multiple-choice distractors.
- `0140_cross_sentence_coreference` — pronoun/entity resolution across sentence pairs.
- `0145_sentence_reordering` — reconstruct coherent order from shuffled sentence chunks.

### 0150–0199: knowledge

#### Implemented
- `0151_geography`

#### Suggested unimplemented additions
- `0150_multihop_facts` — two-hop factual reasoning from short contexts.
- `0152_syllogism_validity` — determine whether simple syllogisms are logically valid.
- `0153_book_author_match` — match books to their authors.
- `0154_food_category_classification` — classify foods (e.g., meat/cheese/pasta/fruit/etc.).
- `0155_historical_event_year` — choose the correct year for major historical events.

### 0200 boundary note

- `0200` marks safety classification (e.g., benign vs unsafe prompt intent).
- Detailed `0200+` design is intentionally deferred.

## Next steps

1. Backfill migration compatibility for old `0120_geography` references in persisted datasets.
2. Decide which knowledge placeholders (`0152+`) should be formalized first (data + generator + runner).
3. Keep this file updated whenever a new benchmark code is introduced.
