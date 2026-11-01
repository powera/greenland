# ipa

Utilities for working with IPA (International Phonetic Alphabet)
pronunciations: generation, normalization, and rhyme key computation.

## Layout

- `generation.py` — LLM-based IPA pronunciation generation with schema
  validation
- `normalization.py` — IPA string normalization, character validation, and
  similarity scoring
- `rhyme_keys.py` — language-specific rhyme key computation (vowel/stress
  detection)
- `ipa_chars.json` — reference data of valid IPA characters

The public API is exported from `__init__.py` (e.g.,
`generate_ipa_pronunciation`, `normalize_ipa`, `compute_rhyme_key`).

## English character checks

`invalid_english_ipa_characters` checks generated English pronunciations against
our IPA character reference plus common notation (delimiters, spaces, syllabic
marks, and affricate ties). It accepts bare IPA as well as slash-delimited IPA;
it does not use the comparison normalizer, which can discard parts of a string.
English word-pronunciation storage and standalone IPA generation reject
unsupported characters. This checks characters only: a valid transcription can
still represent the wrong word, sense, or tense. Spelling similarity is not used
as a correctness gate. English prompts request General American pronunciation.
