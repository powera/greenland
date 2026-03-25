# Langtools

`src/langtools` is Greenland's shared language-logic package.

It provides reusable building blocks for:

1. **Form generation** (noun/verb/adjective/adverb paradigms).
2. **Script helpers** (romanization, reading extraction, script conversion).
3. **Language-aware collation** (stable dictionary sorting behavior).
4. **Prompt direction notes** used by form-generation workflows.

## Who uses this package

`langtools` is imported by higher-level systems, especially:

- `src/wordfreq/translation/*` for LLM form generation pipelines.
- `src/clients/*` dispatch paths that call language-specific query methods.
- `src/barsukas/*` browse/search experiences that rely on sorting and display helpers.

## High-level layout

```text
src/langtools/
├── <lang>/            # Per-language modules (e.g. en, zh, lt, ko)
├── form_registry.py   # Central (language, POS) form specs
├── llm_forms_base.py  # Shared query engine for all language/POS specs
├── form_patterns.py   # Pattern expansion for forms_config definitions
├── collation.py       # Shared sort-key generation
├── directions.py      # Dispatcher for optional language direction notes
├── dialect_overrides.py
├── README.md
└── STRUCTURE.md       # Detailed architecture + extension guide
```

## Language module patterns

Most language folders follow one of these patterns:

- **Full-stack modules** (for example `en`, `de`, `es`, `fr`, `lt`):
  - rich `types.py` models,
  - language utilities,
  - optional Wiktionary parsing,
  - `llm_forms.py` entrypoints.
- **Config-driven modules** (many newer languages):
  - `forms_config.py` declares form axes,
  - `form_registry.py` + `form_patterns.py` derive mappings automatically,
  - thin `llm_forms.py` wrappers call shared logic.
- **Script/helper-heavy modules** (for example `zh`, `ja`, `ko`):
  - still support form queries,
  - additionally expose script-specific utilities such as pinyin/romaji/hangul decomposition.

## Core idea: registry-driven forms

The central `FORM_SPECS` registry (in `form_registry.py`) defines each supported
`(language_code, pos_type)` combination. Shared logic in `llm_forms_base.py`
consumes a `LanguageFormSpec` and performs schema construction, prompt loading,
LLM calling, and query logging.

This removes duplicated per-language boilerplate and keeps task generation in
`src/wordfreq/translation/generate_forms_tasks.py` data-driven.

## Quick extension checklist

When adding a new config-driven language or POS:

1. Add `src/langtools/<lang>/forms_config.py` with the form pattern config.
2. Add a thin `src/langtools/<lang>/llm_forms.py` wrapper if explicit import
   points are needed by other code.
3. Confirm `FORM_SPECS[(<lang>, <pos>)]` is populated.
4. Run task discovery/validation paths in translation tooling.

For the deep architecture and dependency notes, read `STRUCTURE.md`.
