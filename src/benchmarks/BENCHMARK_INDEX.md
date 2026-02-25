# Benchmark Index and Numbering Outline

This document captures the current benchmark lineup and numbering through `0200`.

## Numbering policy

- `0010`–`0099`: token-based, word-based, and simple math/transformation benchmarks.
- `0101`–`0149`: linguistics benchmarks (language, translation, morphology, sentence structure).
- `0150`–`0199`: knowledge benchmarks (facts, world knowledge, reasoning-over-facts).
- `0200`: safety classification benchmark family entry point.

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
| 0021 | `simple_arithmetic` | Simple Arithmetic | simple math | implemented |
| 0022 | `unit_conversion` | Unit Conversion | general knowledge | implemented |
| 0024 | `percentage_math` | Fractions and Percentages | simple math | implemented |
| 0026 | `time_arithmetic` | Time Arithmetic | simple math | implemented |
| 0032 | `part_of_speech` | Part of Speech | word processing | implemented |
| 0051 | `pinyin_letters` | Pinyin Letter Count | token processing | implemented |
| 0061 | `word_to_ipa` | Word to IPA | token processing | implemented |
| 0062 | `sentence_decomposition` | Sentence Decomposition | word processing | implemented |
| 0108 | `translation_en_fr` | Translation en_fr | translation | implemented |
| 0109 | `translation_en_zh` | Translation en_zh | translation | implemented |
| 0110 | `translation_sw_ko` | Translation sw_ko | translation | implemented |
| 0111 | `synonyms` | Multilingual Synonym Generation | word processing | implemented |
| 0121 | `verb_forms` | Verb Forms | word processing | implemented |
| 0122 | `lemma` | Lemma Identification | word processing | implemented |
| 0130 | `validate_lemma_form` | Validate Lemma Form (lokys) | agent regression | implemented |
| 0131 | `validate_definition` | Validate Definition (lokys) | agent regression | implemented |
| 0132 | `validate_translation` | Validate Translation (voras) | agent regression | implemented |
| 0151 | `geography` | Geography Knowledge | general knowledge | implemented |
| 0152 | `syllogism_validity` | Syllogism Validity | general knowledge | implemented |
| 0153 | `book_author_match` | Book Author Match | general knowledge | implemented |
| 0154 | `food_category_classification` | Food Category Classification | general knowledge | implemented |
| 0155 | `historical_event_year` | Historical Event Year | general knowledge | implemented |

## Numbering changes applied

- `0033_lemma` → `0122_lemma`.
- `0050_translation_en_fr` → `0108_translation_en_fr`.
- `0050_translation_en_zh` → `0109_translation_en_zh`.
- `0050_translation_sw_ko` → `0110_translation_sw_ko`.
- `0111_synonyms` is now explicitly registered and listed as implemented.
- `0035_simple_haystack` assets were removed from the repository.

## Proposed unimplemented additions

### 0010–0099: token/word/simple math
- `0034_pluralization` — singular/plural generation and validation.
- `0036_word_segmentation` — split compounds or run-on tokens into words.
- `0040_character_normalization` — Unicode/case/diacritic normalization checks.

### 0101–0149: linguistics
- `0105_reading_comprehension_short` — short paragraph QA with explicit answer spans.
- `0115_cultural_knowledge` — fact retrieval with multiple-choice distractors.
- `0140_cross_sentence_coreference` — pronoun/entity resolution across sentence pairs.
- `0145_sentence_reordering` — reconstruct coherent order from shuffled sentence chunks.

### 0150–0199: knowledge
- `0150_multihop_facts` — two-hop factual reasoning from short contexts.

### 0200+
- `0200` marks safety classification (e.g., benign vs unsafe prompt intent).


## Similar lemma-related benchmarks

- `0122_lemma`: core lemmatization task (given a word form, return lemma).
- `0130_validate_lemma_form`: agent-regression validator task (judge whether a form is lemma and suggest correction).
- They are related but not the same benchmark objective.
