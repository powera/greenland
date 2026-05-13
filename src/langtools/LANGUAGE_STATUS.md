# Langtools Per-Language Status (Core Set)

This file tracks architecture status only for the current core languages:

- CJK: `zh`, `ja`, `ko`
- FIGS + additional core: `fr`, `it`, `de`, `es`, `pt`, `nl`, `sv`, `lt`

Legend:

- ✅ present
- ◐ present via shared/top-level mechanism (not language-local)
- ⭕ not currently present in language directory (may be intentional)

## Capability checklist

| Language | `llm_forms.py` | `forms_config.py` | `conjugation.py` | `grammatical_words.py` | `directions.py` | language-local `tokenizer.py` |
|---|---:|---:|---:|---:|---:|---:|
| zh | ✅ | ✅ | ⭕ | ✅ | ✅ | ✅ |
| ja | ✅ | ✅ | ⭕ | ✅ | ⭕ | ⭕ |
| ko | ✅ | ✅ | ⭕ | ⭕ | ✅ | ⭕ |
| fr | ✅ | ✅ | ✅ | ✅ | ✅ | ⭕ |
| it | ✅ | ✅ | ✅ | ✅ | ✅ | ⭕ |
| de | ✅ | ✅ | ✅ | ✅ | ✅ | ⭕ |
| es | ✅ | ✅ | ✅ | ✅ | ✅ | ⭕ |
| pt | ✅ | ✅ | ✅ | ✅ | ✅ | ⭕ |
| nl | ✅ | ✅ | ✅ | ✅ | ✅ | ⭕ |
| sv | ✅ | ✅ | ✅ | ✅ | ✅ | ⭕ |
| lt | ✅ | ✅ | ✅ | ✅ | ✅ | ⭕ |

## Notes for architecture cleanup

1. The **directory-per-language** pattern is in place for all core languages.
2. The **forms stack** (`forms_config.py` + `llm_forms.py`) is present across
   all core languages listed here.
3. **Verb conjugation** is currently concentrated in FIGS + `pt`, `nl`, `sv`,
   `lt`, `de`, while CJK languages use other morphology pathways.
4. Tokenization is mixed: `zh` has language-local tokenizer logic, while many
   other languages rely on shared behavior.
5. Dispatcher standardization at top-level `src/langtools/*.py` should continue
   to converge toward language-first dynamic import entrypoints.

## FIGS+LT directory-shape verification (2026-05-13)

Checked against `LANGUAGE_MODULE_FORMAT.md` and `STRUCTURE.md`:

- `es`, `fr`, and `lt` all include the minimum contract files:
  `__init__.py`, `llm_forms.py`, and `types.py`.
- `es`, `fr`, and `lt` all include `forms_config.py` for registry-driven form
  support.
- All three include optional core capability modules tracked in this status
  file (`conjugation.py`, `grammatical_words.py`, `directions.py`).

Intentional language-specific extras (not required by contract):

- `fr`: `verb_forms.py`, `test_utils.py`
- `lt`: `declension.py`, `principal_parts.py`
- `es` has no extra morphology helper module beyond `conjugation.py` at this
  time.
