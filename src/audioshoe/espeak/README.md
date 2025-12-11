# eSpeak-NG Audio Generation

This module provides text-to-speech audio generation using eSpeak-NG, an open-source speech synthesizer.

**Language documentation:** https://github.com/espeak-ng/espeak-ng/blob/master/docs/languages.md

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
- Culturally appropriate voice names with gender variants
- IPA phonetic input support
- Automatic WAV to MP3 conversion (requires ffmpeg)
- Configurable speech speed and pitch

**Usage:**
```python
from audioshoe.espeak import generate_audio, EspeakVoice

result = generate_audio(
    text="labas",
    voice=EspeakVoice.ONA,  # Lithuanian female voice
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
# List available voices
python -m agents.strazdas --list-voices

# Generate audio for Lithuanian lemmas with specific voices
python -m agents.strazdas --language lt --voices Ona Jonas Ruta Tomas --limit 10

# Use IPA phonetic notation (when available)
python -m agents.strazdas --language lt --use-ipa

# Generate with default voices for French
python -m agents.strazdas --language fr --limit 20

# Filter by difficulty level
python -m agents.strazdas --language zh --difficulty-level 5
```

## Available Voices

Each language has **four** culturally appropriate voice names with balanced gender representation (2 female, 2 male):

### Lithuanian (lt)
- **Ona** - Female, variant 1
- **Jonas** - Male, variant 1
- **Ruta** - Female, variant 2
- **Tomas** - Male, variant 2

### Chinese / Mandarin (zh)
- **Mei** - Female, variant 1
- **Wei** - Male, variant 1
- **Ling** - Female, variant 2
- **Jun** - Male, variant 2

### Korean (ko)
- **Minji** - Female, variant 1
- **Joon** - Male, variant 1
- **Sora** - Female, variant 2
- **Minsu** - Male, variant 2

### French (fr)
- **Claire** - Female, variant 1
- **Pierre** - Male, variant 1
- **Marie** - Female, variant 2
- **Luc** - Male, variant 2

### German (de)
- **Anna** - Female, variant 1
- **Hans** - Male, variant 1
- **Greta** - Female, variant 2
- **Karl** - Male, variant 2

### Spanish (es)
- **Sofia** - Female, variant 1
- **Carlos** - Male, variant 1
- **Isabel** - Female, variant 2
- **Diego** - Male, variant 2

### Portuguese (pt)
- **Ana** - Female, variant 1
- **João** - Male, variant 1
- **Maria** - Female, variant 2
- **Pedro** - Male, variant 2

### Swahili (sw)
- **Amani** - Female, variant 1
- **Jabari** - Male, variant 1
- **Zara** - Female, variant 2
- **Kiano** - Male, variant 2

### Vietnamese (vi)
- **Linh** - Female, variant 1
- **Minh** - Male, variant 1
- **Hoa** - Female, variant 2
- **Tuan** - Male, variant 2

## Technical Details

### Voice Identifiers

Internally, eSpeak-NG uses voice identifiers in the format `{language}+{gender}{variant}`. For example:
- **Ona** (Lithuanian female, variant 1) → `lt+f1`
- **Pierre** (French male, variant 1) → `fr+m1`
- **Mei** (Chinese female, variant 1) → `zh+f1`

The `EspeakVoice` enum handles this mapping automatically.

### Language Codes

| Language   | Code | eSpeak Voice Base |
|------------|------|-------------------|
| Lithuanian | lt   | lt                |
| Chinese    | zh   | zh (Mandarin)     |
| Korean     | ko   | ko                |
| French     | fr   | fr                |
| German     | de   | de                |
| Spanish    | es   | es                |
| Portuguese | pt   | pt                |
| Swahili    | sw   | sw                |
| Vietnamese | vi   | vi                |

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

## Barsukas Integration

The eSpeak-NG engine is integrated into the Barsukas web interface:

1. Navigate to `/audio/generate`
2. Select "espeak-ng" as the TTS engine
3. Choose language - voices will update based on selected language
4. Select voices by name (e.g., Ona, Pierre, Mei)
5. Optionally enable "Use IPA" for phonetic generation
6. Submit to generate audio files

Generated files are stored in `AUDIO_BASE_DIR` with voice directories named after the voice (e.g., `lt/Ona/`, `fr/Pierre/`) to distinguish them from OpenAI-generated files.

## IPA Support

If lemmas have IPA (International Phonetic Alphabet) transcriptions, you can use them for audio generation:

```python
result = agent.generate_audio_for_lemma(
    session, lemma, language_code, voices,
    create_review_record=True,
    use_ipa=True  # Use IPA if available
)
```

Or from command line:
```bash
python -m agents.strazdas --language lt --use-ipa
```

This allows for more precise phonetic control over the generated audio.

## Performance Considerations

- eSpeak-NG is very fast (typically < 1 second per word)
- No API rate limits or costs
- Can process thousands of lemmas quickly
- Quality is lower than commercial TTS but acceptable for many use cases
- Useful for rapid prototyping and testing before investing in commercial TTS

## Code Examples

### Programmatic Usage

```python
from audioshoe.espeak import EspeakVoice, DEFAULT_ESPEAK_VOICES, generate_audio
from clients.audio import AudioFormat

# Generate with specific voice
result = generate_audio(
    text="bonjour",
    voice=EspeakVoice.PIERRE,
    speed=175,
    pitch=55,
)

# Get default voices for a language
lt_voices = DEFAULT_ESPEAK_VOICES["lt"]  # [Ona, Jonas, Ruta, Tomas]

# Get all voices for a language
all_lt_voices = EspeakVoice.get_voices_for_language("lt")

# Check voice properties
print(EspeakVoice.PIERRE.language_code)  # 'fr'
print(EspeakVoice.PIERRE.gender)  # 'm'
print(EspeakVoice.PIERRE.variant)  # 1
print(EspeakVoice.PIERRE.espeak_identifier)  # 'fr+m1'
```

### Agent Usage

```python
from agents.strazdas import StrazdasAgent
from audioshoe.espeak import EspeakVoice

agent = StrazdasAgent(output_dir="/path/to/output")

# Generate with specific voices
voices = [EspeakVoice.ONA, EspeakVoice.JONAS]
results = agent.generate_batch(
    language_code="lt",
    limit=100,
    voices=voices,
    use_ipa=True,
)

print(f"Generated {results['success_count']} files")
```

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
- Try different voice variants (1, 2, or 3)
- Consider using IPA input for better pronunciation

**KeyError when specifying voice:**
- Voice names are case-insensitive in CLI but case-sensitive in Python
- Use `EspeakVoice.ONA` (not `EspeakVoice.ona`)
- Or use `EspeakVoice['ONA']` for string lookups

## References

- [eSpeak-NG GitHub Repository](https://github.com/espeak-ng/espeak-ng)
- [eSpeak-NG Languages Documentation](https://github.com/espeak-ng/espeak-ng/blob/master/docs/languages.md)
- [eSpeak-NG Voices Documentation](https://github.com/espeak-ng/espeak-ng/blob/master/docs/voices.md)
- [eSpeak-NG Guide](https://github.com/espeak-ng/espeak-ng/blob/master/docs/guide.md)
