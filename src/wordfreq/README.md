# WordFreq Database Initialization Guide

This guide explains how to initialize all parts of the wordfreq database system, which provides word frequency analysis, linguistic processing, and translation capabilities for the Greenland project.

## Overview

The wordfreq system consists of three main components that need to be initialized:

1. **Word frequency data** - Corpus-based frequency rankings from various sources
2. **Static word data** - Curated word lists from `nouns.py` with translations
3. **LLM-generated translations** - AI-powered linguistic analysis and translations

## Prerequisites

Before initializing the database, ensure you have:

- Python 3.9+ installed
- All project dependencies installed (`pip install -r requirements.txt`)
- Access to LLM services (OpenAI, Anthropic, etc.) for translation generation
- SQLite database file at the configured path

## Step 1: Load and Calculate WordFreq Data

The first step is to populate the database with word frequency data from various corpora.

### Quick Start (Recommended)

Use the simplified loader that handles all corpora automatically:

```bash
# From the project root directory
python -c "
from wordfreq.frequency.corpus import load_all_corpora
results = load_all_corpora()
```

### Available Corpora

The system includes these pre-configured corpora:

- **19th_books**: Word frequencies from 19th century books
- **20th_books**: Word frequencies from 20th century books  
- **subtitles**: Frequencies from movie and TV subtitles (SUBTLEX)
- **wiki_vital**: Frequencies from Wikipedia vital articles
- **cooking**: Frequencies from various recipes

### What This Step Does

1. Creates database tables if they don't exist
2. Loads word frequency data from JSON/text files in `src/wordfreq/data/`
3. Processes and normalizes word tokens (lowercase, filters numerals)
4. Calculates frequency ranks and harmonic mean rankings
5. Stores data in the `WordToken`, `Corpus`, and `WordFrequency` tables

## Step 2: Load the "nouns.py" Data

The second step imports curated static word lists with predefined translations and categories.

### Run the Migration Script

```bash
# From the project root directory
python3 wordfreq/trakaido/migrate_static_data.py
```

### What This Step Does

1. Reads static word data from `trakaido/nouns.py`
2. Creates or updates `Lemma` records for each word
3. Sets Lithuanian translations on lemmas
4. Creates language-specific derivative forms
5. Assigns progress levels (1-7) and categories
6. Generates unique GUIDs for each word
7. Links words to frequency data from Step 1

### Data Structure

The `nouns.py` file contains hierarchical word lists:

```python
nouns_one = {
  "Food + Drink": [
    { "english": "bread", "lithuanian": "duona" },
    { "english": "water", "lithuanian": "vanduo" },
    # ...
  ],
  "Plants + Animals": [
    # ...
  ]
}
```

## Step 3: Run LLM Queries to Generate Translations

The final step uses AI language models to generate detailed linguistic analysis and translations.

### Process All Words

```python
from wordfreq.translation.processor import WordProcessor

# Initialize processor with default settings
processor = WordProcessor()

# Process all words that need analysis
results = processor.process_all_words(limit=1000, skip_processed=True)

print(f"Processed {results['successful']}/{results['total']} words successfully")
```

### Process Specific Words

```python
from wordfreq.translation.client import LinguisticClient

# Initialize client
client = LinguisticClient.get_instance()

# Process individual words
success = client.process_word("example")
if success:
    print("Word processed successfully")
```

### Batch Processing

```python
# Process multiple words efficiently
word_list = ["apple", "banana", "orange"]
results = client.process_words_batch(word_list, throttle=2.0)

print(f"Batch results: {results}")
```

### What This Step Does

1. Queries LLM services for detailed word analysis
2. Generates part-of-speech classifications
3. Creates definitions and usage examples
4. Generates translations to target languages
5. Stores results in `Definition`, `Translation`, and related tables
6. Handles rate limiting and error recovery

### Configuration

LLM processing can be configured via these parameters:

- **Model**: Choose LLM model (GPT-4, Claude, etc.)
- **Batch size**: Number of words per batch (default: 128)
- **Threads**: Parallel processing threads (default: 4)
- **Throttle**: Delay between API calls (default: 3.0 seconds)
- **Max retries**: Retry failed requests (default: 1)

## Verification

After initialization, verify the database contains data:

```python
from wordfreq.storage.database import create_database_session
from wordfreq.storage.models.schema import WordToken, Lemma, Definition

session = create_database_session()

# Check word tokens
word_count = session.query(WordToken).count()
print(f"Word tokens: {word_count}")

# Check lemmas  
lemma_count = session.query(Lemma).count()
print(f"Lemmas: {lemma_count}")

# Check definitions
def_count = session.query(Definition).count()
print(f"Definitions: {def_count}")
```

## Troubleshooting

### Logs

Enable detailed logging:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Database Reset

To start fresh, delete the database file:

```bash
rm /path/to/linguistics.sqlite
```

Then re-run the initialization process.

## File Locations

- **Database**: `src/wordfreq/data/linguistics.sqlite`
- **Corpus data**: `src/wordfreq/data/*.json`, `src/wordfreq/data/*.txt`
- **Static words**: `src/wordfreq/trakaido/nouns.py`
- **Configuration**: `src/wordfreq/frequency/corpus.py`
- **Migration script**: `src/wordfreq/trakaido/migrate_static_data.py`

## Next Steps

After initialization, you can:

- Generate trakaido wordlists using `dict_generator.py`
- Export word data using scripts in `wordfreq/dictionary/`
- Run frequency analysis using `wordfreq/frequency/analysis.py`
- Review and edit translations using the web interface