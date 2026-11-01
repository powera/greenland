# Lithuanian vocabulary audio coverage — 2026-11-01

This is the baseline snapshot before the level 1–3 generation and historical
GUID/audio repair later that day; the CSV has the same baseline scope. Those
repairs restored 401 stranded audio references and selected the older Rūta
airport take. These counts should not be read as current post-repair coverage.

Read-only audit of the live local SQLite database and existing `lang_lt` WireWord export. No database changes, generation, uploads, or API calls were made. CDN availability could not be checked: network retrieval of sample asset manifests failed. Counts describe metadata, not listening-based pronunciation quality.

## Base vocabulary, effective Lithuanian levels 1–30

Scope uses `coalesce(lt difficulty override, base difficulty level)`, matching the exporter. All 996 entries have Lithuanian translations. Audio is matched by GUID, base slot, exact current translation, non-rejected status, nonempty MD5, and an upload URL.

- 619 entries (62.1%) have both Jonas and Rūta recordings and audio hashes in the existing export.
- 377 entries (37.9%) have no base audio review row at all; all 377 also lack base audio hashes in the export. No partial single-voice cases or stale/rejected cases were found in this scope.
- 116 entries have at least one production URL; 503 more have staging URLs only. All Lithuanian review rows are marked `pending_review`, including those with production URLs. Export references therefore do not establish review approval or production availability.
- The 377 missing entries contain 355 distinct spellings. 62 entries have identical text somewhere in the existing uploaded Lithuanian base-audio inventory; only 296 spellings are absent from that inventory. Reuse would need explicit matching and review: the current helper only shares recordings within a GUID, language, and voice.

| Levels | Entries | Missing base audio |
| --- | ---: | ---: |
| 1–5 | 189 | 26 |
| 6–10 | 173 | 50 |
| 11–15 | 160 | 54 |
| 16–20 | 167 | 84 |
| 21–25 | 161 | 81 |
| 26–30 | 146 | 82 |

Missing counts by level: 1:1, 2:6, 3:4, 4:2, 5:13, 6:15, 7:7, 8:3, 9:3, 10:22, 11:19, 12:4, 13:0, 14:20, 15:11, 16:1, 17:20, 18:25, 19:18, 20:20, 21:0, 22:31, 23:17, 24:20, 25:13, 26:23, 27:19, 28:12, 29:13, 30:15.

Early gaps: L1 airport (oro uostas); L2 train (traukinys), fork (šakutė), spoon (šaukštas), cup (puodelis), plate (lėkštė), bowl (dubuo); L3 afraid (išsigandęs), hungry (alkanas), and two senses of be (būti).

The largest subtype gaps are quality adjectives (27), physical-property adjectives (27), determiners (19), family relations (17), time periods (16), prepositions (15), and occupations (15). The data confirms broad coverage gaps; it does not establish that every missing item was newly added.

Full entry inventory: `20261101_lt_audio_coverage.csv`. `recorded_voices` includes staging or production; `prod_voices` requires production; `export_voices` describes the existing local export.

## Countries, nationalities, languages

Thirty entries with base levels 231–233 already have Lithuanian overrides to level 15: 11 countries, 11 nationalities/origin senses, and 8 language names. Their current export levels are also 15. Nineteen have audio; eleven lack it:

- United Kingdom — Jungtinė Karalystė
- British person — britas
- Australian — australas
- English — anglų kalba
- Lithuanian — lietuvių kalba
- Latvian — latvių kalba
- Estonian — estų kalba
- Polish — lenkų kalba
- German — vokiečių kalba
- French — prancūzų kalba
- Russian — rusų kalba

Another 179 entries remain at effective levels 231–233 (45 countries, 107 nationality/origin senses, 27 language names), outside this audit's generation scope. Their high levels alone do not establish an override bug; the curated rules deliberately retain a main geography inventory.

## Gender variants and inflections

There are 96 stored Lithuanian base gender-variant slots attached to these 996 entries; 49 differ from the lemma's base translation. There are no Lithuanian lemma audio rows with a non-null grammatical-form slot, including gender variants. Same-text base variants may reuse base audio at export, but the 49 different-text variants require separate coverage work. These are additional to the 377 base-entry gaps; no deduplicated combined generation estimate is claimed. General inflected-form audio is likewise absent from the review table; recording all paradigms would be a separate, much larger scope.

## How existing audio was generated

The 2,568 Lithuanian base audio rows are 1,284 Jonas + 1,284 Rūta, attributed to agent `vieversys`; 18 extra experimental base rows use alloy, ash, and nova (6 each). Sentence rows are excluded from these counts.

Git history immediately preceding the recorded August–September generation dates maps Jonas to `Voice.ASH` and Rūta to `Voice.NOVA`. The historical OpenAI client default is `gpt-4o-mini-tts-2025-12-15`. Together, agent attribution, character-voice names, dates, and historical code strongly indicate the main inventory came from OpenAI TTS, rather than OuteTTS. Per-file model provenance is stored in asset manifests, not in AudioQualityReview; the exact model cannot be independently established for every recording without retrieving those manifests. The presence of old OuteTTS wrapper scripts does not establish that they produced the current inventory.

The current code already defaults to `gpt-realtime-2.1-mini` and uses a WebSocket Realtime recording session, receives PCM, and encodes MP3. Jonas still maps to Ash; Rūta now maps to Coral, because Nova is absent from the Realtime voice allowlist. Existing character names therefore conceal a voice change, and even shared voice names do not prove acoustic continuity across models. The migration appears in commit `407495e7` on 2026-10-17. Transcript mismatch warnings and duration checks exist, but do not establish Lithuanian pronunciation accuracy.

Official OpenAI documentation recommends migration from the Speech endpoint to Realtime for this model: https://developers.openai.com/api/docs/guides/text-to-speech . Realtime voice documentation: https://developers.openai.com/api/docs/guides/realtime-conversations . The user's reported >10% error rate was not independently measured in this audit.

## Suggested next batch

1. Resolve whether exported staging-only hashes are actually served by the configured production audio prefix before calling 619 entries playable.
2. Preserve healthy existing recordings. Review same-text reuse candidates, then fill missing base words in ascending effective level, including the eleven L15 geography entries.
3. Include distinct stored base gender variants if “all words” means all displayed gender choices.
4. Use a small Lithuanian Realtime voice/quality pilot before a full fill, with results persisted through the ordinary pipeline; pay particular attention to Rūta's changed voice and pronunciation. Live generation requires explicit approval under AGENTS.md.
5. Review and publish the accepted recordings, then regenerate the export and verify asset accessibility. Filling 377 entries in two voices is 754 recording slots before reuse, gender variants, or retries.
