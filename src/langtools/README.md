# Langtools

`src/langtools` contains language-processing helpers shared across Greenland.

## Purpose

Langtools primarily supports three needs:

1. **Form generation/extraction** for lemmas (e.g., inflections and conjugations).
2. **Romanization/reading helpers** for non-Latin scripts.
3. **Language-aware sorting keys** for consistent dictionary ordering.

## Scope at a glance

- Western-language helpers for lexical form workflows.
- Chinese/Japanese/Korean utilities for readings and text normalization.
- Collation helpers used by dictionary and browse interfaces.
- Prompt-direction notes used by shared generation pipelines.

## Typical usage

Langtools modules are consumed by higher-level systems (not usually run directly):

- `wordfreq` pipelines (form generation and lexical processing)
- Barsukas dictionary/browse features (sorting + display helpers)
- Agent workflows that need language-specific normalization

## Structure

```text
langtools/
├── <language_code>/   # Language-focused helpers
├── collation.py       # Shared sort-key generation
├── directions.py      # Prompt direction note loader
└── README.md
```

For implementation details and deeper architecture notes, see `STRUCTURE.md`.
