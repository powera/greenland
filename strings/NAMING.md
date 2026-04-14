# Barsukas STRINGS Naming Design (LSTR / SSTR / CSTR, namespace rules)

This is a design-only proposal for clearer string naming.

## Primary objective

Make it obvious whether a string is:
- short / lemma-like (`LSTR`)
- sentence-length (`SSTR`)
- long multi-sentence block (`CSTR`)

---

## Top-level buckets

- `LSTR` = short strings (single lemma/term/short phrase)
- `SSTR` = sentence-length strings
- `CSTR` = 3+ sentence text blocks

---

## LSTR namespace rules

For `LSTR`, namespace behavior is special:

1. **Default namespace is common**
   - `LSTR.<key_path>` means the value comes from common namespace.
   - Example: `LSTR.linguistics.verb`

2. **CURRENT for current page/module strings**
   - `LSTR.CURRENT.<key_path>`
   - Example: `LSTR.CURRENT.play_xylophone`

3. **OTHER for explicit cross-page references**
   - `LSTR.OTHER.<page_namespace>.<key_path>`
   - Example: `LSTR.OTHER.lemmas.search_placeholder`

### Interpretation summary

- `LSTR.foo.bar` → common (`common/foo/bar` conceptually)
- `LSTR.CURRENT.foo` → current page/module namespace
- `LSTR.OTHER.lemmas.foo` → explicitly from `lemmas` namespace

---

## SSTR / CSTR namespace rules

For sentences and long blocks, a namespace is always required.

- `SSTR.<namespace>.<key_path>`
- `CSTR.<namespace>.<key_path>`

Examples:
- `SSTR.lemmas.search_placeholder`
- `SSTR.sync.lemma.add_lemma_confirmation`
- `CSTR.sync.lemma.release_sync_intro`

No implicit `common` default for `SSTR`/`CSTR`.

---

## File/source mapping guidance

This proposal is naming-focused; implementation can map these paths to existing
JSON files however is most practical. Conceptually:

- `LSTR.<key_path>` resolves to shared/common files first
  - example source idea: `common/linguistics/*.json`
- `LSTR.CURRENT.*` resolves in-page namespace
- `LSTR.OTHER.<ns>.*` resolves that explicit namespace
- `SSTR.<ns>.*` and `CSTR.<ns>.*` resolve directly in namespace `<ns>`

---

## Naming conventions for keys

- Use explicit names (`part_of_speech_abbreviation`, `sort_order.alphabetical`)
- Avoid ambiguous short names in new keys (`pos`, `ipa`, `sort_alpha`)
- snake_case leaf keys

---

## Examples mapped to current concerns

### Common/shared short terms

- `LSTR.database`
- `LSTR.import`
- `LSTR.export`
- `LSTR.optional`
- `LSTR.linguistics.part_of_speech_abbreviation`

### Current page short strings

- `LSTR.CURRENT.play_xylophone`

### Cross-page short-string reuse

- `LSTR.OTHER.lemmas.search_placeholder`

### Sentence-level strings

- `SSTR.lemmas.search_placeholder`
- `SSTR.sentence.empty.no_results`
- `SSTR.sync.lemma.add_lemma_confirmation`

### Long text blocks

- `CSTR.sync.lemma.release_sync_intro`

---

## Migration approach (incremental)

1. Introduce `LSTR/SSTR/CSTR` helpers while keeping existing `STRINGS` lookups.
2. Add compatibility mapping from new symbolic paths to existing JSON locations.
3. Migrate high-traffic templates first.
4. Add validation rules:
   - `LSTR` allows implicit common + `CURRENT` + `OTHER`
   - `SSTR`/`CSTR` require explicit namespace
   - disallow new ambiguous keys (`pos`, `ipa`, `sort_alpha`)
5. Remove compatibility aliases after deprecation window.

---

## Decision summary

Use:
- `LSTR.<key_path>` as common default
- `LSTR.CURRENT.<key_path>` for current page namespace
- `LSTR.OTHER.<ns>.<key_path>` for explicit cross-page lookup
- `SSTR.<ns>.<key_path>` (namespace required)
- `CSTR.<ns>.<key_path>` (namespace required)

This preserves concise access for common terms while making sentence/long-text ownership explicit.
