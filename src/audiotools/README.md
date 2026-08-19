# audiotools

Audio generation tools for Greenland Mint. Generates TTS audio (OpenAI,
OuteTTS) for language-learning flashcards and uploads the artifacts to S3.

This is the production audio-generation pipeline. The acoustic-analysis and
segmenter-research tooling (`qualityreview/`, `stirna.py`, the `gen_*_samples.py`
calibration generators, and `do-automation/`) remains in the separate
`audio/` submodule (github.com/powera/audiotools).

Run these as ordinary modules with the project's `PYTHONPATH`:

    PYTHONPATH=src python src/audiotools/gen_audio.py --help

## Top-level Python files

### `audio_checker.py`
LLM-based audio content checker. Sends WAV/MP3 files to an OpenAI
audio-aware model (`gpt-4o-mini-audio-preview`) and asks whether the
intended word is actually present and whether there are artifacts like
breaths. Returns a structured `AudioCheckResult` with confidence scores.
Also consumed by `qualityreview/batch_review.py` in the `audio/` submodule
as the "second opinion" alongside librosa-based analysis.

### `audio_utils.py`
Shared utilities for the Lithuanian TTS pipeline. Defines the Lithuanian
alphabet (`LITHUANIAN_CHARS`), diacritic-aware normalization, and the
`LITHUANIAN_TTS_INSTRUCTIONS` prompt that gets threaded into OpenAI calls
to coax better pronunciation of length/stress patterns. Imported by
`gen_audio.py` and the legacy `genaudio_outetts.py`.

### `config.py`
Static configuration for the audio-checker library. Model name, API-key
path, request timeout/retries, supported audio formats, max file size,
default language, and thresholds (temperature, confidence, batch size).
No runtime logic.

### `gen_audio.py`
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
  OuteTTS is deprioritized in favor of the OpenAI path in `gen_audio.py`.
