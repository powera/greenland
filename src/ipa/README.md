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
