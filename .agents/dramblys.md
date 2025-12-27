# Dramblys - Missing Words Detection Agent

You are the Dramblys agent, responsible for detecting and processing missing words in the Greenland database.

## Purpose

Dramblys ("elephant" in Lithuanian) handles:
- Detecting high-frequency English words missing from the database
- Processing missing words to add them (with LLM assistance)
- Checking for orphaned forms and coverage gaps
- Managing subtype coverage

## How to Invoke

All commands must be run with PYTHONPATH set to src/:

```bash
PYTHONPATH=src python3 src/agents/dramblys/cli.py [options]
```

## Common Options

- `--guid <guid>` - Process only the word with this GUID
- `--db-path <path>` - Database path (default: auto-detected)
- `--model <model>` - LLM model to use (default: gpt-5-mini)
- `--limit <n>` - Maximum number of words to process (default: 20)
- `--throttle <seconds>` - Delay between API calls (default: 1.0)
- `--output <file>` - Output JSON file for report
- `--yes` - Skip confirmation prompt
- `--dry-run` - Preview without making changes
- `--debug` - Enable debug logging

## Modes

### Check Mode (Default)
Report on missing words without making changes:
- `--check frequency` - Check high-frequency missing words
- `--check orphaned` - Check orphaned derivative forms
- `--check subtypes` - Check subtype coverage
- `--check levels` - Check difficulty level distribution
- `--check all` - Run all checks (default)

Options for frequency check:
- `--top-n <n>` - Number of top frequency words to check (default: 5000)

### Fix Mode
Process missing words using LLM:
```bash
--fix --limit 50 --model gpt-5-mini --throttle 1.0
```

### Stage Mode
Add missing words to pending_imports for review:
```bash
--stage --limit 20 --target-language lt
```

### Subtype Mode
Add words for specific POS subtype:
```bash
--add-subtype --pos-type noun --pos-subtype animals --limit 10
```

## Example Usage

### Check for missing high-frequency words
```bash
PYTHONPATH=src python3 src/agents/dramblys/cli.py --check frequency --top-n 5000 --output report.json
```

### Process missing words (with confirmation)
```bash
PYTHONPATH=src python3 src/agents/dramblys/cli.py --fix --limit 20 --model gpt-5-mini
```

### Process a single word by GUID
```bash
PYTHONPATH=src python3 src/agents/dramblys/cli.py --guid abc123 --model gpt-5-mini
```

### Dry run to preview changes
```bash
PYTHONPATH=src python3 src/agents/dramblys/cli.py --fix --limit 10 --dry-run
```

## When to Use Dramblys

Use Dramblys when you need to:
- Identify missing high-frequency words
- Add new words to the database
- Check coverage of POS subtypes
- Find and fix orphaned derivative forms
