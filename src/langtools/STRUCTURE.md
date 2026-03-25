# Langtools Architecture

This document is the implementation-focused reference for `src/langtools`.

## 1) System overview

`langtools` is organized around a **registry-driven form generation model**:

- Per-language config/modules declare grammatical form inventory.
- `form_registry.py` builds `FORM_SPECS[(language_code, pos_type)]` entries.
- `llm_forms_base.py` executes shared form query logic using one spec.
- `wordfreq.translation.generate_forms_tasks` builds runnable tasks from
  those specs.

In parallel, `langtools` also contains:

- script helpers (Chinese/Japanese/Korean and others),
- language collation helpers,
- dialect override behavior,
- optional language-specific direction notes.

---

## 2) Top-level modules and responsibilities

- `form_registry.py`
  - Discovers `langtools/*/forms_config.py` files.
  - Expands config patterns into concrete form field lists + enum mappings.
  - Builds the canonical `FORM_SPECS` mapping.

- `llm_forms_base.py`
  - Defines `LanguageFormSpec` dataclass.
  - Implements shared `query_forms(...)` logic:
    - lemma/translation loading,
    - JSON schema assembly,
    - prompt/context loading,
    - LLM call + logging,
    - form extraction/validation.

- `form_patterns.py`
  - Expands declarative form patterns such as:
    - `case_number`,
    - `person_tense`,
    - `case_number_gender`,
    - `degree`,
    - `explicit`,
    - `singular_plural`, `tense_only`, `base_only`.

- `collation.py`
  - Produces language-aware sort keys so SQLite binary collation aligns with
    expected lexical order.

- `directions.py`
  - Loads optional per-language prompt direction notes (from
    `langtools/<lang>/directions.py` when present).

- `dialect_overrides.py`
  - Declares dialect relationships and optional transforms (for example
    Simplified/Traditional Chinese behavior).

---

## 3) Language folder archetypes

### A. Full-stack lexical modules (deep file breakdown)

Primary examples: `en`, `de`, `es`, `fr`, `lt`.

These folders usually contain the files below (some language-specific extras
exist, but this is the common pattern):

- `__init__.py`
  - Package marker and light exports.

- `types.py`
  - Dataclasses/enums for that language's paradigm outputs (noun/verb/etc).
  - Defines expected form slot names and metadata fields used by parsers and
    generation paths.

- `forms_config.py`
  - Declarative POS configs consumed by registry auto-discovery.
  - Source of truth for form axes in the registry-driven pipeline.

- `utils.py`
  - Text normalization and utility heuristics (cleaning, article extraction,
    gender hints, person-label normalization, etc.).

- `wiktionary.py`
  - Optional Wiktionary parser implementation for this language.
  - Converts templates/tables/text into language `types.py` structures.

- `conjugation.py`
  - Mechanical conjugation logic where available.
  - Used by `llm_forms.py` as a fast deterministic path before LLM fallback.

- `llm_forms.py`
  - Runtime entrypoints called by client/workflow code.
  - Common contents:
    1. `*_FORM_MAPPING` constants read from `FORM_SPECS`.
    2. `query_<language>_<pos>_*` functions that call shared `query_forms(...)`.
    3. Optional deterministic fast path for verbs (mechanical conjugation), with
       fallback to shared LLM querying and query logging.
  - In other words, `llm_forms.py` is the language adapter that binds the shared
    engine to language-specific naming and optional pre-LLM logic.

- `pronouns.py`
  - Subject-pronoun inventory by person slot (`1s`, `2s`, ...).
  - Consumed by `langtools.person_labels` to generate person labels/metadata
    for UI/prompts and ambiguity handling.

- `grammatical_words.py`
  - Four-tier lexical inventory for filtering/linking behavior:
    - personal pronouns,
    - grammatical-only words,
    - function words,
    - non-personal pronouns.
  - Consumed by top-level `langtools.grammatical_words` registry and sentence/
    linker pipelines.

- `manifest.py` (where present)
  - WireWord grammar-manifest metadata for tense/person slot presentation.

- `verb_forms.py` (where present)
  - Verb-form benchmark layout/prompt config for evaluation tooling.

- `directions.py` (where present)
  - Additional language prompt-direction notes.

- language-specific extras
  - Example: Lithuanian `principal_parts.py`, German generated conjugation data,
    English `rhyme_key.py`, test helper modules.

#### Why `pronouns.py` and `grammatical_words.py` are separate

They should stay separate.

- `pronouns.py` is **person-slot metadata** (`1s`/`2s`/`3p`) for conjugation and
  person-label UX paths.
- `grammatical_words.py` is **token-tier classification** for lexical filtering
  and lemma-link decisions.

There is intentional overlap in surface words (for example subject pronouns),
but the data models and consumers are different, so merging would blur two
separate responsibilities.

### B. Config-driven modules

Many languages use:

- `forms_config.py` as the single declarative source of form axes,
- `types.py` and `llm_forms.py` wrappers,
- automatic registration via top-level registry tooling.

This pattern minimizes duplicated boilerplate.

### C. Script/helper-focused modules

Examples: `zh`, `ja`, `ko`.

These modules provide script-specific helpers **and** can participate in
registry-driven form generation (via `forms_config.py` + `llm_forms.py`).

Helper highlights:

- `zh/pinyin_helper.py`, `zh/converter.py`
- `ja/romaji_helper.py`, `ja/gojuon.py`
- `ko/hangul_helper.py`

---

## 4) Form generation flow (runtime)

1. A workflow asks for forms for language/POS.
2. It resolves a `LanguageFormSpec` from `FORM_SPECS`.
3. `query_forms(...)` builds the schema + prompt payload.
4. Client call executes through the unified LLM client.
5. Response forms are normalized into `Dict[str, str]` and logged.

`generate_forms_tasks.py` creates tasks from all registered specs and applies
language/POS overrides (thresholds, fetch strategy, explicit client methods)
where needed.

---

## 5) Adding or updating a language (recommended path)

For a new config-driven language:

1. Create `src/langtools/<lang>/forms_config.py` with POS configs.
2. Ensure enum members needed by those forms are derivable from pattern output.
3. Add `src/langtools/<lang>/llm_forms.py` wrapper functions if call sites
   expect explicit imports.
4. Verify `FORM_SPECS` contains the expected `(lang, pos)` entries.
5. Run related translation/form-generation checks.

For languages that require advanced parsing or special behavior, add optional
helpers (`utils.py`, parser modules, script tools) without bypassing the shared
registry/query path unless there is a clear reason.

---

## 6) Notes for maintainers

- Prefer adding new behavior through declarative config + shared infrastructure
  before creating bespoke per-language pipelines.
- Keep language-specific constants/logic scoped to each language folder.
- Keep doc comments near pattern definitions and overrides synchronized with the
  behavior in `form_registry.py` and `generate_forms_tasks.py`.
