# Barsukas API quick reference

This file documents the main JSON endpoints under `src/barsukas/routes/api/v1.py` that are useful for automation/agents.

Base prefix: `/api`.

## Version + discovery

- `GET /api/v1`
  - Returns API version and endpoint descriptions.

## Search + lemma detail

- `GET /api/v1/search?q=<query>[&pos_type=...][&difficulty=...][&limit=...][&offset=...]`
  - Search lemmas by text/definition/translations.

- `GET /api/v1/lemmas/by-difficulty?difficulty=<level>[&pos_type=...][&missing_translation=<code>][&limit=...][&offset=...]`
  - List lemmas for one difficulty level without supplying a text query.
  - `missing_translation`: optional language code; when supplied, only returns lemmas where that translation is missing/empty.
    Each returned lemma then includes `translation_absence[code]`.
  - Lemma summaries include `lexical_gap_reason` when populated.

- `GET /api/v1/lemmas/translations?guids=<guid1,guid2,...>[&language=<code>]`
  - Fetch translations for multiple GUIDs in one call.
  - With `language=<code>`, omitted translations are described in
    `metadata.translation_absence[guid][code]`.
  - Marked translations are described in
    `metadata.translation_metadata[guid][code]`.

- `GET /api/v1/lemma/<guid>`
  - Basic lemma details.
  - Includes `lexical_gap_reason` for concepts that may not have conventional
    native lexical items in historical/classical languages.
- `POST /api/v1/lemma/<guid>` or `PATCH /api/v1/lemma/<guid>`
  - Update mutable lemma fields.
  - Body: `{"difficulty_level": <int|null>}`.

- `POST /api/v1/lemma/<main_guid>/merge-synonym/<synonym_guid>`
  - Merge the synonym lemma into the main lemma. Requires the same `pos_type` and at least 3 matching non-empty translations after normalization.
  - Adds the synonym lemma text/translations as per-language `synonym` derivative forms on the main lemma, tombstones `synonym_guid`, repoints sentence/audio references, and deletes the synonym lemma row.
  - Optional body: `{"changed_by": "...", "notes": "..."}`.

- `GET /api/v1/lemma/<guid>/translations[?language=<code>]`
  - Translations keyed by language code.
  - With `language=<code>`, a missing translation returns an empty `data` map
    and `metadata.translation_absence[code]` with:
    - `reason`: primary reason, one of `not_populated`, `excluded`, or `lexical_gap`
    - `reason_codes`: all applicable reasons
    - `effective_difficulty_level`: per-language override if present, otherwise
      the lemma difficulty
    - `difficulty_override`: present when a language-specific override exists
    - `lexical_gap_reason`: present when the lemma has one
  - Populated translations with status markers appear in
    `metadata.translation_metadata[code]`.

- `PATCH /api/v1/lemma/<guid>/translations/<language>/metadata`
  - Mark one populated translation with optional metadata.
  - Body: `{"translation_status": <string|null>, "translation_status_note": <string|null>}`.
  - `translation_status` may be one of `conventional`, `late_construction`,
    `modern_loan`, `descriptive`, or `uncertain`.
  - Use `late_construction` for useful learner cues that are not ordinary
    historical/native vocabulary, such as Neo-Latin terms or modern Sanskrit
    coinages.

- `GET /api/v1/lemma/<guid>/wordfreq`
  - Word frequency rollups nested by `language_code -> corpus_name -> {total_frequency, best_rank}`.
  - `total_frequency` is the corpus rollup value for the lemma lexeme; `best_rank` is the best (lowest) available form rank in that corpus.

- `GET /api/v1/lemma/<guid>/forms[?language=<code>]`
  - Derivative forms for a lemma.

- `GET /api/v1/lemma/<guid>/grammar[?language=<code>]`
  - Grammar facts.

- `GET /api/v1/lemma/<guid>/pronunciations[?language=<code>]`
  - Base-form IPA/phonetic pronunciations by language.

- `GET /api/v1/lemma/<guid>/audio[?language=<code>]`
  - Audio availability by language with `has_lemma_audio`, `form_audio_count`, and `audio_files` (includes `manifest_md5` and URL pointers).
- `GET /api/v1/audio/voices[?language=<code>]`
  - Lists voice options by backend for discovery before generation.
  - Response entries include: `voice_name`, `display_voice`, `backend`, `language_code`, `gender`, `sample_url`.

- `GET /api/v1/lemma/<guid>/sentences[?language=<code>]`
  - Example sentences using the lemma.


- `GET /api/v1/tasks/<task_id>`
  - Task status/result snapshot for queued background work.

- `GET /api/v1/sentences/<id>`
  - Full sentence payload including translations and `sentence_words` rows.

## Model registry

- `GET /api/v1/models[?q=<search>]`
  - List LLM models from the benchmarks database (requires postgres backend).
  - `q`: optional substring search across codename, displayname, model_path, lmstudio_model_name.
  - Returns array of `{codename, displayname, model_path, model_type, lmstudio_model_name, launch_date, license_name}`.
  - Returns HTTP 503 if benchmarks database is not configured.

## Agent task + LLM check endpoints (GUID-based)

All LLM-invoking endpoints below require JSON body with `"model": "<model-name>"`.

- `POST /api/v1/agents/lemma/<guid>/add-missing-translations`
- `POST /api/v1/agents/lemma/<guid>/generate-pronunciations` (optional `lang_code`)
- `POST /api/v1/agents/lemma/<guid>/generate-forms` (optional `lang_code`)
- `POST /api/v1/agents/lemma/<guid>/generate-synonyms` (optional `lang_code`)

- `POST /api/v1/agents/lemma/<guid>/check-definition`
- `POST /api/v1/agents/lemma/<guid>/check-disambiguation`
- `POST /api/v1/agents/lemma/<guid>/check-translations`
- `POST /api/v1/agents/lemma/<guid>/check-pronunciations`
- `POST /api/llm/<agent>/generate-audio`
  - Bulk lemma audio generation (currently supports `agent=vieversys` and `agent=strazdas`).
  - Body: `{"guids": [...], "language": "bs", "voice": "...", "include_forms": false, "force": false}`.

Check endpoints return:

- `data.status`: `"ok"` or `"issues_found"`
- `data.issues`: list of issues/suggestions
- `data.confidence_summary`: aggregate confidence/check metadata
- `metadata.guid`, `metadata.model`

## Metadata endpoints (for aggregate counting)

- `GET /api/v1/metadata/pos-subtypes[?pos_type=<type>]`
  - List distinct POS subtypes present in lemmas.
  - `pos_type`: optional exact POS filter (e.g. `noun`, `verb`).

- `GET /api/v1/metadata/levels/by-pos?pos_type=<type>&pos_subtype=<subtype>`
  - Return difficulty-level distribution for lemmas in one POS bucket.
  - Response `data` is a map of difficulty level string to count (uses `"null"` for unset levels).

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
