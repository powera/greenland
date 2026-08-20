# audiotools

Audio generation tools for Greenland Mint. Generates TTS audio (OpenAI,
OuteTTS) for language-learning flashcards and uploads the artifacts to S3.

This is the production audio-generation pipeline. The acoustic-analysis and
segmenter-research tooling (`qualityreview/`, `stirna.py`, the `gen_*_samples.py`
calibration generators, and `do-automation/`) remains in the separate
`audio/` submodule (github.com/powera/audiotools).

Run these as ordinary modules with the project's `PYTHONPATH`:

    PYTHONPATH=src python src/audiotools/gen_lithuanian_word_audio.py --help

## Top-level Python files

### `audio_checker.py`
LLM-based audio content checker. Sends WAV/MP3 files to an OpenAI
audio-aware model (`gpt-4o-mini-audio-preview`) and asks whether the
intended word is actually present and whether there are artifacts like
breaths. Returns a structured `AudioCheckResult` with confidence scores.
Also consumed by `qualityreview/batch_review.py` in the `audio/` submodule
as the "second opinion" alongside librosa-based analysis.

### `config.py`
Static configuration for the audio-checker library. Model name, API-key
path, request timeout/retries, supported audio formats, max file size,
default language, and thresholds (temperature, confidence, batch size).
No runtime logic.

### `file_utils.py`
Small file helpers shared by the generation CLIs: reading a word list one
per line, and creating an output directory. Nothing audio- or
language-specific. The Lithuanian pieces that used to live alongside these
now sit where they belong -- `sanitize_lithuanian_word` and
`LITHUANIAN_CHARS` in `langtools.lt.utils` (the charset derived from
`langtools/lt/letters.py` rather than restated), the TTS instructions in
`prompts/audio/word/lt.txt` behind
`clients.audio.openai_tts.get_instructions`, and key loading in
`clients.keys`.

### `gen_lithuanian_word_audio.py`
Primary CLI for generating Lithuanian pronunciation audio via OpenAI TTS.
Accepts a single word (`--word`) or a batch file (`--batch words.txt`),
supports all eight OpenAI voices, multi-voice generation with per-voice
output folders (`--organize-by-voice`), configurable speed, and `--force`
overwrite. Output lands in a cache directory served by the Atacama webapp.

### `generate_json_audio.py`
Convenience wrapper around `genaudio_outetts.py` for bulk Lithuanian audio
from a JSON-of-sentences format. JSON contains `english`, `lithuanian`,
and required `filename` per item. Supports generating audio across
multiple speakers in one pass and optionally uploading to a remote server.

### `manifest_rebuild.py`
Rebuilds an `audio_manifest.json` for a directory of already-generated MP3s
by scanning the files themselves -- no database involved. Recovers a
manifest from whatever is on disk, deriving each entry's GUID and text from
the filename convention. Distinct from
`clients.audio.manifest.generate_manifest`, which builds a manifest for a
single freshly generated file from metadata the caller already holds: use
that one when generating, this one when reconstructing after the fact.

### `review_records.py`
Shared helpers for the `AudioQualityReview` table. `find_existing_review`
performs the lookup mirroring both unique constraints -- notably the lemma
one, whose NULL `grammatical_form` SQL will not catch, so a missed lookup
silently duplicates rows rather than raising. `clear_review_verdict` drops a
stale human judgement from a row being pointed at new audio. Used by
`agents.gandras`, `agents.vieversys`, and `workqueue.handlers.vieversys`,
each of which previously carried its own copy.

### `s3_ops.py`
Agent-local S3 helpers for the staging bucket -- listing staged manifests,
fetching them, and uploading audio. Each helper takes the uploader as an
argument rather than reaching for a singleton, so tests can pass a double
(see the credential guard in `clients.keys`).

### `staging_manifest.py`
Parses the JSON manifest an agent writes to S3 beside each MP3
(`ManifestEntry`) and decides which database row it describes
(`match_manifest_to_database`, returning a `MatchResult`). Matching goes by
GUID for lemmas or `sentence_id` for sentences, then compares the manifest
text against the stored translation; `require_text_match=False` imports a
mismatch anyway but still warns. Distinct from `manifest_rebuild.py`, which
reconstructs a manifest from filenames on disk.

### `upload_to_s3.py`
Uploads files from `../wireword-audio/` to Digital Ocean Spaces
(S3-compatible). Filenames are rewritten to MD5 hashes so CDN caches
invalidate correctly when content changes. Accepts `--language`,
`--voice` (repeatable) or `--all-voices`, and `--dry-run`.

### `wireword_audio.py`
Multi-language batch TTS for the "wireword" language-learning content
(Chinese, Korean, French, Lithuanian). Reads wireword JSON files, calls
OpenAI TTS per entry, writes into a per-language/per-voice cache, and
emits a manifest the review tools consume.

## Directories

- `scripts/` — shell wrappers: `oneword_audio.sh`, `copy_audio_cache.sh`,
  `runall.sh`.
- `outetts/` — legacy OuteTTS integration. The speaker voice JSONs it loads
  are not checked in here; they live in the `audio/` submodule under
  `outetts/outetts_voices/`. Set `OUTETTS_VOICES_DIR` to point at them.
  OuteTTS is deprioritized in favor of the OpenAI path in `gen_lithuanian_word_audio.py`.
