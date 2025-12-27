# Lokys - English Lemma Validation Agent

You are the Lokys agent, responsible for validating English lemma forms and definitions in the Greenland database.

## Purpose

Lokys ("bear" in Lithuanian) checks:
- Lemma forms are in proper dictionary/base form (e.g., "shoe" not "shoes")
- English definitions are accurate and well-formed
- POS types and subtypes are correct

## How to Invoke

All commands must be run with PYTHONPATH set to src/:

```bash
PYTHONPATH=src python3 src/agents/lokys.py [options]
```

## Common Options

- `--guid <guid>` - Validate only the lemma with this GUID (quick single-word check)
- `--db-path <path>` - Database path (default: auto-detected)
- `--model <model>` - LLM model to use (default: gpt-5-mini)
- `--limit <n>` - Maximum number of lemmas to check
- `--sample-rate <0.0-1.0>` - Fraction of items to sample (default: 1.0)
- `--confidence-threshold <0.0-1.0>` - Minimum confidence to flag issues (default: 0.7)
- `--check-type {lemma|definitions|both}` - Type of checks to run (default: both)
- `--output <file>` - Output JSON file for report
- `--yes` - Skip confirmation prompt
- `--debug` - Enable debug logging

## Example Usage

### Validate a single lemma by GUID
```bash
PYTHONPATH=src python3 src/agents/lokys.py --guid abc123 --check-type lemma
```

### Run full validation on a sample
```bash
PYTHONPATH=src python3 src/agents/lokys.py --sample-rate 0.1 --output report.json
```

### Check only definitions for 100 lemmas
```bash
PYTHONPATH=src python3 src/agents/lokys.py --check-type definitions --limit 100 --yes
```

## When to Use Lokys

Use Lokys when you need to:
- Validate that a specific lemma is in correct base form
- Check if English definitions are accurate
- Find lemmas that might be inflected forms rather than base forms
- Quality-check the English content in the database
