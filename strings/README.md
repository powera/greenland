# Strings layout

This repository stores UI translation strings in JSON files under namespaced folders.

## Directory structure

- `strings/barsukas/<namespace>/en.json`
- `strings/barsukas/<namespace>/lt.json`
- `strings/barsukas/cstr/<namespace>/en.json`
- `strings/barsukas/cstr/<namespace>/lt.json`

Each `<namespace>` groups related keys (for example: `navigation`, `dictionary`, `lemmas`, `rhymes`, `languages`, `common`).
Nested namespaces are supported using subdirectories, such as:

- `strings/barsukas/common/pagination/en.json` → `common.pagination`
- `strings/barsukas/common/linguistics/en.json` → `common.linguistics`
- `strings/barsukas/cstr/ipa/en.json` → `CSTR.ipa.*`

Current convention: keep shared namespaces at two components (for example,
`common.pagination`, `common.linguistics`).

## Namespace scope (shared vs module-specific)

Use shared namespaces across multiple pages/modules, and keep module-specific
namespaces isolated to their own views.

### Shared namespaces (cross-module)

- `strings/barsukas/common/en.json`
- `strings/barsukas/common/lt.json`
- `strings/barsukas/common/linguistics/en.json`
- `strings/barsukas/common/linguistics/lt.json`
- `strings/barsukas/navigation/en.json`
- `strings/barsukas/navigation/lt.json`
- `strings/barsukas/common/pagination/en.json`
- `strings/barsukas/common/pagination/lt.json`
- `strings/barsukas/languages/en.json`
- `strings/barsukas/languages/lt.json`

### Module-specific namespaces

- `strings/barsukas/lemmas/en.json`
- `strings/barsukas/lemmas/lt.json`
- `strings/barsukas/rhymes/en.json`
- `strings/barsukas/rhymes/lt.json`
- `strings/barsukas/dictionary/en.json`
- `strings/barsukas/dictionary/lt.json`

Rule of thumb: pages should use shared namespaces for generic labels, but avoid
importing another module's namespace (for example, `lemmas` should not use
`rhymes` keys).

## Key naming conventions

To make key intent obvious in templates, use prefixes:

- `token_*` for single words/tokens (`token_import`, `token_optional`)
- `label_*` for form/table labels and short UI phrases (`label_part_of_speech`)
- `message_*` for full-sentence user-facing messages and confirmations
- `abbreviation_*` for acronym-style labels (`abbreviation_international_phonetic_alphabet`)

When creating new keys, prefer descriptive names over short jargon-heavy names.
For example, use `label_part_of_speech` instead of `pos`.

## File format

- Files are UTF-8 JSON objects.
- Keys are stable identifiers used in templates.
- Values are localized strings.
- Prefer static labels for counts, and render the number separately in templates to avoid plural grammar issues.

Example:

```json
{
  "entries_count": "Entries"
}
```

## Template usage

Barsukas loads all namespaces into a global `STRINGS` object for templates.

- Access a namespace with dot syntax: `STRINGS.dictionary.title`
- Access dynamic keys with `.get(...)` when needed.
- For counts, keep text and number as separate template blocks:
  - `{{ STRINGS.dictionary.entries_count }}: {{ total }}`
- New forward-looking accessors are also available:
  - `LSTR` for short labels/terms (with `CURRENT`/`OTHER` support)
  - `SSTR` for sentence-level strings with explicit namespaces
  - `CSTR` for multi-sentence blocks with explicit namespaces (loaded only from `strings/barsukas/cstr/*`)

Canonical examples:

- `{{ LSTR.linguistics.verb }}`
- `{{ SSTR.lemmas.no_results }}`
- `{{ CSTR.ipa.intro_block|safe }}`

`CSTR` has no implicit `common` fallback and must be addressed as `CSTR.<namespace>.<key>`.

## CSTR migration rules

When converting multiple sentence keys into one long block:

1. Create the new key in `strings/barsukas/cstr/<namespace>/{en,lt}.json`.
2. Keep the key module-local (`<namespace>`), do not move it to `common`.
3. Update templates to use only `CSTR.<namespace>.<key>` for that block.
4. Remove the old sentence keys from `strings/barsukas/<namespace>/{en,lt}.json` once migrated.

Example migration (`ipa_reference.html`):

- Before: `intro_line_1` … `intro_line_4` in `strings/barsukas/ipa/*.json`
- After: `intro_block` in `strings/barsukas/cstr/ipa/*.json` and template call `CSTR.ipa.intro_block`

## Fallback behavior

- UI language is selected from supported languages (`en`, `lt`).
- If a namespace file is missing for the selected UI language, Barsukas falls back to `en.json` for that namespace.
