# Langtools Architecture

## Directory layout

```
langtools/
├── __init__.py              # Package exports and docstring
├── collation.py             # Shared Latin-alphabet sort-key generation
├── dialect_overrides.py     # Dialect variant registry (zh-tw, es-mx, pt-br, …)
├── form_patterns.py         # Pattern expansion for forms_config dicts (NEW)
├── form_registry.py         # Central registry: (lang, pos) → LanguageFormSpec
├── llm_forms_base.py        # Shared query_forms() used by all per-language llm_forms
├── README.md                # Plain-English overview (what the tools do)
├── STRUCTURE.md             # This file (architecture reference)
│
├── CJK modules (self-contained, no cross-dependencies)
│   ├── zh/                  # Chinese
│   │   ├── pinyin_helper.py   # Pinyin transliteration and ruby HTML
│   │   └── converter.py       # Traditional/Simplified character conversion
│   ├── ja/                  # Japanese
│   │   ├── romaji_helper.py   # Romaji/hiragana conversion and ruby HTML
│   │   └── gojuon.py          # Gojuon (五十音) syllabary ordering tables
│   └── ko/                  # Korean
│       └── hangul_helper.py   # Hangul syllable decomposition into jamo
│
├── Full-stack Western European modules
│   │  (all have: types, utils, wiktionary parser, LLM forms, CLI scripts)
│   ├── en/                  # English
│   ├── de/                  # German
│   ├── es/                  # Spanish
│   ├── fr/                  # French
│   └── lt/                  # Lithuanian
│
├── Config-driven modules (forms_config.py as single source of truth)
│   │  (forms_config + types + llm_forms shim + generate scripts)
│   ├── lv/                  # Latvian   (7-case nouns, 6-person verbs, adjectives, adverbs)
│   └── uk/                  # Ukrainian (7-case nouns, 6-person verbs, adjectives, adverbs)
│
├── Partial Western European modules
│   │  (types and LLM forms only; no Wiktionary parser)
│   ├── it/                  # Italian   (types + llm_forms)
│   ├── nl/                  # Dutch     (types + llm_forms)
│   ├── pt/                  # Portuguese (types + llm_forms + generate scripts)
│   └── sv/                  # Swedish   (types + llm_forms)
│
├── Partial Eastern European modules
│   │  (types and LLM forms only; no Wiktionary parser)
│   ├── ro/                  # Romanian  (types + llm_forms)
│   └── pl/                  # Polish    (types + llm_forms)
│
└── South Asian modules
    │  (types and LLM forms only; no Wiktionary parser)
    ├── ta/                  # Tamil     (types + llm_forms)
    ├── te/                  # Telugu    (types + llm_forms)
    ├── kn/                  # Kannada   (types + llm_forms)
    ├── ml/                  # Malayalam (types + llm_forms)
    └── si/                  # Sinhala   (types + llm_forms)
```

## File roles within a language module

Full-stack language modules (en, de, es, fr, lt) follow a consistent
internal structure.  Partial modules implement a subset of these layers.

### types.py -- Data structures

Pydantic `@dataclass` classes that define the grammatical forms for each
part of speech in the language.  Every dataclass has:

- `word` -- the lemma (base form)
- `forms` -- `Dict[str, str]` mapping form names to inflected text
- `alternatives` -- `Dict[str, List[str]]` for forms with multiple valid spellings
- `confidence`, `notes`, `raw_template` -- metadata

Languages with grammatical gender also define a `Gender` enum
(e.g. `GermanGender`, `FrenchGender`).

The number and kind of forms varies by language — case-heavy languages
(Lithuanian, Polish, German) have many noun forms, while languages
without a case system (English, Italian, the Dravidian and Sinhala
modules) only track singular/plural.  See each language's `types.py`
for its specific form inventory.

### utils.py -- Language-specific helpers

Pure functions for text normalization and heuristic form generation:

- `clean_form(text)` -- split alternative spellings on `/` and `,`
- `normalize_*_text(text)` -- Unicode NFC normalization
- `detect_gender_from_article(article)` -- map articles to gender enum
- `extract_article(text)` -- separate article from noun
- Language-specific heuristics (e.g. English `generate_regular_plural`,
  Lithuanian `remove_stress_marks`)

### wiktionary.py -- Wiktionary HTML parser

A `Parser` class (e.g. `EnglishParser`, `GermanParser`) that:

1. Receives wikitext or HTML fetched by `clients.wiktionary`
2. Locates language-specific templates (e.g. `en-noun`, `de-ndecl`, `lt-conj`)
3. Extracts inflected forms from template parameters
4. Falls back to heuristic generation (via utils) when templates are missing

### llm_forms.py -- LLM-based form generation

Queries a remote LLM to produce all inflected forms for a lemma.
Each file defines:

- `*_FORM_MAPPING` dicts -- maps internal form names to `GrammaticalForm` enum values
- `query_*_forms()` functions -- builds a JSON schema, sends a prompt via
  `UnifiedLLMClient`, validates the response, and logs the query to the database

### forms_config.py -- Declarative form definitions (config-driven modules)

Languages that use the config-driven approach define their entire
grammatical structure in a single `forms_config.py` file.  Everything
else (enum members, `FORM_SPECS` entries, form generation tasks) is
derived automatically.

Each file exports:

- `LANGUAGE_CODE` -- ISO 639-1 code (e.g. `"lv"`)
- `LANGUAGE_NAME` -- display name (e.g. `"Latvian"`)
- `NOUN_CONFIG`, `VERB_CONFIG`, etc. -- dicts describing each POS

Config dicts specify a pattern `type` and the axes to expand:

| Pattern type         | Axes                        | Example output fields                         |
|----------------------|-----------------------------|-----------------------------------------------|
| `"case_number"`      | cases × numbers             | `nominative_singular`, `genitive_plural`, ...  |
| `"person_tense"`     | persons × tenses            | `1s_present`, `2s_past`, ...                   |
| `"case_number_gender"` | cases × numbers × genders | `nominative_singular_m`, `dative_plural_f`, .. |
| `"degree"`           | explicit list               | `positive`, `comparative`, `superlative`       |
| `"singular_plural"`  | --                          | `singular`, `plural`                           |
| `"tense_only"`       | tenses                      | `present`, `past`, `future`                    |
| `"base_only"`        | --                          | `base`                                         |
| `"explicit"`         | explicit list               | (whatever the config specifies)                |

Optional `extra_schema` dict adds fields like `number_type` to the
LLM query schema.

**How auto-registration works:**

1. `enums.py` scans `langtools/*/forms_config.py` at import time and
   dynamically adds any missing `GrammaticalForm` enum members.
2. `form_registry.py` does the same scan and builds `FORM_SPECS`
   entries using `form_patterns.expand_fields()` / `expand_enum_names()`.
3. `generate_forms_tasks.py` picks up form mappings from `FORM_SPECS`
   and uses `client_method_name="query_language_forms"` (generic dispatch).
4. `client.py`'s `__getattr__` resolves any `query_<lang>_<pos>_*`
   method name to `query_language_forms(lang_code, pos_type, lemma_id)`.

**Adding a new config-driven language** requires only:

1. Create `langtools/<lang>/forms_config.py` with the config dicts.
2. (Optional) Create `langtools/<lang>/llm_forms.py` as a thin shim
   re-exporting `FORM_SPECS[(...)]` mappings, if other code needs
   direct imports.

No edits to `enums.py`, `form_registry.py`, `generate_forms_tasks.py`,
or `client.py` are needed.

### generate_*.py -- CLI task wrappers

Thin scripts that delegate to the shared task registry in
`wordfreq.translation.generate_forms_tasks`:

```python
TASK_KEY = "english_nouns"
def main():
    run_form_generation_task(TASK_KEY)
```

Run with: `PYTHONPATH=src python src/langtools/en/generate_noun_forms.py`

Available scripts by language:

| Language   | Nouns | Verbs | Adjectives | Adverbs |
|------------|-------|-------|------------|---------|
| English    | yes   | yes   | yes        | yes     |
| German     | yes   | yes   | --         | --      |
| Spanish    | yes   | yes   | --         | --      |
| French     | yes   | yes   | --         | --      |
| Lithuanian | yes   | yes   | yes        | yes     |
| Latvian    | yes   | yes   | yes        | yes     |
| Ukrainian  | yes   | yes   | yes        | yes     |
| Portuguese | yes   | yes   | --         | --      |

## dialect_overrides.py -- Dialect variant registry

Centralised registry of dialect variants (e.g. zh-tw, es-mx, pt-br, fr-ca,
en-gb) and their relationships to parent languages.  Each entry is a
`DialectOverride` frozen dataclass that records:

- **parent_lang**: the base language code the dialect derives from
- **display_name / dialect_display_name**: short and prompt-friendly names
- **text_transform / reverse_transform**: optional callables to convert text
  between parent and dialect (e.g. Simplified ↔ Traditional Chinese via
  `zh/converter.py`)
- **sort_key_lang**: which language's sort-key logic to use (usually the parent)
- **tts_locale**: BCP-47 locale for speech synthesis (e.g. `"pt-BR"`)
- **llm_prompt_note**: extra instruction for LLM prompts

Public helpers:

| Function | Purpose |
|----------|---------|
| `is_dialect(code)` | Check if a code is a registered dialect |
| `get_parent_language(code)` | Get parent lang (returns self for non-dialects) |
| `get_dialect_display_name(code)` | Prompt-friendly name with dialect qualifier |
| `get_dialects_for_language(parent)` | List all dialect codes for a parent |
| `transform_to_dialect(code, text)` | Convert parent text → dialect |
| `transform_from_dialect(code, text)` | Convert dialect text → parent |
| `get_sort_key_language(code)` | Which lang's sort-key to use |
| `get_tts_locale(code)` | BCP-47 TTS locale |
| `get_llm_prompt_note(code)` | Extra LLM instruction for this dialect |

Import from `langtools.dialect_overrides` rather than hard-coding dialect
information in individual agents or routes.

## collation.py -- Shared sort-key generation

Produces binary-sortable strings so that SQLite's default binary collation
gives linguistically correct alphabetical ordering.  Two strategies:

**Position remapping** (lt, es, sv, vi, ro, pl): Characters that are
distinct letters in the language's alphabet are mapped to sort in the
right position.  For example, Lithuanian ą sorts after a but before b,
encoded as `a{`.

**Diacritic stripping** (de, fr, it, nl, pt): Accented characters are
not separate letters; accents are removed via Unicode NFD decomposition
so that `café` sorts as `cafe`.

CJK sort keys are handled by the respective language modules (ja, ko,
zh), not by collation.py.  South Asian scripts (ta, te, kn, ml, si)
do not currently have collation support.

## CJK modules

These are self-contained and do not follow the Western European file
convention.  They have no Wiktionary parsers or LLM form generation,
because CJK languages do not inflect words the same way.

**Chinese (zh/):** Pinyin transliteration (via `pypinyin` + `jieba` word
segmentation), HTML ruby annotations, and Traditional/Simplified conversion
(via `opencc`).  All libraries are optional; functions return `None` or
passthrough text when unavailable.

**Japanese (ja/):** Romaji romanization and hiragana reading generation
(via `pykakasi`), HTML ruby annotations, and gojuon syllabary tables for
dictionary alphabet-bar ordering.

**Korean (ko/):** Hangul syllable decomposition into jamo (consonant/vowel
components) using Unicode arithmetic.  No external libraries needed.
Produces sort keys that match standard Korean dictionary order.

## Dependency graph

```
collation.py                      (standalone, no imports from langtools)
dialect_overrides.py              (imports zh/converter.py lazily, storage.translation_helpers lazily)
form_patterns.py                  (standalone, pure expansion logic)

zh/converter.py                   (standalone, uses opencc)
zh/pinyin_helper.py               (imports zh/converter.py, uses pypinyin + jieba)

ja/romaji_helper.py               (standalone, uses pykakasi)
ja/gojuon.py                      (standalone, pure data)

ko/hangul_helper.py               (standalone, pure Unicode arithmetic)

<lang>/forms_config.py            (standalone, pure data — config-driven modules only)
<lang>/types.py                   (imports clients.wiktionary.types)
<lang>/utils.py                   (imports <lang>/types.py)
<lang>/wiktionary.py              (imports <lang>/utils.py, clients.wiktionary)
<lang>/llm_forms.py               (imports form_registry, llm_forms_base)
<lang>/generate_*.py              (imports wordfreq.translation.generate_forms_tasks)

form_registry.py                  (imports form_patterns, llm_forms_base, enums;
                                   auto-discovers <lang>/forms_config.py)
llm_forms_base.py                 (imports clients, storage, util.prompt_loader)
storage/models/enums.py           (auto-discovers <lang>/forms_config.py via form_patterns)
```

## External library dependencies

| Library    | Used by | Purpose                              | Required? |
|------------|---------|--------------------------------------|-----------|
| pypinyin   | zh      | Pinyin with tone marks               | Optional  |
| jieba      | zh      | Chinese word segmentation            | Optional  |
| opencc     | zh      | Traditional/Simplified conversion    | Optional  |
| pykakasi   | ja      | Romaji and hiragana conversion       | Optional  |
| BeautifulSoup4 | en, de, es, fr, lt | Wiktionary HTML parsing | Required for parsers |

All CJK libraries degrade gracefully: functions return `None` or the
original text unchanged when the library is not installed.
