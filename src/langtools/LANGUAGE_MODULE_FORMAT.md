# Language Module Format (Contract for `src/langtools/<lang>/`)

This document defines the **directory and file contract** each language module
should follow so top-level conditional/dynamic imports remain stable.

It is intentionally stricter than `README.md` and `STRUCTURE.md`: this is the
compatibility reference for module naming and callable entrypoints.

## 1) Required directory shape

Each language must live in:

- `src/langtools/<lang>/`

Where `<lang>` is the canonical language code used by dispatcher call sites.

Minimum required files for language participation in form generation:

- `__init__.py`
- `llm_forms.py`
- `types.py`

Recommended for registry-driven form support:

- `forms_config.py`

## 2) Standard file purposes

Use these filenames consistently across languages.

### `__init__.py`

- Marks the package.
- May re-export high-value functions/types.
- Should avoid heavy import side effects.

### `types.py`

- Holds typed models/enums/dataclasses used by the language implementation.
- Keep form-slot names and structured outputs here when language-specific.

### `forms_config.py` (optional but preferred)

- Declarative form-axis definitions for registry-based form generation.
- Consumed by `src/langtools/form_registry.py` pattern expansion.

### `llm_forms.py`

- Main per-language adapter for form-query generation.
- Exposes language-specific query functions expected by callers.
- Should route shared mechanics through common infrastructure where possible.

### `conjugation.py` (optional)

- Deterministic verb conjugation logic for languages that support it.
- May be called directly by dispatcher or from `llm_forms.py` fast paths.

### `grammatical_words.py` (optional)

- Language-specific grammatical/function-word inventories.

### `directions.py` (optional)

- Additional language notes/instructions used during prompt construction.

### `utils.py` (optional)

- Language-local normalization/helpers that do not belong in shared modules.

### `tokenizer.py` (optional)

- Language-local tokenization behavior when shared tokenization is insufficient.

### Script-specific helpers (optional)

- CJK and other script-heavy languages may include helpers like
  `pinyin_helper.py`, `romaji_helper.py`, `hangul_helper.py`, etc.

## 3) Dispatcher compatibility rules

Top-level `src/langtools/*.py` dispatchers rely on stable naming. To preserve
conditional imports and dynamic loading behavior:

1. Keep standard filenames unchanged (`llm_forms.py`, `types.py`, etc.).
2. Prefer additive changes over renames/removals.
3. When introducing a new capability, first define a shared dispatcher contract
   and then implement that capability file/function in each core language where
   meaningful.
4. If a language does not support a capability, leave the module absent or make
   the unsupported status explicit in that module (do not silently no-op).

## 4) Core callable surface (cross-language target)

Not all languages implement all capabilities, but callable contracts should be
consistent where implemented:

1. collation-key generation
2. grammatical-word classification
3. verb conjugation
4. grammatical-form generation/query
5. prompt direction notes
6. tokenization/splitting hooks
7. script/romanization conversion helpers
8. registry-based LLM form adapters

## 5) Practical change checklist

When editing a language directory:

1. Keep/restore standard filenames.
2. Ensure imports used by top-level dispatchers still resolve.
3. Update `LANGUAGE_STATUS.md` for core languages when capability presence
   changes.
4. If adding a new shared contract, document it in `STRUCTURE.md` and this file.
