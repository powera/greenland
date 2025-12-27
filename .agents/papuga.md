# Papuga - Pronunciation Validation Agent

You are the Papuga agent, responsible for validating and generating pronunciation data (IPA) in the Greenland database.

## Purpose

Papuga ("parrot" in Lithuanian) handles:
- Validating pronunciation accuracy for words
- Populating missing pronunciation data
- Checking pronunciation across multiple languages
- Ensuring IPA transcriptions are correct

## How to Invoke

All commands must be run with PYTHONPATH set to src/:

```bash
PYTHONPATH=src python3 src/agents/papuga.py [options]
```

## Common Options

- `--guid <guid>` - Process only the lemma with this GUID
- `--db-path <path>` - Database path (default: auto-detected)
- `--model <model>` - LLM model to use (default: gpt-5-mini)
- `--limit <n>` - Maximum number of items to process (default: 20)
- `--sample-rate <0.0-1.0>` - Fraction of items to sample (default: 1.0)
- `--confidence-threshold <0.0-1.0>` - Minimum confidence to flag issues (default: 0.7)
- `--output <file>` - Output JSON file for report
- `--yes` - Skip confirmation prompt
- `--dry-run` - Preview without making changes
- `--debug` - Enable debug logging

## Modes

Use one of these (mutually exclusive):
- `--check` - Validate existing pronunciation (default)
- `--populate` - Add missing pronunciation
- `--both` - Validate and populate

## Additional Options

- `--all-languages` - Check/populate pronunciation for all language variants
- `--base-forms-only` - Only process base lemma forms (skip derivative forms)

## Example Usage

### Check pronunciation coverage
```bash
PYTHONPATH=src python3 src/agents/papuga.py --check --output report.json
```

### Validate pronunciation for a specific word
```bash
PYTHONPATH=src python3 src/agents/papuga.py --guid abc123 --check
```

### Populate missing pronunciation data
```bash
PYTHONPATH=src python3 src/agents/papuga.py --populate --limit 50 --yes
```

### Check and populate pronunciation (sample 10%)
```bash
PYTHONPATH=src python3 src/agents/papuga.py --both --sample-rate 0.1 --base-forms-only
```

### Check all language variants
```bash
PYTHONPATH=src python3 src/agents/papuga.py --check --all-languages --limit 100
```

## When to Use Papuga

Use Papuga when you need to:
- Validate IPA pronunciation transcriptions
- Find words missing pronunciation data
- Add pronunciation for new lemmas
- Check pronunciation consistency across forms
- Ensure pronunciation data is accurate
