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

The system supports two types of voices:

1. **Regular eSpeak-NG voices**: Fast, lightweight formant synthesis (2F/2M per language)
2. **MBROLA voices**: High-quality diphone synthesis with better naturalness (varies by language)

### Voice Quality Comparison

- **Regular eSpeak**: Fast generation, robotic but intelligible, no additional setup required
- **MBROLA**: Significantly better audio quality, more natural prosody, requires MBROLA installation

### Regular eSpeak Voices

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

### MBROLA Voices (High Quality)

MBROLA voices provide significantly better audio quality through diphone synthesis. Available for most languages:

#### Lithuanian (lt)
- **Vytautas** - Male, MBROLA (mb-lt1)
- **Darius** - Male, MBROLA (mb-lt2)

#### Chinese / Mandarin (zh)
- **Xiaomei** - Female, MBROLA (mb-cn1)

#### Korean (ko)
- **Jihoon** - Male, MBROLA (mb-hn1)

#### French (fr)
- **Camille** - Female, MBROLA (mb-fr2)
- **Jacques** - Male, MBROLA (mb-fr1)
- **Sophie** - Female, MBROLA (mb-fr4)
- **Bernard** - Male, MBROLA (mb-fr3)

#### German (de)
- **Petra** - Female, MBROLA (mb-de1)
- **Klaus** - Male, MBROLA (mb-de2)
- **Birgit** - Female, MBROLA (mb-de5)
- **Stefan** - Male, MBROLA (mb-de4)

#### Spanish (es)
- **Carmen** - Female, MBROLA (mb-es3)
- **Raúl** - Male, MBROLA (mb-es1)
- **Miguel** - Male, MBROLA (mb-es2)

#### Portuguese (pt)
- **Gabriela** - Female, MBROLA Brazilian (mb-br4)
- **Ricardo** - Male, MBROLA Brazilian (mb-br1)
- **Fernando** - Male, MBROLA Brazilian (mb-br3)

**Note**: Vietnamese and Swahili do not have MBROLA voices available and use regular eSpeak voices only.

## Technical Details

### Voice Identifiers

Internally, eSpeak-NG uses different identifier formats for regular and MBROLA voices:

**Regular eSpeak voices** use the format `{language}+{gender}{variant}`:
- **Ona** (Lithuanian female, variant 1) → `lt+f1`
- **Pierre** (French male, variant 1) → `fr-fr+m1`
- **Mei** (Chinese female, variant 1) → `cmn+f1`

**MBROLA voices** use the format `mb-{language}{number}`:
- **Vytautas** (Lithuanian MBROLA male) → `mb-lt1`
- **Jacques** (French MBROLA male) → `mb-fr1`
- **Petra** (German MBROLA female) → `mb-de1`

The `EspeakVoice` enum handles this mapping automatically via the `espeak_identifier` property.

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

### MBROLA Installation (for High-Quality Voices)

MBROLA voices provide significantly better audio quality but require additional installation steps.

#### Step 1: Install MBROLA Binary

**Ubuntu/Debian:**
```bash
sudo apt-get install mbrola
```

**macOS:**
```bash
# Download from GitHub releases
wget https://github.com/numediart/MBROLA/releases/download/3.3/mbrola-linux-i386
sudo mv mbrola-linux-i386 /usr/local/bin/mbrola
sudo chmod +x /usr/local/bin/mbrola

# Or compile from source
git clone https://github.com/numediart/MBROLA.git
cd MBROLA
make
sudo cp Bin/mbrola /usr/local/bin/
```

**Verify MBROLA Installation:**
```bash
mbrola -h
```

#### Step 2: Install MBROLA Voice Data Files

Voice data files need to be installed for each language you want to use.

**Ubuntu/Debian (via package manager):**
```bash
# Install specific language voices
sudo apt-get install mbrola-fr1 mbrola-fr2 mbrola-fr3 mbrola-fr4  # French
sudo apt-get install mbrola-de1 mbrola-de2 mbrola-de4 mbrola-de5  # German
sudo apt-get install mbrola-es1 mbrola-es2 mbrola-es3            # Spanish
sudo apt-get install mbrola-br1 mbrola-br3 mbrola-br4            # Portuguese (Brazilian)
sudo apt-get install mbrola-cn1                                   # Chinese
sudo apt-get install mbrola-hn1                                   # Korean
sudo apt-get install mbrola-lt1 mbrola-lt2                        # Lithuanian
```

**Manual Installation (all systems):**
```bash
# Create MBROLA voices directory
sudo mkdir -p /usr/share/mbrola

# Download voices from GitHub
cd /tmp
git clone https://github.com/numediart/MBROLA-voices.git

# Install specific voices (example for French and German)
sudo cp -r MBROLA-voices/data/fr1 /usr/share/mbrola/
sudo cp -r MBROLA-voices/data/fr2 /usr/share/mbrola/
sudo cp -r MBROLA-voices/data/de1 /usr/share/mbrola/
sudo cp -r MBROLA-voices/data/de2 /usr/share/mbrola/

# Install all available voices for your languages
for lang in fr1 fr2 fr3 fr4 de1 de2 de4 de5 es1 es2 es3 br1 br3 br4 cn1 hn1 lt1 lt2; do
    sudo cp -r MBROLA-voices/data/$lang /usr/share/mbrola/ 2>/dev/null || echo "$lang not found"
done
```

**Verify MBROLA Voices:**
```bash
# Check installed voices
ls /usr/share/mbrola/

# Test a MBROLA voice with espeak-ng
espeak-ng -v mb-fr1 "Bonjour"
```

#### Step 3: Verify Integration

Test that espeak-ng can use MBROLA voices:

```bash
# Test French MBROLA voice
espeak-ng -v mb-fr1 "Bonjour, comment allez-vous?"

# Test German MBROLA voice
espeak-ng -v mb-de1 "Guten Tag"

# Test Lithuanian MBROLA voice
espeak-ng -v mb-lt1 "Labas"
```

If you hear clear, natural speech, the installation is successful.

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
from audioshoe.espeak import EspeakVoice, DEFAULT_ESPEAK_VOICES, MBROLA_VOICES, RECOMMENDED_VOICES, generate_audio
from clients.audio import AudioFormat

# Generate with regular eSpeak voice
result = generate_audio(
    text="bonjour",
    voice=EspeakVoice.PIERRE,
    speed=175,
    pitch=55,
)

# Generate with MBROLA voice (high quality)
result = generate_audio(
    text="bonjour",
    voice=EspeakVoice.JACQUES,  # MBROLA voice
    speed=175,
    pitch=55,
)

# Get default voices for a language (regular eSpeak only)
lt_voices = DEFAULT_ESPEAK_VOICES["lt"]  # [Ona, Jonas, Ruta, Tomas]

# Get MBROLA voices for a language
fr_mbrola = MBROLA_VOICES["fr"]  # [Camille, Jacques, Sophie, Bernard]

# Get recommended voices (mix of MBROLA and regular)
recommended_fr = RECOMMENDED_VOICES["fr"]  # MBROLA voices prioritized

# Get all voices for a language
all_fr_voices = EspeakVoice.get_voices_for_language("fr")  # All 8 French voices

# Get only MBROLA voices for a language
mbrola_only = EspeakVoice.get_mbrola_voices_for_language("fr")

# Get only regular eSpeak voices
regular_only = EspeakVoice.get_regular_voices_for_language("fr")

# Check voice properties
print(EspeakVoice.PIERRE.language_code)  # 'fr'
print(EspeakVoice.PIERRE.gender)  # 'm'
print(EspeakVoice.PIERRE.variant)  # 1
print(EspeakVoice.PIERRE.is_mbrola)  # False
print(EspeakVoice.PIERRE.espeak_identifier)  # 'fr-fr+m1'

# MBROLA voice properties
print(EspeakVoice.JACQUES.is_mbrola)  # True
print(EspeakVoice.JACQUES.mbrola_code)  # 'mb-fr1'
print(EspeakVoice.JACQUES.espeak_identifier)  # 'mb-fr1'
```

### Agent Usage

```python
from agents.strazdas import StrazdasAgent
from audioshoe.espeak import EspeakVoice, MBROLA_VOICES

agent = StrazdasAgent(output_dir="/path/to/output")

# Generate with regular eSpeak voices
voices = [EspeakVoice.ONA, EspeakVoice.JONAS]
results = agent.generate_batch(
    language_code="lt",
    limit=100,
    voices=voices,
    use_ipa=True,
)

# Generate with MBROLA voices for better quality
mbrola_voices = MBROLA_VOICES["fr"]  # [Camille, Jacques, Sophie, Bernard]
results = agent.generate_batch(
    language_code="fr",
    limit=100,
    voices=mbrola_voices,
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

**Error: "MBROLA voice not found" or no audio with MBROLA voices**
- Verify MBROLA binary is installed: `which mbrola`
- Check if voice data files are installed: `ls /usr/share/mbrola/`
- Test directly: `espeak-ng -v mb-fr1 "test"`
- If the voice directory exists but doesn't work, check permissions: `ls -la /usr/share/mbrola/`
- Ensure espeak-ng can find MBROLA: check that `/usr/bin/mbrola` or `/usr/local/bin/mbrola` exists

**MBROLA voices produce no sound but regular voices work**
- MBROLA binary may not be in PATH
- Try creating a symlink: `sudo ln -s /usr/bin/mbrola /usr/local/bin/mbrola`
- Check espeak-ng MBROLA integration: `espeak-ng --voices=mbrola`

**Poor quality even with MBROLA voices**
- Adjust speed: `speed=175` (default), range 80-450
- Adjust pitch: `pitch=50` (default), range 0-99
- Different MBROLA voices have different characteristics - try variants (e.g., mb-fr1 vs mb-fr3)
- Consider using IPA input for better pronunciation control

**Warning: "ffmpeg not found. Returning WAV format instead."**
- Install ffmpeg for MP3 conversion support
- Or use `audio_format=AudioFormat.WAV` to avoid the warning

**KeyError when specifying voice:**
- Voice names are case-sensitive in Python
- Use `EspeakVoice.ONA` (not `EspeakVoice.ona`)
- Or use `EspeakVoice['ONA']` for string lookups

**MBROLA voice not available for my language**
- Check `MBROLA_VOICES` dictionary to see what's available
- Vietnamese and Swahili don't have MBROLA voices - use regular eSpeak
- For languages with limited MBROLA support, mix MBROLA and regular voices

## References

### eSpeak-NG
- [eSpeak-NG GitHub Repository](https://github.com/espeak-ng/espeak-ng)
- [eSpeak-NG Languages Documentation](https://github.com/espeak-ng/espeak-ng/blob/master/docs/languages.md)
- [eSpeak-NG Voices Documentation](https://github.com/espeak-ng/espeak-ng/blob/master/docs/voices.md)
- [eSpeak-NG Guide](https://github.com/espeak-ng/espeak-ng/blob/master/docs/guide.md)

### MBROLA
- [MBROLA Project GitHub](https://github.com/numediart/MBROLA)
- [MBROLA Voices Repository](https://github.com/numediart/MBROLA-voices)
- [eSpeak-NG MBROLA Documentation](https://github.com/espeak-ng/espeak-ng/blob/master/docs/mbrola.md)
- [MBROLA Wikipedia](https://en.wikipedia.org/wiki/MBROLA)
