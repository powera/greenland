# Qwen3-TTS Audio Generation

This module provides text-to-speech audio generation using Qwen3-TTS, a high-quality neural TTS system from Alibaba's Qwen team with multilingual support, voice design, and voice cloning capabilities.

**Project Repository:** https://github.com/QwenLM/Qwen3-TTS

## Overview

The Qwen3-TTS integration enables generating high-quality neural TTS audio locally with:

- Voice design via natural language descriptions
- Voice cloning from 3+ seconds of reference audio
- Support for 10 languages (CJK + FIGS + PT supported here)
- Local, offline audio generation
- Apple Silicon (M1/M2/M3/M4) support via MPS
- NVIDIA GPU support via CUDA

## Supported Languages

| Language   | Code | Voices Available |
|------------|------|------------------|
| Chinese    | zh   | 4 (f1, f2, m1, m2) |
| Japanese   | ja   | 4 (f1, f2, m1, m2) |
| Korean     | ko   | 4 (f1, f2, m1, m2) |
| French     | fr   | 4 (f1, f2, m1, m2) |
| Italian    | it   | 4 (f1, f2, m1, m2) |
| German     | de   | 4 (f1, f2, m1, m2) |
| Spanish    | es   | 4 (f1, f2, m1, m2) |
| Portuguese | pt   | 4 (f1, f2, m1, m2) |

## Components

### `qwen_tts.py`

Main TTS client that uses the Qwen3-TTS Python library.

**Key Features:**
- Voice design: Create voices via natural language description
- Voice cloning: Clone voices from reference audio samples
- Automatic device detection (MPS, CUDA, CPU)
- WAV to MP3 conversion (requires ffmpeg)
- Configurable models (1.7B or 0.6B variants)

**Usage:**
```python
from audioshoe.qwen import generate_audio, QwenVoice

result = generate_audio(
    text="你好世界",
    voice=QwenVoice.QWEN_ZH_F1,  # Chinese female soprano
)

if result.success:
    with open("output.mp3", "wb") as f:
        f.write(result.audio_data)
```

### `types.py`

Voice definitions and configuration.

## Available Voices

Qwen voices use the naming pattern: `qwen-{lang}-{gender}{variant}`

Where:
- `lang` = language code (zh, ja, ko, fr, it, de, es, pt)
- `gender` = f (female) or m (male)
- `variant` = 1 or 2

### Voice Types

| Variant | Gender | Pitch Type | Description |
|---------|--------|------------|-------------|
| f1 | Female | Soprano | Young, bright, high-pitched |
| f2 | Female | Alto | Mature, warm, lower-pitched |
| m1 | Male | Tenor | Young, clear, higher-pitched |
| m2 | Male | Bass | Mature, deep, authoritative |

### Chinese (zh)
- **qwen-zh-f1** - Female soprano (young, bright)
- **qwen-zh-f2** - Female alto (mature, warm)
- **qwen-zh-m1** - Male tenor (young, clear)
- **qwen-zh-m2** - Male bass (mature, deep)

### Japanese (ja)
- **qwen-ja-f1** - Female soprano
- **qwen-ja-f2** - Female alto
- **qwen-ja-m1** - Male tenor
- **qwen-ja-m2** - Male bass

### Korean (ko)
- **qwen-ko-f1** - Female soprano
- **qwen-ko-f2** - Female alto
- **qwen-ko-m1** - Male tenor
- **qwen-ko-m2** - Male bass

### French (fr)
- **qwen-fr-f1** - Female soprano
- **qwen-fr-f2** - Female alto
- **qwen-fr-m1** - Male tenor
- **qwen-fr-m2** - Male bass

### Italian (it)
- **qwen-it-f1** - Female soprano
- **qwen-it-f2** - Female alto
- **qwen-it-m1** - Male tenor
- **qwen-it-m2** - Male bass

### German (de)
- **qwen-de-f1** - Female soprano
- **qwen-de-f2** - Female alto
- **qwen-de-m1** - Male tenor
- **qwen-de-m2** - Male bass

### Spanish (es)
- **qwen-es-f1** - Female soprano
- **qwen-es-f2** - Female alto
- **qwen-es-m1** - Male tenor
- **qwen-es-m2** - Male bass

### Portuguese (pt)
- **qwen-pt-f1** - Female soprano
- **qwen-pt-f2** - Female alto
- **qwen-pt-m1** - Male tenor
- **qwen-pt-m2** - Male bass

## Voice Design

Qwen3-TTS uses natural language prompts to generate distinct voice characteristics. Each voice has a predefined prompt describing its pitch, tone, and speaking style.

### Custom Voice Design

You can add custom instructions for emotion or style:

```python
from audioshoe.qwen import generate_audio, QwenVoice

# Add emotion instruction
result = generate_audio(
    text="I'm so happy to see you!",
    voice=QwenVoice.QWEN_EN_F1,
    instruct="excited and joyful",
)
```

## Voice Cloning

Clone voices from reference audio (3+ seconds recommended).

### Reference Audio Files

Place reference WAV files in: `~/.local/share/qwen-tts/speakers/`

**Naming options:**
1. **Voice-specific:** `qwen-zh-f1.wav`
2. **Language-gender-pitch:** `zh-female-soprano.wav`
3. **Language-gender default:** `zh-female.wav`

### Voice Cloning Example

```python
from audioshoe.qwen import QwenTTSClient, QwenVoice

client = QwenTTSClient()

result = client.generate_audio(
    text="Hello, this is my cloned voice.",
    voice=QwenVoice.QWEN_ZH_F1,
    use_voice_cloning=True,
    ref_audio="/path/to/reference.wav",
    ref_text="The transcript of the reference audio.",
)
```

## Prerequisites

### Qwen TTS Library Installation

**Install via pip:**
```bash
pip install qwen-tts
```

**For faster inference with Flash Attention (CUDA only):**
```bash
pip install flash-attn --no-build-isolation
```

### PyTorch Installation

**Apple Silicon (M1/M2/M3/M4):**
```bash
pip install torch torchvision torchaudio
```
MPS backend is automatically used.

**NVIDIA GPU (CUDA):**
```bash
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118
```

**CPU Only:**
```bash
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu
```

### Optional: ffmpeg (for MP3 output)

**macOS:**
```bash
brew install ffmpeg
```

**Ubuntu/Debian:**
```bash
sudo apt-get install ffmpeg
```

## Model Variants

| Model | Size | Features | Use Case |
|-------|------|----------|----------|
| `Qwen3-TTS-12Hz-1.7B-VoiceDesign` | 1.7B | Voice design via prompts | Default, flexible |
| `Qwen3-TTS-12Hz-1.7B-CustomVoice` | 1.7B | 9 preset speakers | Consistent voices |
| `Qwen3-TTS-12Hz-1.7B-Base` | 1.7B | Voice cloning | Clone from audio |
| `Qwen3-TTS-12Hz-0.6B-CustomVoice` | 0.6B | 9 preset speakers | Faster, smaller |
| `Qwen3-TTS-12Hz-0.6B-Base` | 0.6B | Voice cloning | Faster, smaller |

## Technical Details

### Device Selection

The client automatically selects the best available device:
1. **MPS** (Apple Silicon) - Recommended for M1/M2/M3/M4 Macs
2. **CUDA** (NVIDIA GPU) - Recommended for NVIDIA GPUs
3. **CPU** - Fallback, slower but always available

### Data Types

- **CUDA:** bfloat16 (best quality)
- **MPS:** float16 (Apple Silicon optimized)
- **CPU:** float32 (most compatible)

### Memory Requirements

| Model | VRAM/RAM Required |
|-------|-------------------|
| 1.7B | ~4-6GB |
| 0.6B | ~2-3GB |

## Code Examples

### Basic Usage

```python
from audioshoe.qwen import generate_audio, QwenVoice

# Generate Chinese speech
result = generate_audio(
    text="你好，很高兴认识你。",
    voice=QwenVoice.QWEN_ZH_F2,  # Female alto
)

if result.success:
    with open("chinese.mp3", "wb") as f:
        f.write(result.audio_data)

# Generate Japanese speech
result = generate_audio(
    text="こんにちは、お元気ですか。",
    voice=QwenVoice.QWEN_JA_M1,  # Male tenor
)

# Generate French speech
result = generate_audio(
    text="Bonjour, comment allez-vous?",
    voice=QwenVoice.QWEN_FR_F1,  # Female soprano
)
```

### Custom Client Configuration

```python
from audioshoe.qwen import QwenTTSClient, QwenVoice
import torch

# Explicit device selection
client = QwenTTSClient(
    device="mps",  # or "cuda:0" or "cpu"
    dtype=torch.float16,
    debug=True,
)

# Use smaller model for faster inference
client = QwenTTSClient(
    model_name=QwenTTSClient.MODEL_CUSTOM_VOICE_SMALL,
)

# Enable Flash Attention (CUDA only)
client = QwenTTSClient(
    device="cuda:0",
    use_flash_attention=True,
)
```

### Working with Voice Collections

```python
from audioshoe.qwen import (
    QwenVoice,
    DEFAULT_QWEN_VOICES,
    RECOMMENDED_VOICES,
    SUPPORTED_LANGUAGES,
)

# Get all voices for a language
zh_voices = QwenVoice.get_voices_for_language("zh")
print(f"Chinese voices: {[v.ui_name for v in zh_voices]}")
# Output: ['qwen-zh-f1', 'qwen-zh-f2', 'qwen-zh-m1', 'qwen-zh-m2']

# Get default voices
default_ja = DEFAULT_QWEN_VOICES["ja"]

# Get recommended voices (balanced selection)
recommended_de = RECOMMENDED_VOICES["de"]

# Check voice properties
voice = QwenVoice.QWEN_FR_M2
print(f"Language: {voice.language_code}")  # 'fr'
print(f"Gender: {voice.gender}")  # 'm'
print(f"Pitch: {voice.pitch_type}")  # 'bass'
print(f"UI name: {voice.ui_name}")  # 'qwen-fr-m2'

# Convert from UI name
voice = QwenVoice.from_ui_name("qwen-ko-f1")
```

### LMStudio Integration

For running Qwen3-TTS via LMStudio on Mac:

1. Download the model in LMStudio
2. Start the local server
3. Use the OpenAI-compatible API endpoint

```python
# Note: Direct LMStudio integration requires additional setup
# as LMStudio primarily supports text LLMs, not TTS models.
# For TTS, use the qwen-tts library directly as shown above.
```

## Troubleshooting

**Error: "Qwen TTS library not found"**
- Install the library: `pip install qwen-tts`

**Error: "MPS backend not available"**
- Ensure macOS 12.3+ and PyTorch 1.12+
- Check: `python -c "import torch; print(torch.backends.mps.is_available())"`

**Slow generation on Mac**
- First run downloads models (~4GB)
- Subsequent runs use cached models
- Ensure MPS is being used (check debug output)

**Out of memory**
- Use smaller model: `MODEL_CUSTOM_VOICE_SMALL` or `MODEL_BASE_SMALL`
- Close other applications
- Reduce batch size

**Poor audio quality**
- Try different voice (f2/m1 are recommended for balanced sound)
- Add emotion/style instructions via `instruct` parameter
- Use voice cloning with high-quality reference audio

**ffmpeg not found**
- Install ffmpeg: `brew install ffmpeg` (macOS)
- Or use `audio_format=AudioFormat.WAV`

## Performance

| Device | Model | Generation Speed |
|--------|-------|-----------------|
| M3 Pro | 1.7B | ~2-4 seconds/sentence |
| M3 Pro | 0.6B | ~1-2 seconds/sentence |
| RTX 4090 | 1.7B | ~0.5-1 second/sentence |
| CPU | 1.7B | ~10-20 seconds/sentence |

## References

- [Qwen3-TTS GitHub Repository](https://github.com/QwenLM/Qwen3-TTS)
- [Qwen Blog: Qwen3-TTS Announcement](https://qwen.ai/blog?id=qwen3tts-0115)
- [Hugging Face Demo](https://huggingface.co/spaces/Qwen/Qwen3-TTS-Demo)
- [Qwen TTS PyPI Package](https://pypi.org/project/qwen-tts/)
