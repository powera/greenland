# Langtools Architecture

## Directory layout

```
langtools/
├── __init__.py              # Package exports and docstring
├── collation.py             # Shared Latin-alphabet sort-key generation
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
└── Partial Western European modules
    │  (types and LLM forms only; no Wiktionary parser)
    ├── it/                  # Italian   (types + llm_forms)
    ├── nl/                  # Dutch     (types + llm_forms)
    ├── pt/                  # Portuguese (types + llm_forms + generate scripts)
    └── sv/                  # Swedish   (types + llm_forms)
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

Form complexity varies by language:

| Language   | Noun forms | Verb forms | Adjective forms | Adverb forms |
|------------|------------|------------|-----------------|--------------|
| English    | 2          | 5 base / 22 full | 3          | 3            |
| German     | 8 (4 cases x 2 numbers) | 18 | varies    | 3            |
| Spanish    | 2 + gender | 6+ per tense | agreement  | --           |
| French     | 2 + gender | 6+ per tense | agreement  | --           |
| Lithuanian | 14 (7 cases x 2 numbers) | 18 | 28 (7 cases x 2 numbers x 2 genders) | 3 |

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
| Portuguese | yes   | yes   | --         | --      |

## collation.py -- Shared sort-key generation

Produces binary-sortable strings so that SQLite's default binary collation
gives linguistically correct alphabetical ordering.  Two strategies:

**Position remapping** (lt, es, sv, vi): Characters that are distinct
letters in the language's alphabet are mapped to sort in the right position.
For example, Lithuanian ą sorts after a but before b, encoded as `a{`.

**Diacritic stripping** (de, fr, it, nl, pt): Accented characters are not
separate letters; accents are removed via Unicode NFD decomposition so
that `café` sorts as `cafe`.

CJK sort keys are handled by the respective language modules (ja, ko, zh),
not by collation.py.

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

zh/converter.py                   (standalone, uses opencc)
zh/pinyin_helper.py               (imports zh/converter.py, uses pypinyin + jieba)

ja/romaji_helper.py               (standalone, uses pykakasi)
ja/gojuon.py                      (standalone, pure data)

ko/hangul_helper.py               (standalone, pure Unicode arithmetic)

<lang>/types.py                   (imports clients.wiktionary.types)
<lang>/utils.py                   (imports <lang>/types.py)
<lang>/wiktionary.py              (imports <lang>/utils.py, clients.wiktionary)
<lang>/llm_forms.py               (imports clients, wordfreq.storage, util.prompt_loader)
<lang>/generate_*.py              (imports wordfreq.translation.generate_forms_tasks)
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
