# Benchmark Index and Numbering Outline

This document captures the current benchmark lineup and proposes a numbering outline through `0200`.

## Numbering policy (draft)

- `0010`–`0099`: token-based, word-based, and simple math/transformation benchmarks.
- `0100`–`0199`: more complex knowledge, validation, and multi-sentence benchmarks.
- `0200`–`0299`: reserved for task-planning and agentic workflows (out of scope for now).
- Avoid renumbering active benchmarks without explicit migration planning.

## Current implemented benchmarks

> Source of truth is the benchmark registry in `lib/utils/registry.py`.

| Code | Slug | Name | Category | Status |
|---|---|---|---|---|
| 0011 | `word_length` | Word Length | token processing | implemented |
| 0012 | `letter_count` | Letter Count | token processing | implemented |
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
| 0120 | `geography` | Geography Knowledge | general knowledge | implemented (candidate renumber) |
| 0121 | `verb_forms` | Verb Forms | word processing | implemented |
| 0130 | `validate_lemma_form` | Validate Lemma Form (lokys) | agent regression | implemented |
| 0131 | `validate_definition` | Validate Definition (lokys) | agent regression | implemented |
| 0132 | `validate_translation` | Validate Translation (voras) | agent regression | implemented |

### Note on `0120_geography`

- `0120_geography` appears to be the main potential renumber candidate based on current sequencing.
- Suggested target if renumbered later: `0110_geography` (or another free `01xx` slot aligned with knowledge benchmarks).
- No renumbering is performed in this change.

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
- `0013_vowel_count` — count vowels in a token.
- `0014_syllable_count` — estimate/count syllables for single words.
- `0024_percentage_math` — simple percent increase/decrease arithmetic.
- `0026_time_arithmetic` — add/subtract times and durations.
- `0034_pluralization` — singular/plural generation and validation.
- `0036_word_segmentation` — split compounds or run-on tokens into words.
- `0040_character_normalization` — Unicode/case/diacritic normalization checks.

### 0100–0199: knowledge + multi-sentence + regression

#### Implemented
- `0120_geography` *(possible renumber later)*
- `0121_verb_forms`
- `0130_validate_lemma_form`
- `0131_validate_definition`
- `0132_validate_translation`

#### Suggested unimplemented additions
- `0105_reading_comprehension_short` — short paragraph QA with explicit answer spans.
- `0110_geography` — reserved as a possible future destination for current geography benchmark code.
- `0115_cultural_knowledge` — fact retrieval with multiple-choice distractors.
- `0140_cross_sentence_coreference` — pronoun/entity resolution across sentence pairs.
- `0150_multihop_facts` — two-hop factual reasoning from short contexts.
- `0160_instruction_following_structured` — strict format-following across multi-sentence prompts.
- `0180_safety_policy_classification` — classify benign vs unsafe prompt intents.

### 0200 boundary note

- `0200` marks the beginning of task-planning benchmarks.
- Detailed `0200`–`0299` design is intentionally deferred.

## Next steps

1. Confirm whether to renumber `0120_geography`.
2. Decide which proposed placeholders should be formalized first (data + generator + runner).
3. Keep this file updated whenever a new benchmark code is introduced.
