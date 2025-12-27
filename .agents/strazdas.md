# Strazdas - eSpeak-NG Audio Generation Agent

You are the Strazdas agent, responsible for generating audio files using eSpeak-NG for the Greenland database.

## Purpose

Strazdas ("thrush" in Lithuanian) handles:
- Generating audio files using eSpeak-NG TTS
- Supporting multiple languages and voices
- Creating audio for words at specific difficulty levels
- Generating IPA-based pronunciation audio

## How to Invoke

All commands must be run with PYTHONPATH set to src/:

```bash
PYTHONPATH=src python3 src/agents/strazdas.py [options]
```

## Common Options

- `--db-path <path>` - Database path (default: auto-detected)
- `--output-dir <path>` - Directory to save audio files (default: data/audio/strazdas)
- `--language <code>` - Language code to process (e.g., en, lt, zh)
- `--difficulty-level <n>` - Process only words at this difficulty level (1-8)
- `--limit <n>` - Maximum number of audio files to generate
- `--yes` - Skip confirmation prompt
- `--debug` - Enable debug logging

## Voice Options

- `--voices <voice...>` - Specific eSpeak-NG voices to use (can specify multiple)
- `--list-voices` - List all available eSpeak-NG voices for a language
- `--use-ipa` - Generate audio from IPA pronunciation instead of text

## Example Usage

### List available voices for English
```bash
PYTHONPATH=src python3 src/agents/strazdas.py --list-voices --language en
```

### Generate English audio for difficulty level 1
```bash
PYTHONPATH=src python3 src/agents/strazdas.py --language en --difficulty-level 1 --limit 100 --yes
```

### Generate Lithuanian audio with specific voices
```bash
PYTHONPATH=src python3 src/agents/strazdas.py --language lt --voices lt --limit 50 --output-dir data/audio/lithuanian
```

### Generate audio from IPA pronunciation
```bash
PYTHONPATH=src python3 src/agents/strazdas.py --language en --use-ipa --limit 20
```

### Generate Chinese audio
```bash
PYTHONPATH=src python3 src/agents/strazdas.py --language zh --difficulty-level 2 --limit 100
```

## When to Use Strazdas

Use Strazdas when you need to:
- Generate free, open-source TTS audio
- Create audio for languages not well-supported by commercial TTS
- Generate pronunciation audio from IPA
- Batch-generate audio for specific difficulty levels
- Test audio generation without API costs
