# Piper TTS Audio Generation

This module provides text-to-speech audio generation using Piper, a fast, local neural text-to-speech system.

**Project Repository:** https://github.com/rhasspy/piper

## Overview

The Piper integration allows generating high-quality neural TTS audio locally without requiring API calls to external services. This is useful for:

- High-quality neural voice synthesis
- Local, offline audio generation
- No per-request costs
- Privacy (no data sent to external servers)
- Fast generation with GPU acceleration support

## Components

### `piper_tts.py`

Main TTS client that interfaces with the Piper command-line tool.

**Key Features:**
- Supports all languages in the project: Lithuanian, Chinese, Korean, French, German, Spanish, Portuguese, Vietnamese
- Gender-based voice selection (male/female variants)
- High-quality neural voice synthesis
- Automatic WAV to MP3 conversion (requires ffmpeg)
- Configurable speech speed

**Usage:**
```python
from audioshoe.piper import generate_audio, PiperVoice

result = generate_audio(
    text="labas",
    voice=PiperVoice.PIPER_LT_M1,  # Lithuanian male voice
    speed=1.0,  # speed multiplier (default: 1.0)
)

if result.success:
    # Save audio
    with open("output.mp3", "wb") as f:
        f.write(result.audio_data)
```

## Available Voices

Piper voices use simplified UI names following the pattern: `piper-{lang}-{gender}{variant}`

Where:
- `lang` = language code (lt, zh, ko, fr, de, es, pt, vi)
- `gender` = m (male) or f (female)
- `variant` = 1, 2, etc.

### Lithuanian (lt)
- **piper-lt-m1** - Male voice (model: human-medium)

### Chinese / Mandarin (zh)
- **piper-zh-m1** - Male voice (model: huayan-medium)
- **piper-zh-f1** - Female voice (model: huayan-x_low)

### Korean (ko)
- **piper-ko-m1** - Male voice (model: human-medium)

### French (fr)
- **piper-fr-m1** - Male voice (model: tom-medium)
- **piper-fr-f1** - Female voice (model: siwis-medium)
- **piper-fr-f2** - Female voice (model: upmc-medium)

### German (de)
- **piper-de-m1** - Male voice (model: thorsten-high)
- **piper-de-f1** - Female voice (model: eva_k-x_low)
- **piper-de-f2** - Female voice (model: karlsson-low)

### Spanish (es)
- **piper-es-m1** - Male voice (model: carlfm-x_low)
- **piper-es-m2** - Male voice (model: davefx-medium)

### Portuguese (pt)
- **piper-pt-m1** - Male voice (model: tugao-medium)

### Vietnamese (vi)
- **piper-vi-m1** - Male voice (model: vais1000-medium)
- **piper-vi-f1** - Female voice (model: 25hours-single-low)

**Note**: Swahili (sw) does not have Piper voices available yet.

## Prerequisites

### Piper Installation

**Ubuntu/Debian:**
```bash
# Download latest release
wget https://github.com/rhasspy/piper/releases/download/v1.2.0/piper_amd64.tar.gz
tar -xzf piper_amd64.tar.gz

# Move to system path
sudo mv piper/piper /usr/local/bin/
```

**macOS (ARM/M1/M2):**
```bash
# Download latest release for macOS
wget https://github.com/rhasspy/piper/releases/download/v1.2.0/piper_arm64.tar.gz
tar -xzf piper_arm64.tar.gz

# Move to system path
sudo mv piper/piper /usr/local/bin/
```

**Verify Installation:**
```bash
piper --version
```

### Voice Model Installation

Piper requires downloading voice model files (.onnx) for each language/voice you want to use.

**Default Models Directory:**
```
~/.local/share/piper/models/
```

**Download Voice Models:**

Visit the [Piper Voices Repository](https://huggingface.co/rhasspy/piper-voices/tree/main) to download models.

Example for Lithuanian:
```bash
# Create models directory
mkdir -p ~/.local/share/piper/models

# Download Lithuanian human-medium voice
cd ~/.local/share/piper/models
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/lt/lt_LT/human/medium/lt_LT-human-medium.onnx
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/lt/lt_LT/human/medium/lt_LT-human-medium.onnx.json
```

**Quick Install Script for All Voices:**
```bash
#!/bin/bash
# Install all voices used in this project

MODELS_DIR="$HOME/.local/share/piper/models"
mkdir -p "$MODELS_DIR"
cd "$MODELS_DIR"

BASE_URL="https://huggingface.co/rhasspy/piper-voices/resolve/main"

# Lithuanian
wget "$BASE_URL/lt/lt_LT/human/medium/lt_LT-human-medium.onnx"
wget "$BASE_URL/lt/lt_LT/human/medium/lt_LT-human-medium.onnx.json"

# Chinese (Mandarin)
wget "$BASE_URL/zh/zh_CN/huayan/medium/zh_CN-huayan-medium.onnx"
wget "$BASE_URL/zh/zh_CN/huayan/medium/zh_CN-huayan-medium.onnx.json"
wget "$BASE_URL/zh/zh_CN/huayan/x_low/zh_CN-huayan-x_low.onnx"
wget "$BASE_URL/zh/zh_CN/huayan/x_low/zh_CN-huayan-x_low.onnx.json"

# Korean
wget "$BASE_URL/ko/ko_KR/human/medium/ko_KR-human-medium.onnx"
wget "$BASE_URL/ko/ko_KR/human/medium/ko_KR-human-medium.onnx.json"

# French
wget "$BASE_URL/fr/fr_FR/tom/medium/fr_FR-tom-medium.onnx"
wget "$BASE_URL/fr/fr_FR/tom/medium/fr_FR-tom-medium.onnx.json"
wget "$BASE_URL/fr/fr_FR/siwis/medium/fr_FR-siwis-medium.onnx"
wget "$BASE_URL/fr/fr_FR/siwis/medium/fr_FR-siwis-medium.onnx.json"
wget "$BASE_URL/fr/fr_FR/upmc/medium/fr_FR-upmc-medium.onnx"
wget "$BASE_URL/fr/fr_FR/upmc/medium/fr_FR-upmc-medium.onnx.json"

# German
wget "$BASE_URL/de/de_DE/thorsten/high/de_DE-thorsten-high.onnx"
wget "$BASE_URL/de/de_DE/thorsten/high/de_DE-thorsten-high.onnx.json"
wget "$BASE_URL/de/de_DE/eva_k/x_low/de_DE-eva_k-x_low.onnx"
wget "$BASE_URL/de/de_DE/eva_k/x_low/de_DE-eva_k-x_low.onnx.json"
wget "$BASE_URL/de/de_DE/karlsson/low/de_DE-karlsson-low.onnx"
wget "$BASE_URL/de/de_DE/karlsson/low/de_DE-karlsson-low.onnx.json"

# Spanish
wget "$BASE_URL/es/es_ES/carlfm/x_low/es_ES-carlfm-x_low.onnx"
wget "$BASE_URL/es/es_ES/carlfm/x_low/es_ES-carlfm-x_low.onnx.json"
wget "$BASE_URL/es/es_ES/davefx/medium/es_ES-davefx-medium.onnx"
wget "$BASE_URL/es/es_ES/davefx/medium/es_ES-davefx-medium.onnx.json"

# Portuguese
wget "$BASE_URL/pt/pt_PT/tugao/medium/pt_PT-tugao-medium.onnx"
wget "$BASE_URL/pt/pt_PT/tugao/medium/pt_PT-tugao-medium.onnx.json"

# Vietnamese
wget "$BASE_URL/vi/vi_VN/vais1000/medium/vi_VN-vais1000-medium.onnx"
wget "$BASE_URL/vi/vi_VN/vais1000/medium/vi_VN-vais1000-medium.onnx.json"
wget "$BASE_URL/vi/vi_VN/25hours-single/low/vi_VN-25hours-single-low.onnx"
wget "$BASE_URL/vi/vi_VN/25hours-single/low/vi_VN-25hours-single-low.onnx.json"

echo "All voice models downloaded to $MODELS_DIR"
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

## Technical Details

### Voice Identifiers

Internally, Piper uses voice identifiers in the format `{language_region}-{model_name}`:

Examples:
- **piper-lt-m1** (Lithuanian male) → `lt_LT-human-medium`
- **piper-fr-m1** (French male) → `fr_FR-tom-medium`
- **piper-de-m1** (German male) → `de_DE-thorsten-high`

The `PiperVoice` enum handles this mapping automatically via the `piper_identifier` property.

### Language Codes

| Language   | Code | Piper Region Code |
|------------|------|-------------------|
| Lithuanian | lt   | lt_LT             |
| Chinese    | zh   | zh_CN (Mandarin)  |
| Korean     | ko   | ko_KR             |
| French     | fr   | fr_FR             |
| German     | de   | de_DE             |
| Spanish    | es   | es_ES             |
| Portuguese | pt   | pt_PT             |
| Vietnamese | vi   | vi_VN             |
| Swahili    | sw   | sw_CD             |

## Performance Considerations

- Piper is very fast with neural quality (typically 1-3 seconds per sentence)
- GPU acceleration supported (automatically used if available)
- No API rate limits or costs
- Model files are loaded once and cached in memory
- Significantly better quality than formant synthesis (eSpeak)
- Comparable quality to cloud TTS services

## Code Examples

### Programmatic Usage

```python
from audioshoe.piper import PiperVoice, DEFAULT_PIPER_VOICES, RECOMMENDED_VOICES, generate_audio
from clients.audio import AudioFormat

# Generate with Lithuanian male voice
result = generate_audio(
    text="labas rytas",
    voice=PiperVoice.PIPER_LT_M1,
    speed=1.0,
)

# Generate with faster speech
result = generate_audio(
    text="labas",
    voice=PiperVoice.PIPER_LT_M1,
    speed=1.2,  # 20% faster
)

# Get default voices for a language
lt_voices = DEFAULT_PIPER_VOICES["lt"]  # [PIPER_LT_M1]
fr_voices = DEFAULT_PIPER_VOICES["fr"]  # [PIPER_FR_M1, PIPER_FR_F1, PIPER_FR_F2]

# Get recommended voices
recommended_de = RECOMMENDED_VOICES["de"]  # German voices

# Get all voices for a language
all_zh_voices = PiperVoice.get_voices_for_language("zh")

# Check voice properties
print(PiperVoice.PIPER_LT_M1.language_code)  # 'lt'
print(PiperVoice.PIPER_LT_M1.gender)  # 'm'
print(PiperVoice.PIPER_LT_M1.model_name)  # 'human-medium'
print(PiperVoice.PIPER_LT_M1.piper_identifier)  # 'lt_LT-human-medium'
print(PiperVoice.PIPER_LT_M1.ui_name)  # 'piper-lt-m1'

# Convert from UI name
voice = PiperVoice.from_ui_name("piper-lt-m1")
```

### Custom Models Directory

```python
from audioshoe.piper import PiperClient
from pathlib import Path

# Use custom models directory
client = PiperClient(
    models_dir=Path("/custom/path/to/models"),
    debug=True
)

result = client.generate_audio(
    text="hello",
    voice=PiperVoice.PIPER_FR_M1,
)
```

## Troubleshooting

**Error: "Piper not found"**
- Install Piper using the instructions above
- If installed in a non-standard location, specify the path:
  ```python
  client = PiperClient(piper_command="/path/to/piper")
  ```

**Error: "Model file not found"**
- Download the required voice model files (see Voice Model Installation above)
- Verify model files are in the correct directory: `~/.local/share/piper/models/`
- Check that both `.onnx` and `.onnx.json` files are present
- Use custom models directory if needed:
  ```python
  client = PiperClient(models_dir=Path("/custom/models/path"))
  ```

**Poor audio quality**
- Make sure you're using high-quality models (e.g., `thorsten-high` for German)
- Adjust speech speed if needed: `speed=0.9` for slower, clearer speech
- Verify the correct model files were downloaded (not corrupted)

**Slow generation**
- First generation is slower as models are loaded into memory
- Subsequent generations are much faster
- Consider using GPU acceleration if available
- Use lower quality models (e.g., `x_low` instead of `high`) for faster generation

**Warning: "ffmpeg not found. Returning WAV format instead."**
- Install ffmpeg for MP3 conversion support
- Or use `audio_format=AudioFormat.WAV` to avoid the warning

**KeyError when specifying voice:**
- Voice names are case-sensitive in Python
- Use `PiperVoice.PIPER_LT_M1` (not `PiperVoice.piper_lt_m1`)
- Or use `PiperVoice.from_ui_name("piper-lt-m1")` for string lookups

## References

- [Piper GitHub Repository](https://github.com/rhasspy/piper)
- [Piper Voices (Hugging Face)](https://huggingface.co/rhasspy/piper-voices)
- [Piper Documentation](https://rhasspy.github.io/piper-samples/)
- [Rhasspy Project](https://rhasspy.readthedocs.io/)
