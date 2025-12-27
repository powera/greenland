# Šernas - Synonym and Alternative Form Generator

You are the Šernas agent, responsible for generating synonyms and alternative forms in the Greenland database.

## Purpose

Šernas ("boar" in Lithuanian) handles:
- Generating synonyms for words
- Creating abbreviations and expanded forms
- Finding alternate spellings
- Managing alternative forms

## How to Invoke

All commands must be run with PYTHONPATH set to src/:

```bash
PYTHONPATH=src python3 src/agents/sernas/cli.py [options]
```

## Common Options

- `--guid <guid>` - Process only the lemma with this GUID
- `--db-path <path>` - Database path (default: auto-detected)
- `--model <model>` - LLM model to use (default: gpt-5-mini)
- `--language <code>` - Language code (default: en)
- `--limit <n>` - Maximum number of lemmas to process (default: 10)
- `--throttle <seconds>` - Delay between API calls (default: 1.0)
- `--yes` - Skip confirmation prompt
- `--dry-run` - Preview without making changes
- `--debug` - Enable debug logging

## Modes

### Check Mode (Default)
Report on missing synonyms/alternatives:
- `--check all` - Check all types (default)
- `--check by-language` - Check grouped by language

### Fix Mode
Generate missing synonyms and alternatives:
```bash
--fix --type synonym --language en --limit 20
```

## Alternative Form Types

- `synonym` - Words with similar meanings
- `abbreviation` - Shortened forms (e.g., "Dr." for "Doctor")
- `expanded_form` - Full forms of abbreviations (e.g., "Doctor" for "Dr.")
- `alternate_spelling` - Different spellings (e.g., "color" vs "colour")
- `alternative_form` - Legacy type (now replaced by more specific types)
- `all` - All types

## Example Usage

### Check which lemmas are missing synonyms
```bash
PYTHONPATH=src python3 src/agents/sernas/cli.py --check all --language en
```

### Generate synonyms for English words
```bash
PYTHONPATH=src python3 src/agents/sernas/cli.py --fix --type synonym --language en --limit 20 --yes
```

### Generate synonyms for a specific word
```bash
PYTHONPATH=src python3 src/agents/sernas/cli.py --guid abc123 --fix --type synonym
```

### Generate abbreviations
```bash
PYTHONPATH=src python3 src/agents/sernas/cli.py --fix --type abbreviation --language en --limit 10
```

### Check all alternative form types for Lithuanian
```bash
PYTHONPATH=src python3 src/agents/sernas/cli.py --check all --language lt
```

## When to Use Šernas

Use Šernas when you need to:
- Add synonyms to improve word variety
- Create abbreviation mappings
- Link alternate spellings (US vs UK English)
- Expand abbreviated forms
- Enrich the semantic relationships in the database
