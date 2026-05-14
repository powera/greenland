# Language Module Format (Contract for `src/langtools/<lang>/`)

This document defines the **directory, module, and callable contract** each
language module should follow so top-level conditional/dynamic imports remain
stable.

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

## 2) Canonical top-level dispatcher signatures

These are the stable shared entrypoints in `src/langtools/*.py` that language
modules are expected to satisfy.

```python
# src/langtools/collation.py
# Covers Latin, Cyrillic, Brahmic, and Thai. CJK is handled by script-specific
# helpers in langtools/<lang>/ and is not dispatched here. All returned keys
# are plain ASCII so SQLite's default binary collation orders them correctly.

def generate_sort_key(lang_code: str, text: str) -> Optional[str]: ...
def generate_latin_sort_key(lang_code: str, text: str) -> Optional[str]: ...  # legacy alias

# src/langtools/letters.py

def get_letters(lang_code: str, *, uppercase: bool = True) -> Optional[List[str]]: ...

# src/langtools/directions.py

def get_language_direction_note(language_code: str) -> str: ...

# src/langtools/verb_forms.py

def get_language_verb_forms_config(language_code: str) -> Dict[str, Any]: ...

# src/langtools/noun_declensions.py

def get_mechanical_noun_decliner(language_code: str) -> Optional[DeclineFunc]: ...

# src/langtools/pronouns.py

def strip_pronoun_or_raise(language_code: str, text: str) -> str: ...
def strip_pronoun(language_code: str, text: str) -> str: ...

# src/langtools/grammatical_words.py

def is_grammatical_word(word: str, language_code: str) -> bool: ...
def is_function_word(word: str, language_code: str) -> bool: ...

# src/langtools/tokenizer.py

def tokenize(text: str, language_code: str) -> List[str]: ...
```

Notes:

- Some historical functions are language-first and some are `language_code`
  second; cleanup should converge toward language-first for new APIs.
- Language modules should preserve compatibility with current dispatchers until
  a coordinated API migration lands.

## 3) Standard file purposes + expected callable signatures

Use these filenames consistently across languages.

### `__init__.py`

- Marks the package.
- May re-export high-value functions/types.
- Should avoid heavy import side effects.

### `types.py`

- Holds typed models/enums/dataclasses used by the language implementation.
- Keep form-slot names and structured outputs here when language-specific.

### `forms_config.py` (optional but preferred)

Expected exports:

```python
# Pattern: declarative POS config constants consumed by form_registry.
# Names can vary, but values must be machine-readable by form_registry.

# Example shape (illustrative):
# FORM_CONFIGS: Dict[str, Dict[str, Any]]
```

- Declarative form-axis definitions for registry-based form generation.
- Consumed by `src/langtools/form_registry.py` pattern expansion.

### `llm_forms.py`

Expected callable patterns (language code replaced by actual `<lang>`):

```python
# Required generic adapter (preferred):
# def query_<lang>_forms(..., pos_type: str, ...) -> Dict[str, str]: ...

# Common explicit adapters (if used by call sites):
# def query_<lang>_noun_forms(...) -> Dict[str, str]: ...
# def query_<lang>_verb_forms(...) -> Dict[str, str]: ...
# def query_<lang>_adjective_forms(...) -> Dict[str, str]: ...
```

Contract expectations:

- Return normalized `Dict[str, str]` form slots for shared pipelines.
- Delegate shared schema/prompt/LLM mechanics to common infrastructure where
  possible.
- Keep function names stable once consumed by external call sites.

### `conjugation.py` (optional)

Expected callable pattern:

```python
# def mechanically_conjugate_<lang>_verb(lemma: str, ...) -> Optional[Dict[str, str]]: ...
```

- Deterministic verb conjugation logic for languages that support it.
- May be called directly by dispatcher or from `llm_forms.py` fast paths.

### `grammatical_words.py` (optional)

Expected exports:

```python
# PERSONAL_PRONOUNS: set[str] | frozenset[str]
# GRAMMATICAL_WORDS: set[str] | frozenset[str]
# FUNCTION_WORDS: set[str] | frozenset[str]
# NON_PERSONAL_PRONOUNS: set[str] | frozenset[str]
```

- Language-specific grammatical/function-word inventories used by shared
  classifier dispatchers.

### `directions.py` (optional)

Expected callable:

```python
def get_directions() -> str: ...
```

- Additional language notes/instructions used during prompt construction.

### `utils.py` (optional)

Expected optional callable for pronoun stripping compatibility:

```python
# def strip_pronoun(text: str) -> str: ...
```

- Language-local normalization/helpers that do not belong in shared modules.

### `tokenizer.py` (optional)

Expected callable:

```python
def tokenize(text: str) -> List[str]: ...
```

- Language-local tokenization behavior when shared tokenization is insufficient.

### `letters.py` (optional)

Expected exports:

```python
LETTERS_UPPER: List[str]  # alphabet in canonical dictionary order
```

- Used by ``langtools.letters.get_letters`` to power dictionary-view letter
  bars and similar UX (e.g. `/dictionary` in barsukas).
- For scripts without case distinction (CJK, Hangul, Thai, Devanagari, Tamil,
  Bengali, Kannada), ``LETTERS_UPPER`` simply holds the script's ordering set;
  the dispatcher does not lowercase it.
- Entries are *explicit* — not derived from `collation.py` — because dictionary
  bars need the user-visible letters (e.g. Spanish Ñ between N and O; Polish
  excludes Q V X; Chinese uses pinyin initials minus rare ones).
- Currently provided for tier 1–3 languages plus Turkish; absent languages
  default to plain A–Z at the call site.

### Script-specific helpers (optional)

- CJK and other script-heavy languages may include helpers like
  `pinyin_helper.py`, `romaji_helper.py`, `hangul_helper.py`, etc.

## 4) Dispatcher compatibility rules

Top-level `src/langtools/*.py` dispatchers rely on stable naming. To preserve
conditional imports and dynamic loading behavior:

1. Keep standard filenames unchanged (`llm_forms.py`, `types.py`, etc.).
2. Prefer additive changes over renames/removals.
3. When introducing a new capability, first define a shared dispatcher contract
   and then implement that capability file/function in each core language where
   meaningful.
4. If a language does not support a capability, leave the module absent or make
   the unsupported status explicit in that module (do not silently no-op).

## 5) Core callable surface (cross-language target)

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

## 6) Practical change checklist

When editing a language directory:

1. Keep/restore standard filenames.
2. Ensure imports used by top-level dispatchers still resolve.
3. Update `LANGUAGE_STATUS.md` for core languages when capability presence
   changes.
4. If adding a new shared contract, document it in `STRUCTURE.md` and this file.
