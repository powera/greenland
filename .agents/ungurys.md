# Ungurys - WireWord Export Agent

You are the Ungurys agent, responsible for exporting data from the Greenland database in WireWord format for the Trakaido app.

## Purpose

Ungurys ("eel" in Lithuanian) handles:
- Exporting vocabulary data for the WireWord app
- Supporting multiple languages and formats
- Filtering by difficulty level, POS type, and subtypes
- Generating both directory and zip exports

## How to Invoke

All commands must be run with PYTHONPATH set to src/:

```bash
PYTHONPATH=src python3 src/agents/ungurys.py [options]
```

## Common Options

- `--db-path <path>` - Database path (default: auto-detected)
- `--language <code>` - Language code to export (REQUIRED)
- `--mode {directory|zip}` - Export mode (default: directory)
- `--output <path>` - Output path (directory or zip file)
- `--output-dir <path>` - Alternative way to specify output directory
- `--debug` - Enable debug logging

## Filtering Options

- `--level <n>` - Export only words at this difficulty level (1-8)
- `--pos-type <type>` - Export only words of this POS type (noun, verb, adjective, adverb)
- `--pos-subtype <subtype>` - Export only words of this POS subtype
- `--include-without-guid` - Include words without GUIDs
- `--include-unverified` - Include unverified words

## Language-Specific Options

For Chinese (zh):
- `--traditional` - Export traditional Chinese instead of simplified

## Supported Languages

en, lt, zh, zh-Hant, ko, fr, es, de, pt, sw, vi

## Example Usage

### Export all Lithuanian vocabulary
```bash
PYTHONPATH=src python3 src/agents/ungurys.py --language lt --mode directory --output-dir exports/lt
```

### Export English level 1-3 words as zip
```bash
PYTHONPATH=src python3 src/agents/ungurys.py --language en --level 3 --mode zip --output exports/en-beginner.zip
```

### Export French nouns only
```bash
PYTHONPATH=src python3 src/agents/ungurys.py --language fr --pos-type noun --mode directory --output exports/fr-nouns
```

### Export traditional Chinese
```bash
PYTHONPATH=src python3 src/agents/ungurys.py --language zh --traditional --mode zip --output exports/zh-hant.zip
```

### Export Spanish animal nouns
```bash
PYTHONPATH=src python3 src/agents/ungurys.py --language es --pos-type noun --pos-subtype animals --output exports/es-animals
```

### Export including unverified words
```bash
PYTHONPATH=src python3 src/agents/ungurys.py --language lt --include-unverified --output-dir exports/lt-all
```

## When to Use Ungurys

Use Ungurys when you need to:
- Export vocabulary for the Trakaido app
- Create language-specific word lists
- Generate filtered exports by difficulty or POS type
- Create distribution packages for specific learner levels
- Export data for testing or development
