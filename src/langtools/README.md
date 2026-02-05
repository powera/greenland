# Langtools - Language-Specific Text Processing

Language-specific tools for morphological analysis, Wiktionary parsing, and
sort-key generation, used by the Greenland linguistic database.

## Language Modules

### Western European (Wiktionary parsers)

Each of these modules provides a `Parser` class and convenience functions for
extracting word forms from Wiktionary data.

| Module | Language | Capabilities |
|--------|----------|--------------|
| `langtools.en` | English | Noun plurals, verb conjugations, adjective comparison, adverb forms |
| `langtools.de` | German | Noun declensions (with gender), verb conjugations, adjective declensions, adverb forms |
| `langtools.es` | Spanish | Noun forms, verb conjugations, adjective agreement |
| `langtools.fr` | French | Noun forms, verb conjugations, adjective agreement |
| `langtools.lt` | Lithuanian | Noun declensions, verb conjugations |

Each module contains:
- `types.py` - Pydantic models for word forms (NounDeclension, VerbConjugation, etc.)
- `utils.py` - Language-specific text utilities
- `wiktionary.py` - Wiktionary HTML parser

Example:
```python
from langtools.en.wiktionary import get_english_noun_forms

forms, success = get_english_noun_forms("mouse")
if success:
    print(forms.forms)  # {'singular': 'mouse', 'plural': 'mice'}
```

### CJK Languages

| Module | Language | Capabilities |
|--------|----------|--------------|
| `langtools.zh` | Chinese | Pinyin generation, simplified/traditional character conversion |
| `langtools.ja` | Japanese | Romaji conversion, Gojuon kana ordering |
| `langtools.ko` | Korean | Hangul syllable decomposition for sort keys |

### Collation (`langtools.collation`)

Generates locale-aware sort keys for Latin-alphabet languages, enabling correct
alphabetical ordering in SQLite's binary collation.

Two strategies:
- **Position remapping** (lt, es, sv, vi) - Remaps characters that are distinct
  letters in the language's alphabet (e.g., Lithuanian ą sorts after a, before b)
- **Diacritic stripping** (de, fr, it, pt) - Removes accents so accented characters
  sort with their base letter

```python
from langtools.collation import generate_latin_sort_key

generate_latin_sort_key("lt", "ąžuolas")  # correct Lithuanian ordering
generate_latin_sort_key("fr", "café")     # → "cafe"
```

CJK sort keys are handled by their respective modules (`zh`, `ja`, `ko`),
not by the collation module.
