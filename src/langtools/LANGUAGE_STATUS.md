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

## Spanish mechanical coverage (2026-09-15)

`es` now generates verb and adjective forms mechanically for essentially the
whole release vocabulary; only multi-word phrases ("darse cuenta", "de mala
calidad") fall through to the LLM.

- `es/orthography.py` is new: syllable nuclei, stress placement, and
  written-accent add/drop.  Both the conjugator (enclitic pronouns) and the
  adjective inflector (plural formation) need the same primitives.
- `es/conjugation.py` replaced the hand-listed `-cer/-cir` table with the
  actual rules (vowel → `-zco`, consonant → `c` → `z`), added `-ger/-gir`,
  `-quir` and `-guar` spelling, the `i` → `y` preterite for vowel stems
  (`leyó`, `leíste`), palatal stems that swallow the `i` (`gruñó`), the `-eír`
  family, the `hue-` spelling (`huelo`), accented `-iar`/`-uar` boot forms
  (`envío`, `actúo`), and pronominal verbs (`me levanto`, `levántate`).
- `es/inflection.py` covers the gendered consonant endings (`hablador`,
  `francés`), invariant comparatives, and consonant plurals with their accent
  shifts (`jóvenes`, `comunes`).
- Detailed tables live in `src/regtest/langtools/test_es_*.py`; run them with
  `./run_tests.sh regtest`.

## Adjective coverage + conjugation API (2026-06-15)

- **Adjective forms** are now configured for all core languages. `es`, `fr`,
  `de`, `nl` use the `singular_m/f` × `plural_m/f` agreement axis; `sv` uses the
  Swedish `common`/`neuter`/`plural` axis (no grammatical gender). `es` and `fr`
  additionally have mechanical adjective helpers (`inflection.py`) with LLM
  fallback; `de`/`sv`/`nl` adjectives are LLM-only. (`en`, `it`, `pt`, `lt`
  already had adjective configs.)
- **Mechanical conjugation API standardized** on
  `conjugate(lemma, ...) -> Optional[Dict[str, str]]` across the core languages.
  `fr.conjugate` now returns the forms dict (use `conjugate_detailed` for
  confidence/notes); `lt.conjugate` is the canonical name (`conjugate_verb`
  retained as alias); `en` adds a `conjugate` wrapper over `expand_verb_forms`.

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
