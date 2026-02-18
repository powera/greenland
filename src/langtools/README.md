# Langtools

Language-specific text-processing tools used by the Greenland multilingual
linguistic database.  The package handles three broad tasks:

1. **Figuring out word forms** -- given a dictionary word like "mouse" or
   "gehen", produce all the inflected forms a language learner needs to know
   (plurals, conjugations, declensions, comparatives, etc.).

2. **Romanizing non-Latin scripts** -- converting Chinese, Japanese, and
   Korean text into Latin-alphabet readings (pinyin, romaji) so learners
   can see how words are pronounced.

3. **Sorting words correctly** -- generating sort keys so that words appear
   in the right alphabetical order for each language, even when the
   language's alphabet differs from plain Unicode ordering.

## What each tool does

### Word-form extraction (Western European languages)

For English, German, Spanish, French, and Lithuanian, langtools can look up
a word on Wiktionary and pull out all its grammatical forms automatically.
For example, give it the English verb "swim" and it returns "swims",
"swam", "swum", "swimming".  Give it the Lithuanian noun "namas" and it
returns all 14 case forms (nominative, genitive, dative, etc. in both
singular and plural).

When Wiktionary doesn't have the data, or for languages without a
Wiktionary parser (Italian, Dutch, Portuguese, Swedish), the tools can
ask an LLM (like ChatGPT or Claude) to generate the forms instead.

Each language module knows what forms matter for that language:

- **English:** singular/plural for nouns, five principal parts for verbs
  (walk/walks/walked/walked/walking), and comparative forms for
  adjectives and adverbs (big/bigger/biggest).

- **German:** four-case declensions for nouns (with gender: der/die/das),
  conjugations across present/past/future for verbs, and comparison forms
  for adjectives and adverbs.

- **Spanish and French:** singular/plural with gender for nouns,
  full verb conjugation tables, and adjective agreement forms.

- **Lithuanian:** the most complex -- seven cases times two numbers
  (14 forms) for nouns, 28 forms for adjectives (adding masculine/feminine),
  18 verb conjugations, and adverb comparatives.

- **Italian, Dutch, Portuguese, Swedish:** form definitions and LLM-based
  generation, but no Wiktionary parser yet.

### Chinese tools

- **Pinyin generation:** converts Chinese characters into pinyin with tone
  marks (e.g. "你好" becomes "nǐ hǎo").  Uses word segmentation to handle
  characters that are pronounced differently depending on context.

- **Ruby HTML:** produces HTML where pinyin appears above each Chinese word,
  the way furigana works in Japanese textbooks.

- **Character conversion:** converts between Traditional and Simplified
  Chinese (e.g. "傳統" to "传统" and back).

### Japanese tools

- **Romaji generation:** converts Japanese text (kanji, hiragana, katakana)
  into Hepburn romanization (e.g. "東京" becomes "toukyou").

- **Hiragana readings:** converts kanji to hiragana, used for generating
  dictionary sort keys.

- **Ruby HTML:** produces HTML with romaji displayed above Japanese text.

- **Gojuon tables:** the standard Japanese syllabary ordering
  (あ, い, う, え, お, か, き, ...) used to build alphabet navigation bars
  in the web interface.

### Korean tools

- **Hangul decomposition:** breaks composed Hangul syllables into their
  consonant and vowel components (e.g. "한" becomes "ㅎㅏㄴ").  This
  produces sort keys that match the standard Korean dictionary order.
  No external libraries needed -- it's pure Unicode math.

### Alphabetical sorting (collation)

Different languages put letters in different orders.  Lithuanian treats
"ą" as a separate letter that comes after "a" but before "b".  Swedish
puts "å", "ä", "ö" at the end of the alphabet after "z".  French treats
"é" as the same letter as "e" for sorting purposes.

The collation module generates sort keys that make SQLite's simple binary
comparison produce the right ordering for each language.  Two strategies
are used depending on whether accented characters are separate letters
(position remapping) or just decorated versions of base letters (diacritic
stripping).


### Prompt direction hints

Langtools now includes optional per-language prompt direction notes used by shared
word-generation helpers.

- `langtools/directions.py` provides `get_language_direction_note(language_code)`
  and dynamically resolves `langtools.<code>.directions`.
- `langtools/ko/directions.py` adds a Korean note requiring Hangul output.
- `langtools/zh/directions.py` adds a Chinese note requiring Simplified/Mainland output.

## Quick examples

```python
# Get English noun forms from Wiktionary
from langtools.en.wiktionary import get_english_noun_forms
forms, ok = get_english_noun_forms("mouse")
# forms.forms == {'singular': 'mouse', 'plural': 'mice'}

# Generate pinyin for Chinese text
from langtools.zh.pinyin_helper import generate_pinyin
generate_pinyin("你好")  # "nǐ hǎo"

# Generate a Lithuanian sort key
from langtools.collation import generate_latin_sort_key
generate_latin_sort_key("lt", "ąžuolas")  # sorts after "a..." but before "b..."

# Decompose Korean for dictionary sorting
from langtools.ko.hangul_helper import decompose_hangul
decompose_hangul("바나나")  # "ㅂㅏㄴㅏㄴㅏ"

# Convert Japanese to romaji
from langtools.ja.romaji_helper import generate_romaji
generate_romaji("東京")  # "toukyou"
```

## Running form generation

Form generation is driven by the task registry in
`wordfreq.translation.generate_forms_tasks`.  Use
`run_form_generation_task(task_key)` with keys like `"english_nouns"`,
`"german_verbs"`, or `"lithuanian_adjectives"`.  Available task keys
are listed in `FORM_GENERATION_TASKS`.

See [STRUCTURE.md](STRUCTURE.md) for the full architecture reference,
including the file layout within each language module, the dependency
graph, and external library requirements.
