# BEBRAS - Sentence-Word Link Management Agent

**Bebras** (Lithuanian for "beaver") manages the relationship between sentences and vocabulary words in the Greenland language learning system.

## Features

- **Sentence Analysis**: Uses LLM to extract key vocabulary words from sentences
- **Word Disambiguation**: Resolves ambiguous words (e.g., "mouse" → animal vs. computer)
- **Multi-language Support**: Generates translations for target languages (Chinese, Lithuanian, etc.)
- **Database Integrity**: Checks for orphaned records and data quality issues

## Architecture

```
bebras/
├── agent.py          # Core BebrasAgent class for sentence processing
├── cli.py            # Command-line interface
├── disambiguation.py # Word disambiguation logic
├── translation.py    # Translation management
└── integrity.py      # Database integrity checker
```

## Usage

### Sentence Processing

```bash
# Process a single sentence
python bebras.py --sentence "I eat a banana" --languages lt zh

# Process sentences from a file
python bebras.py --file sentences.txt --languages lt zh

# Custom source language
python bebras.py --sentence "La gato dormas" --source eo --languages en lt
```

### Database Integrity

```bash
# Run all integrity checks
python bebras.py --check-integrity

# Run specific check
python bebras.py --check-integrity --check orphaned
```

### Python API

```python
from agents.bebras import BebrasAgent

agent = BebrasAgent(model="gpt-5-mini")

# Process a sentence
result = agent.process_sentence(
    sentence_text="I eat a banana",
    source_language="en",
    target_languages=["lt", "zh"]
)

# Batch processing
batch_result = agent.process_sentence_batch(
    sentences=["The cat sleeps", "She reads a book"],
    source_language="en",
    target_languages=["lt", "zh"]
)
```

## How It Works

1. **Analysis**: LLM extracts content words with POS, role, and disambiguation hints
2. **Matching**: Searches database for matching lemmas, filtered by POS
3. **Disambiguation**: Uses context and LLM to resolve ambiguous matches
4. **Translation**: Generates natural translations in target languages
5. **Linking**: Creates records in `sentences`, `sentence_translations`, and `sentence_words` tables

## Database Schema

### Tables Used

- **sentences**: Pattern, tense, difficulty level
- **sentence_translations**: Translations in each language (en, lt, zh, etc.)
- **sentence_words**: Links to lemmas with position and grammatical metadata

## Configuration

| Argument | Description | Default |
|----------|-------------|---------|
| `--sentence` | Single sentence to process | Required* |
| `--file` | File with sentences (one per line) | Required* |
| `--source` | Source language code | `en` |
| `--languages` | Target language codes | `lt zh` |
| `--model` | LLM model to use | `gpt-5-mini` |
| `--verified` | Mark sentences as verified | `False` |
| `--debug` | Enable debug logging | `False` |
| `--json` | Output results as JSON | `False` |

*One of `--sentence` or `--file` is required.

## Supported Languages

Default: Lithuanian (`lt`), Chinese (`zh`)

Also supported: English, French, Korean, Swahili, Vietnamese, German, Spanish, Japanese

## Disambiguation

When multiple lemmas match a word, BEBRAS:
1. Filters by part of speech
2. Prefers exact text matches
3. Uses LLM-provided disambiguation hints
4. Falls back to LLM selection between candidates

## Error Handling

- **No matching lemma**: Creates `SentenceWord` with `lemma_id=NULL`
- **Translation failure**: Logs error, continues with other languages
- **Database errors**: Rolls back transaction, returns error details
