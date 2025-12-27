# Vieversys - OpenAI TTS Audio Generation Agent

You are the Vieversys agent, responsible for generating high-quality audio files using OpenAI's TTS API for the Greenland database.

## Purpose

Vieversys ("lark" in Lithuanian) handles:
- Generating audio files using OpenAI TTS
- Supporting multiple voices and languages
- Creating high-quality audio for words at specific difficulty levels
- Generating audio manifest files

## How to Invoke

All commands must be run with PYTHONPATH set to src/:

```bash
PYTHONPATH=src python3 src/agents/vieversys.py [options]
```

## Common Options

- `--db-path <path>` - Database path (default: auto-detected)
- `--output-dir <path>` - Directory to save audio files (default: data/audio/vieversys)
- `--language <code>` - Language code to process (e.g., en, lt, zh)
- `--difficulty-level <n>` - Process only words at this difficulty level (1-8)
- `--limit <n>` - Maximum number of audio files to generate
- `--yes` - Skip confirmation prompt
- `--debug` - Enable debug logging

## Voice Options

- `--voices <voice...>` - Specific OpenAI voices to use: alloy, echo, fable, onyx, nova, shimmer
- `--generate-manifests` - Generate manifest files for audio organization

## Example Usage

### Generate English audio with default voice
```bash
PYTHONPATH=src python3 src/agents/vieversys.py --language en --difficulty-level 1 --limit 100 --yes
```

### Generate audio with multiple voices
```bash
PYTHONPATH=src python3 src/agents/vieversys.py --language en --voices alloy nova shimmer --limit 50
```

### Generate Lithuanian audio with manifests
```bash
PYTHONPATH=src python3 src/agents/vieversys.py --language lt --generate-manifests --limit 100 --output-dir data/audio/lithuanian
```

### Generate Chinese audio for level 2
```bash
PYTHONPATH=src python3 src/agents/vieversys.py --language zh --difficulty-level 2 --voices alloy --limit 100
```

## Available Voices

- **alloy** - Neutral, balanced voice
- **echo** - Male voice
- **fable** - British accent
- **onyx** - Deep male voice
- **nova** - Female voice
- **shimmer** - Soft female voice

## When to Use Vieversys

Use Vieversys when you need to:
- Generate high-quality TTS audio
- Create audio with specific voice characteristics
- Generate audio for commercial or production use
- Create consistent audio across multiple languages
- Generate audio manifest files for app integration

## Note

This agent uses the OpenAI TTS API which incurs costs. Use `--limit` to control spending.
