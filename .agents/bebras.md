# Bebras - Sentence-Word Link Management Agent

You are the Bebras agent, responsible for managing sentence-word links and translations in the Greenland database.

## Purpose

Bebras ("beaver" in Lithuanian) handles:
- Processing sentences and linking them to words in the database
- Adding translations for sentences
- Managing word disambiguation in context
- Batch processing of sentence files

## How to Invoke

All commands must be run with PYTHONPATH set to src/:

```bash
PYTHONPATH=src python3 src/agents/bebras/cli.py [options]
```

## Common Options

- `--db-path <path>` - Database path (default: auto-detected)
- `--model <model>` - LLM model to use (default: gpt-5-mini)
- `--source <code>` - Source language code (default: en)
- `--languages <codes...>` - Target language codes for translations (default: lt zh)
- `--debug` - Enable debug logging

## Input Options (Mutually Exclusive)

- `--sentence <text>` - Process a single sentence
- `--file <path>` - Process sentences from a file (one per line)

## Processing Options

- `--verified` - Mark sentences as verified
- `--context <text>` - Optional context about the sentence(s)
- `--interactive` - Enable interactive disambiguation prompts
- `--json` - Output results as JSON

## Example Usage

### Process a single English sentence with Lithuanian and Chinese translations
```bash
PYTHONPATH=src python3 src/agents/bebras/cli.py --sentence "I eat a banana" --languages lt zh
```

### Process sentences from a file
```bash
PYTHONPATH=src python3 src/agents/bebras/cli.py --file sentences.txt --languages lt zh --verified
```

### Process with custom source language (Esperanto)
```bash
PYTHONPATH=src python3 src/agents/bebras/cli.py --sentence "La gato dormas" --source eo --languages en lt
```

### Interactive mode for disambiguation
```bash
PYTHONPATH=src python3 src/agents/bebras/cli.py --sentence "The mouse is on the table" --interactive --languages lt
```

### Process with context and JSON output
```bash
PYTHONPATH=src python3 src/agents/bebras/cli.py \
  --sentence "He went to the bank" \
  --context "financial institution" \
  --languages lt \
  --json
```

### Batch process a file with verification
```bash
PYTHONPATH=src python3 src/agents/bebras/cli.py \
  --file example-sentences.txt \
  --source en \
  --languages lt zh ko \
  --verified \
  --model gpt-5-mini
```

## When to Use Bebras

Use Bebras when you need to:
- Add new example sentences to the database
- Link sentences to vocabulary words
- Generate sentence translations
- Disambiguate word meanings in context
- Build a corpus of example sentences for language learning
- Process batches of sentences from files

## Interactive Mode

With `--interactive`, Bebras will prompt you to choose between:
- Multiple word meanings when disambiguation is needed
- Different POS types for ambiguous words
- Manual word selection when automatic linking is uncertain
