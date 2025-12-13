# Coqui TTS Audio Generation

This module provides text-to-speech audio generation using Coqui TTS (XTTS), a high-quality neural text-to-speech system with multilingual support and voice cloning capabilities.

**Project Repository:** https://github.com/coqui-ai/TTS

## Overview

The Coqui TTS integration allows generating high-quality neural TTS audio locally with optional voice cloning. This is useful for:

- Very high-quality neural voice synthesis
- Voice cloning from reference audio samples
- Local, offline audio generation
- No per-request costs
- Privacy (no data sent to external servers)
- GPU acceleration support for faster generation

## Components

### `coqui_tts.py`

Main TTS client that uses the Coqui TTS Python library.

**Key Features:**
- Supports all languages in the project: Lithuanian, Chinese, Korean, French, German, Spanish, Portuguese, Vietnamese, Swahili
- Gender-based voice selection (male/female variants)
- High-quality neural voice synthesis using XTTS v2
- Optional voice cloning with reference speaker audio
- Automatic WAV to MP3 conversion (requires ffmpeg)
- Configurable speech speed
- GPU acceleration support

**Usage:**
```python
from audioshoe.coqui import generate_audio, CoquiVoice

result = generate_audio(
    text="labas",
    voice=CoquiVoice.COQUI_LT_M1,  # Lithuanian male voice
    speed=1.0,  # speed multiplier (default: 1.0)
)

if result.success:
    # Save audio
    with open("output.mp3", "wb") as f:
        f.write(result.audio_data)
```

## Available Voices

Coqui voices use simplified UI names following the pattern: `coqui-{lang}-{gender}{variant}`

Where:
- `lang` = language code (lt, zh, ko, fr, de, es, pt, vi, sw)
- `gender` = m (male) or f (female)
- `variant` = 1, 2, etc.

All voices use the **XTTS v2** multilingual model with optional voice cloning.

### Lithuanian (lt)
- **coqui-lt-m1** - Male voice
- **coqui-lt-f1** - Female voice

### Chinese / Mandarin (zh)
- **coqui-zh-m1** - Male voice
- **coqui-zh-f1** - Female voice

### Korean (ko)
- **coqui-ko-m1** - Male voice
- **coqui-ko-f1** - Female voice

### French (fr)
- **coqui-fr-m1** - Male voice
- **coqui-fr-f1** - Female voice

### German (de)
- **coqui-de-m1** - Male voice
- **coqui-de-f1** - Female voice

### Spanish (es)
- **coqui-es-m1** - Male voice
- **coqui-es-f1** - Female voice

### Portuguese (pt)
- **coqui-pt-m1** - Male voice
- **coqui-pt-f1** - Female voice

### Vietnamese (vi)
- **coqui-vi-m1** - Male voice
- **coqui-vi-f1** - Female voice

### Swahili (sw)
- **coqui-sw-m1** - Male voice
- **coqui-sw-f1** - Female voice

## Voice Cloning

Coqui TTS supports voice cloning, allowing you to customize voices with reference speaker audio.

### Reference Speaker Files

Place reference speaker WAV files in: `~/.local/share/coqui/speakers/`

**Naming options:**
1. **Voice-specific:** `coqui-lt-m1.wav` (for specific voice)
2. **Language-gender default:** `lt-male.wav`, `lt-female.wav` (fallback for all lt male/female voices)

**Requirements for reference audio:**
- Format: WAV file
- Duration: 6-30 seconds recommended
- Quality: Clear, high-quality recording
- Content: Clean speech in target language
- Single speaker only

**Example:**
```bash
# Create speakers directory
mkdir -p ~/.local/share/coqui/speakers

# Add reference audio for Lithuanian male voice
cp my_reference_audio.wav ~/.local/share/coqui/speakers/coqui-lt-m1.wav

# Or add language-wide default
cp male_voice.wav ~/.local/share/coqui/speakers/lt-male.wav
```

When generating audio, the system will:
1. Look for voice-specific reference (e.g., `coqui-lt-m1.wav`)
2. Fall back to language-gender default (e.g., `lt-male.wav`)
3. Use default XTTS v2 voice if no reference found

## Prerequisites

### Coqui TTS Installation

**Install via pip:**
```bash
# Install Coqui TTS
pip install TTS

# For GPU support (CUDA)
pip install TTS[cuda]
```

**Verify Installation:**
```bash
python -c "import TTS; print(TTS.__version__)"
tts --list_models
```

### Model Download

The XTTS v2 model is downloaded automatically on first use. It will be cached in:
- Linux/macOS: `~/.local/share/tts/`
- Windows: `%APPDATA%\tts\`

**Manual download (optional):**
```bash
# Download XTTS v2 model manually
tts --model_name tts_models/multilingual/multi-dataset/xtts_v2 --text "test" --out_path test.wav
```

### GPU Support (Optional but Recommended)

For significantly faster generation, use GPU acceleration:

**NVIDIA GPU (CUDA):**
```bash
# Install PyTorch with CUDA support
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118

# Install TTS
pip install TTS
```

**AMD GPU (ROCm):**
```bash
# Install PyTorch with ROCm support
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/rocm5.6

# Install TTS
pip install TTS
```

**Apple Silicon (MPS):**
PyTorch MPS backend is automatically used on M1/M2/M3 Macs.

### Optional: ffmpeg (for MP3 output)

**Ubuntu/Debian:**
```bash
sudo apt-get install ffmpeg
```

**macOS:**
```bash
brew install ffmpeg
```

## Technical Details

### XTTS v2 Model

XTTS v2 is Coqui's flagship multilingual model featuring:
- 17+ languages supported
- Voice cloning from 6+ seconds of audio
- High-quality neural synthesis
- Streaming support
- GPU acceleration

**Model Identifier:**
```
tts_models/multilingual/multi-dataset/xtts_v2
```

### Language Codes

| Language   | Code | Coqui Code |
|------------|------|------------|
| Lithuanian | lt   | lt         |
| Chinese    | zh   | zh-cn      |
| Korean     | ko   | ko         |
| French     | fr   | fr         |
| German     | de   | de         |
| Spanish    | es   | es         |
| Portuguese | pt   | pt         |
| Vietnamese | vi   | vi         |
| Swahili    | sw   | sw         |

## Performance Considerations

- **First generation:** Slower due to model loading (~5-30 seconds)
- **Subsequent generations:** Much faster (~1-5 seconds per sentence)
- **GPU acceleration:** 3-10x faster than CPU
- **Voice cloning:** Adds minimal overhead (~0.5 seconds)
- **Model size:** XTTS v2 is ~1.8GB
- **Memory:** Requires ~4-6GB RAM (CPU) or ~2-4GB VRAM (GPU)

## Code Examples

### Programmatic Usage

```python
from audioshoe.coqui import CoquiVoice, DEFAULT_COQUI_VOICES, RECOMMENDED_VOICES, generate_audio
from clients.audio import AudioFormat

# Generate with Lithuanian male voice
result = generate_audio(
    text="labas rytas",
    voice=CoquiVoice.COQUI_LT_M1,
    speed=1.0,
)

# Generate with faster speech
result = generate_audio(
    text="labas",
    voice=CoquiVoice.COQUI_LT_M1,
    speed=1.2,  # 20% faster
)

# Get default voices for a language
lt_voices = DEFAULT_COQUI_VOICES["lt"]  # [COQUI_LT_M1, COQUI_LT_F1]
fr_voices = DEFAULT_COQUI_VOICES["fr"]  # [COQUI_FR_M1, COQUI_FR_F1]

# Get recommended voices
recommended_de = RECOMMENDED_VOICES["de"]  # German voices

# Get all voices for a language
all_zh_voices = CoquiVoice.get_voices_for_language("zh")

# Check voice properties
print(CoquiVoice.COQUI_LT_M1.language_code)  # 'lt'
print(CoquiVoice.COQUI_LT_M1.gender)  # 'm'
print(CoquiVoice.COQUI_LT_M1.model_name)  # 'tts_models/multilingual/multi-dataset/xtts_v2'
print(CoquiVoice.COQUI_LT_M1.ui_name)  # 'coqui-lt-m1'
print(CoquiVoice.COQUI_LT_M1.coqui_language)  # 'lt'

# Convert from UI name
voice = CoquiVoice.from_ui_name("coqui-lt-m1")
```

### Custom Client Configuration

```python
from audioshoe.coqui import CoquiClient
from pathlib import Path

# Disable GPU (use CPU only)
client = CoquiClient(
    use_gpu=False,
    debug=True
)

# Custom speaker directory for voice cloning
client = CoquiClient(
    speaker_wav_dir=Path("/custom/speakers/"),
    use_gpu=True
)

result = client.generate_audio(
    text="hello",
    voice=CoquiVoice.COQUI_FR_M1,
)
```

### Voice Cloning Example

```python
from audioshoe.coqui import CoquiClient, CoquiVoice
from pathlib import Path

# Set up client with custom speaker directory
client = CoquiClient(
    speaker_wav_dir=Path("./my_speakers/"),
    use_gpu=True
)

# Place your reference audio at: ./my_speakers/coqui-lt-m1.wav
# Then generate with cloned voice
result = client.generate_audio(
    text="Labas! Kaip laikaisi?",
    voice=CoquiVoice.COQUI_LT_M1,
)
```

## Troubleshooting

**Error: "Coqui TTS library not found"**
- Install the TTS library: `pip install TTS`
- Verify installation: `python -c "import TTS"`

**Error: "Model download failed"**
- Check internet connection
- Verify disk space (~2GB needed)
- Try manual download: `tts --model_name tts_models/multilingual/multi-dataset/xtts_v2 --text "test" --out_path test.wav`

**Slow generation (CPU)**
- Enable GPU acceleration (see GPU Support section above)
- First generation is always slower due to model loading
- Consider using lower-quality models for faster generation

**CUDA out of memory**
- Reduce batch size (process shorter text segments)
- Use CPU mode: `CoquiClient(use_gpu=False)`
- Close other GPU applications
- Upgrade GPU or add more VRAM

**Poor voice quality**
- Ensure reference speaker audio is high quality
- Use 10-20 seconds of clear speech for reference
- Verify reference audio is in the correct language
- Check that WAV file is not corrupted

**Voice cloning not working**
- Verify speaker WAV files are in correct directory: `~/.local/share/coqui/speakers/`
- Check file naming: `coqui-lt-m1.wav` or `lt-male.wav`
- Ensure WAV files are valid and playable
- Enable debug mode to see which speaker file is being used

**Warning: "ffmpeg not found"**
- Install ffmpeg for MP3 conversion support
- Or use `audio_format=AudioFormat.WAV` to avoid the warning

**Import errors after installation**
- Update pip: `pip install --upgrade pip`
- Reinstall TTS: `pip uninstall TTS && pip install TTS`
- Check for conflicting packages: `pip list | grep -i tts`

**Model compatibility issues**
- Update TTS library: `pip install --upgrade TTS`
- Clear cache: `rm -rf ~/.local/share/tts/`
- Redownload models

## Comparison with Other Backends

| Feature | Coqui | Piper | eSpeak-NG |
|---------|-------|-------|-----------|
| Quality | ★★★★★ | ★★★★☆ | ★★☆☆☆ |
| Speed (CPU) | ★★☆☆☆ | ★★★★☆ | ★★★★★ |
| Speed (GPU) | ★★★★☆ | ★★★★★ | N/A |
| Voice Cloning | ✓ | ✗ | ✗ |
| Model Size | ~1.8GB | ~10-50MB | <1MB |
| Setup Complexity | Medium | Easy | Easy |
| GPU Support | ✓ | ✓ | ✗ |
| Languages | 17+ | 40+ | 100+ |

**Recommendation:**
- Use **Coqui** for highest quality and voice cloning
- Use **Piper** for balance of quality and speed
- Use **eSpeak-NG** for maximum speed and minimal resources

## References

- [Coqui TTS GitHub Repository](https://github.com/coqui-ai/TTS)
- [XTTS Documentation](https://docs.coqui.ai/en/latest/models/xtts.html)
- [Coqui TTS Models](https://github.com/coqui-ai/TTS/wiki/Released-Models)
- [Voice Samples](https://coqui.ai/samples)
