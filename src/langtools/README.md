# Langtools

`src/langtools` is Greenland's shared language-logic package.

## Target architecture (current direction)

Langtools is being aligned to a language-plugin architecture with these rules:

1. **Each language lives in its own directory** under `src/langtools/<lang>/`.
2. **Top-level `src/langtools/*.py` functions are dispatchers** that:
   - take `language` as the first argument, and
   - perform a dynamic import of the language implementation.
3. **Language capability is intentionally partial**:
   - not every function is meaningful for every language,
   - missing functionality should be represented explicitly (for example by
     no implementation, `NotImplementedError`, or a capability check).
4. **A focused core surface area** (about eight key functions), such as:
   - collation key generation,
   - grammatical-word classification,
   - verb conjugation,
   - noun/other inflectional form generation,
   - language-specific prompt direction notes,
   - tokenizer/splitting helpers,
   - script/romanization helpers,
   - registry-based LLM form querying.

This README is intentionally high-level; see `STRUCTURE.md` for concrete
module contracts and `LANGUAGE_STATUS.md` for per-language status.

## Important scope note

Core-language planning and gap discussion currently focuses on:

- **CJK**: `zh`, `ja`, `ko`
- **FIGS + additional core**: `fr`, `it`, `de`, `es`, `pt`, `nl`, `sv`, `lt`

Non-core languages can continue to evolve, but are not the focus of the current
architecture cleanup pass.
