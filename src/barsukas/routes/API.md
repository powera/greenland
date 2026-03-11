# Barsukas API quick reference

This file documents the main JSON endpoints under `src/barsukas/routes/api.py` that are useful for automation/agents.

Base prefix: `/api`.

## Version + discovery

- `GET /api/v1`
  - Returns API version and endpoint descriptions.

## Search + lemma detail

- `GET /api/v1/search?q=<query>[&pos_type=...][&difficulty=...][&limit=...][&offset=...]`
  - Search lemmas by text/definition/translations.

- `GET /api/v1/lemma/<guid>`
  - Basic lemma details.

- `GET /api/v1/lemma/<guid>/translations[?language=<code>]`
  - Translations keyed by language code.

- `GET /api/v1/lemma/<guid>/forms[?language=<code>]`
  - Derivative forms for a lemma.

- `GET /api/v1/lemma/<guid>/grammar[?language=<code>]`
  - Grammar facts.

- `GET /api/v1/lemma/<guid>/pronunciations[?language=<code>]`
  - Base-form IPA/phonetic pronunciations by language.

- `GET /api/v1/lemma/<guid>/sentences[?language=<code>]`
  - Example sentences using the lemma.

## Metadata endpoint (for aggregate counting)

- `GET /api/v1/metadata/words[?language=<code>]`

Returns per-language aggregate counts with this shape:

- `total_words`
- `words_by_subtype`
- `audio.with_audio` / `audio.without_audio`
- `derivative_forms.with_derivative_forms` / `derivative_forms.without_derivative_forms`

### Counting rules

- Language lemma universe:
  - `en`: lemmas with non-null `lemma_text`
  - non-`en`: lemmas with non-empty `lemma_translations.translation` in that language
- "with audio": lemma-level audio rows in `audio_quality_reviews` (`guid` set, `sentence_id` null, `grammatical_form` null)
- "with derivative forms": at least one `derivative_forms` row for that lemma in that language

## Response conventions

- Success: `{"data": ... , "metadata": ...}` (metadata optional)
- Error: `{"error": "..."}` with HTTP error status

## Notes for agent authors

- Prefer `/api/v1` and `/api/v1/metadata/words` for machine-friendly summaries.
- Use `language=<code>` to avoid downloading unnecessary multi-language payloads.
