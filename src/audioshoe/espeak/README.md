# eSpeak-NG Audio Generation

This module provides text-to-speech audio generation using eSpeak-NG, an open-source speech synthesizer.

## Overview

The eSpeak-NG integration allows generating audio files for lemmas without requiring API calls to external services like OpenAI. This is useful for:

- Cost-free audio generation
- Offline audio generation
- Rapid prototyping and testing
- Languages where OpenAI TTS may have limitations

## Components

### `espeak_tts.py`

Main TTS client that interfaces with the eSpeak-NG command-line tool.

**Key Features:**
- Supports all languages in the project: Lithuanian, Chinese, Korean, French, German, Spanish, Portuguese, Swahili, Vietnamese
- Voice variant mapping (maps OpenAI Voice enum to eSpeak variants)
- IPA phonetic input support
- Automatic WAV to MP3 conversion (requires ffmpeg)
- Configurable speech speed and pitch

**Usage:**
```python
from audioshoe.espeak import generate_audio
from clients.audio import Voice, AudioFormat

result = generate_audio(
    text="labas",
    voice=Voice.ASH,
    language_code="lt",
    audio_format=AudioFormat.MP3,
    speed=150,  # words per minute
    pitch=50,   # 0-99
)

if result.success:
    # Save audio
    with open("output.mp3", "wb") as f:
        f.write(result.audio_data)
```

### Agent: `strazdas.py`

Batch audio generation agent for processing multiple lemmas using eSpeak-NG.

"Strazdas" means "thrush" in Lithuanian - a songbird known for its melodious voice.

**Usage:**
```bash
# Generate audio for Lithuanian lemmas
python -m agents.strazdas --language lt --limit 10

# Use IPA phonetic notation (when available)
python -m agents.strazdas --language lt --use-ipa

# Specify voices
python -m agents.strazdas --language fr --voices ash alloy nova

# Filter by difficulty level
python -m agents.strazdas --language zh --difficulty-level 5
```

## Prerequisites

### eSpeak-NG Installation

**Ubuntu/Debian:**
```bash
sudo apt-get install espeak-ng
```

**macOS:**
```bash
brew install espeak-ng
```

**Verify Installation:**
```bash
espeak-ng --version
espeak-ng --voices
```

### Optional: ffmpeg (for MP3 output)

The module generates WAV files by default. To automatically convert to MP3, install ffmpeg:

**Ubuntu/Debian:**
```bash
sudo apt-get install ffmpeg
```

**macOS:**
```bash
brew install ffmpeg
```

If ffmpeg is not available, the module will return WAV format even when MP3 is requested.

## Language Voice Codes

The following language codes are supported:

| Language   | Code | eSpeak Voice |
|------------|------|--------------|
| Lithuanian | lt   | lt           |
| Chinese    | zh   | zh (Mandarin)|
| Korean     | ko   | ko           |
| French     | fr   | fr           |
| German     | de   | de           |
| Spanish    | es   | es           |
| Portuguese | pt   | pt           |
| Swahili    | sw   | sw           |
| Vietnamese | vi   | vi           |

## Voice Variants

eSpeak-NG supports voice variants which provide different pitch/tone characteristics. The OpenAI Voice enum is mapped to numeric variants (1-7):

| OpenAI Voice | eSpeak Variant |
|--------------|----------------|
| ALLOY        | 1              |
| ASH          | 2              |
| BALLAD       | 3              |
| CORAL        | 4              |
| ECHO         | 5              |
| FABLE        | 6              |
| NOVA         | 7              |

The actual voice used is specified as `{language}+{variant}`, e.g., `lt+2` for Lithuanian with variant 2.

## Barsukas Integration

The eSpeak-NG engine is integrated into the Barsukas web interface:

1. Navigate to `/audio/generate`
2. Select "espeak-ng" as the TTS engine
3. Choose language, voices, and other parameters
4. Optionally enable "Use IPA" for phonetic generation
5. Submit to generate audio files

Generated files are stored in `AUDIO_BASE_DIR` with the voice name prefixed by "espeak-" (e.g., `espeak-ash`, `espeak-alloy`) to distinguish them from OpenAI-generated files.

## IPA Support

If lemmas have IPA (International Phonetic Alphabet) transcriptions, you can use them for audio generation:

```python
result = agent.generate_audio_for_lemma(
    session, lemma, language_code, voices,
    create_review_record=True,
    use_ipa=True  # Use IPA if available
)
```

This allows for more precise phonetic control over the generated audio.

## Performance Considerations

- eSpeak-NG is very fast (typically < 1 second per word)
- No API rate limits or costs
- Can process thousands of lemmas quickly
- Quality is lower than commercial TTS but acceptable for many use cases

## Troubleshooting

**Error: "eSpeak-NG not found"**
- Install espeak-ng using the instructions above
- If installed in a non-standard location, specify the path:
  ```python
  client = EspeakNGClient(espeak_command="/path/to/espeak-ng")
  ```

**Warning: "ffmpeg not found. Returning WAV format instead."**
- Install ffmpeg for MP3 conversion support
- Or use `audio_format=AudioFormat.WAV` to avoid the warning

**Audio quality issues:**
- Adjust speed: `speed=175` (default), range 80-450
- Adjust pitch: `pitch=50` (default), range 0-99
- Try different voice variants

## References

- [eSpeak-NG GitHub](https://github.com/espeak-ng/espeak-ng)
- [eSpeak-NG Documentation](https://github.com/espeak-ng/espeak-ng/blob/master/docs/guide.md)
- [eSpeak-NG Voices Documentation](https://github.com/espeak-ng/espeak-ng/blob/master/docs/voices.md)
