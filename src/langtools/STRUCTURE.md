# Langtools Architecture

This document defines the cleanup target for `src/langtools`.

## 1) Organizing principle

Langtools should operate as a **language-plugin system**:

- Shared dispatch functions live at `src/langtools/*.py`.
- Language implementations live in `src/langtools/<lang>/`.
- Top-level dispatchers dynamically import language modules based on the
  requested language code.

## 2) Directory contract

### Per-language directories

Every supported language should have a dedicated folder:

- `src/langtools/<lang>/`

That folder may expose any subset of the standard capabilities. Missing
capabilities are valid and expected for some languages.

### Top-level dispatcher modules

Top-level modules in `src/langtools/` provide stable call points for the rest of
Greenland. Dispatcher functions should:

1. accept `language` as the first argument,
2. resolve the implementation module using dynamic import, and
3. call the language-specific function when present.

## 3) Capability model

Not every language should be forced to implement every function.

Use a **capability-based** model:

- If a language implements a capability, expose it via the expected module/file.
- If not implemented, fail clearly (or return an explicit “not supported” result,
  depending on caller contract).
- Avoid stubs that silently do nothing.

## 4) Core function surface (target ~8 functions)

The practical shared API should stay focused around a small set of key
capabilities. Current target categories:

1. **Collation key** (`collation` dispatcher + per-language collation behavior)
2. **Grammatical words** (language-aware grammatical-word classification)
3. **Verb conjugation** (deterministic or assisted)
4. **General grammatical forms** (noun/adjective/etc form generation)
5. **Prompt direction notes** (`directions`)
6. **Tokenization helpers** (`tokenizer` where language-specific behavior matters)
7. **Script/romanization helpers** (CJK-focused converters/readings)
8. **LLM form-query integration** (registry-based form slots + query adapters)

The exact function names can evolve, but architecture should keep this surface
small and explicit.

## 5) Core-language focus for cleanup

This cleanup pass tracks completeness only for:

- **CJK**: `zh`, `ja`, `ko`
- **FIGS + additional core**: `fr`, `it`, `de`, `es`, `pt`, `nl`, `sv`, `lt`

Do not treat missing features in other languages as blockers for this phase.

## 6) Migration guidance

When refactoring existing code toward this architecture:

1. Move language logic into `src/langtools/<lang>/...` if still top-level.
2. Keep top-level functions as lightweight dispatchers.
3. Prefer explicit capability checks over implicit fallbacks.
4. Keep shared logic generic; keep language exceptions local to the language
   folder.
5. Update `LANGUAGE_STATUS.md` whenever core-language capability status changes.
