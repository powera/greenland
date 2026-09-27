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
| fr | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| it | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| de | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| es | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| pt | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| nl | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| sv | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| lt | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |

`tokenizer.py` hooks present per language (all optional; see
`LANGUAGE_MODULE_FORMAT.md`):

| Language | `tokenize` | `split_contractions` | `candidate_lemmas` |
|---|---:|---:|---:|
| zh | ✅ jieba | ⭕ | ✅ |
| fr | ◐ | ✅ | ✅ |
| it | ◐ | ✅ | ✅ |
| de | ◐ | ✅ | ✅ |
| es | ◐ | ✅ | ✅ |
| pt | ◐ | ✅ | ✅ |
| nl | ◐ | ✅ | ✅ |
| sv | ◐ | ⭕ | ✅ |
| lt | ◐ | ⭕ | ✅ |
| ja, ko | ◐ | ⭕ | ⭕ |

## Notes for architecture cleanup

1. The **directory-per-language** pattern is in place for all core languages.
2. The **forms stack** (`forms_config.py` + `llm_forms.py`) is present across
   all core languages listed here.
3. **Verb conjugation** is currently concentrated in FIGS + `pt`, `nl`, `sv`,
   `lt`, `de`, while CJK languages use other morphology pathways.
4. Tokenization: only `zh` has a language-local `tokenize`; the others split
   on whitespace.  Lemma matching (`candidate_lemmas`) covers all tier 1/2
   languages.
5. Dispatcher standardization at top-level `src/langtools/*.py` should continue
   to converge toward language-first dynamic import entrypoints.

## Lemma matching for tier 1/2 languages (2026-09-26)

Sentence decomposition matched tokens to lemmas by exact string equality
against `LemmaTranslation` and `DerivativeForm`, and `DerivativeForm` rows are
nearly absent outside `lt` (~24k rows; `fr` 26, the rest 0).  In inflected
languages most tokens therefore never matched.

- `langtools.tokenizer` is now the dispatcher for three optional per-language
  hooks in `<lang>/tokenizer.py` -- `tokenize`, `split_contractions`,
  `candidate_lemmas` -- loaded by convention instead of a hard-coded module map.
- New top-level entry points: `lemma_lookup_keys(language, token)` (the token,
  its contraction parts and its lemma candidates, for DB lookup) and
  `surface_matches_lemma(language, surface, lemma)` (the confirm step).
- `suffix_rules.py` holds the shared suffix-rule engine.  Rules over-generate;
  the stored-lemma lookup is the filter.
- Share of sentence-translation tokens (400 sampled sentences per language)
  matching a stored lemma or form, exact vs with `lemma_lookup_keys`:
  `lt` 59% -> 72%, `es` 40% -> 65%, `fr` 45% -> 77%, `de` 36% -> 68%,
  `pt` 41% -> 68%, `nl` 46% -> 67%, `sv` 33% -> 62%, `zh` 42% -> 47%
  (`it` had too few translated sentences to measure).  Most remaining misses
  are grammatical words and lemmas not in the database.
- Known gaps: German/Dutch separable verbs split across the clause ("ich rufe
  dich an"), irregular forms outside the small per-language tables, and Chinese
  segmentation mismatches beyond the attached-particle / 的 / compound cases.
- Callers (`sentences.candidate_lookup`, `sentences.dialog_coverage`) still use
  exact matching; switching them to `lemma_lookup_keys` is the follow-up.

## es-419 as a form-storing language (2026-09-15)

Latin American Spanish now stores and exports its own paradigms, so WireWord
carries verb tense tables for `es` and `es-419` alike.

- A `forms_config.py` may declare `DIALECT_LANGUAGE_NAMES`; every code listed
  gets its own `GrammaticalForm` members (`verb/es-419_1s_present`), its own
  `FORM_SPECS` entries and its own `derivative_forms` rows, which is what the
  export filters on.  Only `es` opts in today -- `zh-tw` and `pt-br` are
  untouched.
- `es.conjugation.conjugate_for_dialect` is the dialect-aware entry point, and
  `langtools.conjugation.conjugate` prefers it when a language defines one,
  passing the *unresolved* code.  es-419 differs from es in the 2p slot alone,
  which takes the ustedes form; the `past` slot is the preterite, which is the
  simple past both varieties use.
- `manifest_grammar` and `person_labels` now pass the requested code to a
  language module's getter when it declares a `language_code` parameter, so
  `es/manifest.py` and `es/pronouns.py` can vary by variety.  es-419's manifest
  keeps all six person slots and reports `second_person_plural: ustedes`.
- `ustedes` moved from es's 2p pronoun list to nothing (it takes the 3p verb
  form, so offering it beside `habláis` was wrong); es-419's 2p is `ustedes`.
- `generate_mechanical_forms` covers `("es", "verb")` and all of `es-419`.  The
  TODO blocking Spanish verbs is cleared: agreement against the Spanish in
  `data/release/sentences` is 93%, up from the 78.8% recorded there, and the
  residual disagreements are translation choices rather than bad morphology.

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
