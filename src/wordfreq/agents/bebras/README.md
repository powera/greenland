# BEBRAS - Sentence-Word Link Management Agent

**Bebras** (Lithuanian for "beaver") is an agent that manages the relationship between sentences and vocabulary words in the Greenland language learning system.

## Features

- **Sentence Analysis**: Uses LLM to extract key vocabulary words from sentences
- **Word Disambiguation**: Resolves ambiguous words (e.g., "mouse" → animal vs. computer)
- **Multi-language Support**: Automatically generates translations for target languages
- **Database Integration**: Creates proper links between sentences and lemmas
- **Batch Processing**: Process multiple sentences efficiently

## Architecture

```
bebras/
├── __init__.py          # Package exports
├── agent.py             # Core BebrasAgent class
├── cli.py               # Command-line interface
├── disambiguation.py    # Word disambiguation logic
└── translation.py       # Translation management
```

## Usage

### Command Line

```bash
# Process a single sentence with Lithuanian and Chinese translations
python src/wordfreq/agents/bebras.py \
    --sentence "I eat a banana" \
    --languages lt zh

# Process sentences from a file
python src/wordfreq/agents/bebras.py \
    --file sentences.txt \
    --languages lt zh

# With custom source language
python src/wordfreq/agents/bebras.py \
    --sentence "La gato dormas" \
    --source eo \
    --languages en lt

# Debug mode with JSON output
python src/wordfreq/agents/bebras.py \
    --sentence "The mouse is on the table" \
    --languages lt zh \
    --debug \
    --json
```

### Python API

```python
from wordfreq.agents.bebras import BebrasAgent

# Initialize agent
agent = BebrasAgent(model="gpt-5-mini", debug=True)

# Process a single sentence
result = agent.process_sentence(
    sentence_text="I eat a banana",
    source_language="en",
    target_languages=["lt", "zh"],
    context="Simple present tense example",
    verified=False
)

if result['success']:
    print(f"Sentence ID: {result['sentence_id']}")
    print(f"Linked words: {result['linked_words']}")
    print(f"Minimum level: {result['minimum_level']}")

# Batch processing
sentences = [
    "The cat sleeps on the mat",
    "She reads a book",
    "They play soccer"
]

batch_result = agent.process_sentence_batch(
    sentences=sentences,
    source_language="en",
    target_languages=["lt", "zh"]
)

print(f"Processed: {batch_result['success_count']}/{batch_result['total']}")
```

## How It Works

### 1. Sentence Analysis

The agent uses an LLM to analyze the sentence and extract:
- Content words (nouns, verbs, adjectives, adverbs)
- Part of speech for each word
- Role in the sentence (subject, verb, object, etc.)
- Grammatical form
- Disambiguation hints for ambiguous words

### 2. Word Matching

For each extracted word, BEBRAS:
1. Searches the database for matching lemmas
2. Filters by part of speech
3. If multiple candidates exist, uses disambiguation hints
4. Falls back to LLM-based disambiguation if needed

### 3. Translation Generation

For each target language:
1. Generates natural, idiomatic translations using LLM
2. Ensures grammatical correctness
3. Stores translations in the `sentence_translations` table

### 4. Database Linking

Creates records in:
- `sentences`: Sentence metadata (pattern, tense, difficulty)
- `sentence_translations`: Translations in each language
- `sentence_words`: Links to lemmas with position and grammatical info

## Configuration

### Command-line Arguments

| Argument | Description | Default |
|----------|-------------|---------|
| `--sentence` | Single sentence to process | Required* |
| `--file` | File with sentences (one per line) | Required* |
| `--source` | Source language code | `en` |
| `--languages` | Target language codes | `lt zh` |
| `--model` | LLM model to use | `gpt-5-mini` |
| `--verified` | Mark sentences as verified | `False` |
| `--context` | Context about the sentence | None |
| `--debug` | Enable debug logging | `False` |
| `--json` | Output results as JSON | `False` |

*One of `--sentence` or `--file` is required.

### Environment

BEBRAS uses the following from the environment:
- Database path: `constants.WORDFREQ_DB_PATH`
- LLM configuration: Via `UnifiedLLMClient`

## Supported Languages

Default target languages:
- `lt` - Lithuanian
- `zh` - Chinese (Mandarin)

Additional supported languages:
- `en` - English
- `fr` - French
- `ko` - Korean
- `sw` - Swahili
- `vi` - Vietnamese
- `de` - German
- `es` - Spanish
- `ja` - Japanese

## Database Schema

### Tables Used

**sentences**
- `id`: Primary key
- `pattern_type`: Sentence pattern (SVO, SVAO, etc.)
- `tense`: Verb tense (present, past, future)
- `minimum_level`: Calculated difficulty level
- `source_filename`: Source tracking
- `verified`: Verification status

**sentence_translations**
- `sentence_id`: Foreign key to sentences
- `language_code`: Language code (en, lt, zh, etc.)
- `translation_text`: Translated sentence text

**sentence_words**
- `sentence_id`: Foreign key to sentences
- `lemma_id`: Foreign key to lemmas (nullable)
- `language_code`: Language code
- `position`: Word position (0-indexed)
- `word_role`: Semantic role (subject, verb, object)
- `english_text`: English form
- `target_language_text`: Target language lemma
- `grammatical_form`: Grammatical form
- `grammatical_case`: Grammatical case
- `declined_form`: Actual form used in sentence

## Examples

### Example 1: Simple Sentence

Input: "I eat a banana"

Analysis:
- Pattern: SVO
- Tense: present
- Words:
  - eat (verb) → links to lemma "eat"
  - banana (noun) → links to lemma "banana"

Output:
- Sentence record created
- English translation: "I eat a banana"
- Lithuanian translation: "Aš valgau bananą"
- Chinese translation: "我吃香蕉"
- 2 word links created

### Example 2: Ambiguous Word

Input: "The mouse is on the table"

Analysis:
- Pattern: SVC
- Tense: present
- Words:
  - mouse (noun) - disambiguation: "computer device" or "animal"
  - table (noun)

Disambiguation:
- Uses context from full sentence
- LLM determines likely meaning
- Links to appropriate lemma variant

### Example 3: Batch Processing

Input file `sentences.txt`:
```
The cat sleeps on the mat
She reads a book
They play soccer
```

Result:
- 3 sentences created
- Each with Lithuanian and Chinese translations
- All words linked to existing lemmas
- Minimum difficulty calculated for each

## Disambiguation

When multiple lemmas match a word, BEBRAS:

1. **Filters by POS**: Narrows candidates by part of speech
2. **Exact match**: Prefers exact text matches
3. **Uses hints**: Applies LLM-provided disambiguation hints
4. **LLM disambiguation**: Calls LLM to select best candidate
5. **Default**: Falls back to first candidate if all else fails

Example disambiguation for "mouse":
```python
Candidates:
1. mouse (animal): A small rodent
2. mouse (computer): A pointing device for computers

Context: "on the table"
Selected: #2 (computer mouse more likely on table)
```

## Error Handling

BEBRAS handles errors gracefully:

- **No matching lemma**: Creates SentenceWord with `lemma_id=NULL`
- **Translation failure**: Logs error, continues with other languages
- **LLM timeout**: Returns error, doesn't commit partial data
- **Database errors**: Rolls back transaction, returns error

## Performance

- **Single sentence**: ~5-10 seconds (includes LLM calls)
- **Batch processing**: More efficient due to session reuse
- **Concurrent processing**: Not currently supported

## Future Enhancements

Potential improvements:
- Interactive disambiguation mode
- Confidence scoring for word matches
- Support for multi-word expressions
- Phonetic analysis for pronunciation
- Grammar pattern recognition
- Sentence similarity detection

## Related Agents

- **ZVIRBLIS**: Generates example sentences for vocabulary words
- **GANDRAS**: (Future) Grammar analysis and rule generation
- **BEBRAS_OLD**: Original database integrity checker

## License

Part of the Greenland language learning system.
