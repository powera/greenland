# audioshoe

Text-to-speech (TTS) audio generation with support for multiple engines.
Used to generate word and sentence audio for the Trakaido app.

## Layout

- `coqui/` — Coqui TTS (neural synthesis, voice cloning)
- `piper/` — Piper TTS (lightweight local inference)
- `espeak/` — eSpeak-NG CLI wrapper (phonetic synthesis)
- `qwen/` — Qwen TTS integration
- `driver.py`, `sample_driver.py` — Whisper speech-to-text drivers for audio
  regression testing
- `split_file.py` — audio segmentation and transcription utilities

Each engine subdirectory has its own README with setup and usage details.
Audio generation is normally driven by the `strazdas` and `vieversys` agents
(see `src/agents/README.md`).
