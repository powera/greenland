# Barsukas API quick reference

This file documents the main JSON endpoints under `src/barsukas/routes/api.py` that are useful for automation/agents.

Base prefix: `/api`.

## Version + discovery

- `GET /api/v1`
  - Returns API version and endpoint descriptions.

## Search + lemma detail

- `GET /api/v1/search?q=<query>[&pos_type=...][&difficulty=...][&limit=...][&offset=...]`
  - Search lemmas by text/definition/translations.

- `GET /api/v1/lemmas/by-difficulty?difficulty=<level>[&pos_type=...][&limit=...][&offset=...]`
  - List lemmas for one difficulty level without supplying a text query.

- `GET /api/v1/lemma/<guid>`
  - Basic lemma details.
- `POST /api/v1/lemma/<guid>` or `PATCH /api/v1/lemma/<guid>`
  - Update mutable lemma fields.
  - Body: `{"difficulty_level": <int|null>}`.

- `GET /api/v1/lemma/<guid>/translations[?language=<code>]`
  - Translations keyed by language code.

- `GET /api/v1/lemma/<guid>/forms[?language=<code>]`
  - Derivative forms for a lemma.

- `GET /api/v1/lemma/<guid>/grammar[?language=<code>]`
  - Grammar facts.

- `GET /api/v1/lemma/<guid>/pronunciations[?language=<code>]`
  - Base-form IPA/phonetic pronunciations by language.

- `GET /api/v1/lemma/<guid>/audio[?language=<code>]`
  - Audio availability by language with `has_lemma_audio`, `form_audio_count`, and `audio_files` (includes `manifest_md5` and URL pointers).

- `GET /api/v1/lemma/<guid>/sentences[?language=<code>]`
  - Example sentences using the lemma.

## Model registry

- `GET /api/v1/models[?q=<search>]`
  - List LLM models from the benchmarks database (requires postgres backend).
  - `q`: optional substring search across codename, displayname, model_path, lmstudio_model_name.
  - Returns array of `{codename, displayname, model_path, model_type, lmstudio_model_name, launch_date, license_name}`.
  - Returns HTTP 503 if benchmarks database is not configured.

## Metadata endpoints (for aggregate counting)

- `GET /api/v1/metadata/words[?language=<code>][&max_difficulty=<int>][&difficulty=<int>]`

Returns per-language aggregate counts with this shape:

- `total_words`
- `words_by_subtype`
- `audio.with_audio` / `audio.without_audio`
- `derivative_forms.with_derivative_forms` / `derivative_forms.without_derivative_forms`

### Word counting rules

- Language lemma universe:
  - `en`: lemmas with non-null `lemma_text`
  - non-`en`: lemmas with non-empty `lemma_translations.translation` in that language
- "with audio": lemma-level audio rows in `audio_quality_reviews` (`guid` set, `sentence_id` null, `grammatical_form` null)
- "with derivative forms": at least one `derivative_forms` row for that lemma in that language
- `max_difficulty`: if supplied, restricts to words whose effective difficulty
  (`COALESCE(lemma_difficulty_overrides.difficulty_level, lemma.difficulty_level)` for the
  requested language) is between 1 and `max_difficulty` inclusive (excludes -1 / NULL)
- `difficulty`: if supplied, restricts to words whose effective difficulty exactly equals
  that value

- `GET /api/v1/metadata/sentences[?language=<code>][&max_difficulty=<int>]`

Returns per-language aggregate counts with this shape:

- `total_sentences`
- `sentences_by_pattern`
- `audio.with_audio` / `audio.without_audio`
- `verification.verified` / `verification.unverified`

### Sentence counting rules

- Language sentence universe: sentences with non-empty `sentence_translations.translation_text` in that language
- "with audio": at least one sentence-level row in `audio_quality_reviews` (`sentence_id` set) for the same language
- "verified": `sentences.verified` among the language sentence universe
- `max_difficulty`: if supplied, restricts to sentences whose `minimum_level` is between
  1 and `max_difficulty` inclusive (excludes NULL / unset sentences)

## Pending imports

- `GET /pending-imports/api/duplicates`
  - Find pending imports that are duplicates of existing lemmas (direct match or form-of-lemma match).
  - Only checks imports where `definition == english_word` (not yet staged).
  - Each result has: pending import fields + `match_type` ("direct"/"form"), `matched_lemma_guid`, `matched_lemma_text`, `matched_pos_type`.

- `GET /pending-imports/api/list[?search=...][&pos_type=...][&pos_subtype=...][&source=...][&language=...][&page=N]`
  - List pending imports as JSON. Supports the same filters as the HTML list view.
  - Returns `{"data": [...], "metadata": {"total": N, "page": P, "total_pages": T}}`.
  - Each item: `id`, `english_word`, `definition`, `disambiguation_translation`, `disambiguation_language`, `pos_type`, `pos_subtype`, `example_sentence`, `source`, `frequency_rank`, `notes`, `added_at`.

## Response conventions

- Success: `{"data": ... , "metadata": ...}` (metadata optional)
- Error: `{"error": "..."}` with HTTP error status

## Notes for agent authors

- Prefer `/api/v1` and `/api/v1/metadata/words` for machine-friendly summaries.
- Use `language=<code>` to avoid downloading unnecessary multi-language payloads.
