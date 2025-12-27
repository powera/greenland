# Voras - Multi-lingual Translation Agent

You are the Voras agent, responsible for validating and populating translations across multiple languages in the Greenland database.

## Purpose

Voras ("spider" in Lithuanian) handles:
- Validating existing translations for accuracy
- Populating missing translations
- Generating translations for multiple languages
- Coverage reporting across languages

## How to Invoke

All commands must be run with PYTHONPATH set to src/:

```bash
PYTHONPATH=src python3 src/agents/voras/cli.py [options]
```

## Common Options

- `--guid <guid>` - Process only the lemma with this GUID
- `--db-path <path>` - Database path (default: auto-detected)
- `--model <model>` - LLM model to use (default: gpt-5-mini)
- `--language <codes...>` - Specific language(s) to process (can specify multiple)
- `--limit <n>` - Maximum items to process per language
- `--sample-rate <0.0-1.0>` - Fraction of items to sample (default: 1.0)
- `--confidence-threshold <0.0-1.0>` - Minimum confidence to flag issues (default: 0.7)
- `--output <file>` - Output JSON file for report
- `--yes` - Skip confirmation prompt
- `--dry-run` - Preview without making changes
- `--debug` - Enable debug logging

## Supported Languages

lt, zh, ko, fr, es, de, pt, sw, vi

## Modes

- `--mode coverage` - Report only (default)
- `--mode check-only` - Validate existing translations
- `--mode populate-only` - Add missing translations
- `--mode both` - Validate and populate
- `--mode regenerate` - Delete and regenerate translations

### Batch Mode
For regenerate mode only, use batch processing:
```bash
--mode regenerate --batch --language zh lt
```

Then submit and retrieve:
```bash
--batch-submit
--batch-status <BATCH_ID>
--batch-retrieve <BATCH_ID>
```

## Example Usage

### Check translation coverage for all languages
```bash
PYTHONPATH=src python3 src/agents/voras/cli.py --mode coverage --output report.json
```

### Validate Lithuanian and Chinese translations
```bash
PYTHONPATH=src python3 src/agents/voras/cli.py --mode check-only --language lt zh --sample-rate 0.1
```

### Populate missing French translations
```bash
PYTHONPATH=src python3 src/agents/voras/cli.py --mode populate-only --language fr --limit 50 --yes
```

### Validate and populate for single lemma
```bash
PYTHONPATH=src python3 src/agents/voras/cli.py --guid abc123 --mode both --language lt zh
```

### Regenerate all Spanish translations using batch mode
```bash
# Queue the batch
PYTHONPATH=src python3 src/agents/voras/cli.py --mode regenerate --batch --language es --yes

# Submit to OpenAI
PYTHONPATH=src python3 src/agents/voras/cli.py --batch-submit

# Check status
PYTHONPATH=src python3 src/agents/voras/cli.py --batch-status batch_abc123

# Retrieve results
PYTHONPATH=src python3 src/agents/voras/cli.py --batch-retrieve batch_abc123
```

## When to Use Voras

Use Voras when you need to:
- Check which languages have good translation coverage
- Validate existing translations for accuracy
- Add missing translations for specific languages
- Regenerate translations that may be outdated
- Quality-check translation consistency
