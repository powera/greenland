# Strings layout

This repository stores UI translation strings in JSON files under namespaced folders.

## Directory structure

- `strings/barsukas/<namespace>/en.json`
- `strings/barsukas/<namespace>/lt.json`

Each `<namespace>` groups related keys (for example: `navigation`, `pagination`, `dictionary`, `lemmas`, `rhymes`, `languages`, `common`, `linguistics`).

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

## Fallback behavior

- UI language is selected from supported languages (`en`, `lt`).
- If a namespace file is missing for the selected UI language, Barsukas falls back to `en.json` for that namespace.
