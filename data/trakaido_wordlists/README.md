# Trakaido Wordlists

A comprehensive collection of Lithuanian language wordlists for language learning applications.

## Overview

This package contains structured wordlists for Lithuanian language learning, including:

- **Nouns**: Organized by declension classes with full declension tables
- **Verbs**: Present, past, and future tense conjugations
- **Phrases**: Common expressions and conversational phrases
- **Audio batches**: Word lists organized for audio generation

## Installation

### From Git Repository (Recommended for development)

```bash
pip install git+https://github.com/your-username/trakaido-wordlists.git
```

### As a Git Submodule

```bash
git submodule add https://github.com/your-username/trakaido-wordlists.git wordlists
git submodule update --init --recursive
```

## Usage

### Basic Usage

```python
from trakaido_wordlists import all_words, get_all_word_pairs_flat

# Access all wordlists
print(all_words.keys())
# Output: dict_keys(['nouns_one', 'nouns_two', 'nouns_three', 'nouns_four', 'common_words', 'verbs_present', 'verbs_past', 'phrases_one'])

# Get a flat list of all word pairs
all_pairs = get_all_word_pairs_flat()
print(f"Total word pairs: {len(all_pairs)}")
```

### Accessing Specific Wordlists

```python
from trakaido_wordlists import nouns_one, phrases_one, verbs_present

# Access noun wordlists
print("First declension nouns:")
for group_name, words in nouns_one.items():
    print(f"  {group_name}: {len(words)} words")

# Access phrases
print("Greeting phrases:")
for phrase in phrases_one["Greetings"]:
    print(f"  {phrase['english']} -> {phrase['lithuanian']}")

# Access verb conjugations
print("Present tense verbs:")
for group_name, verbs in verbs_present.items():
    print(f"  {group_name}: {len(verbs)} verbs")
```

### Utility Functions

```python
from trakaido_wordlists import check_for_duplicates, find_missing_words

# Check for duplicate words across all wordlists
english_exact, english_semantic, lithuanian_exact, lithuanian_semantic = check_for_duplicates()
print(f"Found {len(english_exact)} exact English duplicates")

# Find words missing from your wordlists
missing = find_missing_words(["house", "car", "tree", "book"])
print(f"Missing words: {missing}")

# Or check against a file
missing = find_missing_words("my_word_list.txt")
```

## Data Structure

### Word Pairs
Most wordlists use this structure:
```python
{
    "english": "house",
    "lithuanian": "namas"
}
```

### Noun Declensions
Nouns include full declension tables:
```python
{
    "english": "house",
    "lithuanian": "namas",
    "declensions": {
        "nominative": {"singular": "namas", "plural": "namai"},
        "genitive": {"singular": "namo", "plural": "namų"},
        # ... other cases
    }
}
```

### Verb Conjugations
Verbs include conjugation tables:
```python
{
    "english": "to eat",
    "lithuanian": "valgyti",
    "present_tense": {
        "1s": {"english": "I eat", "lithuanian": "aš valgau"},
        "2s": {"english": "you eat", "lithuanian": "tu valgai"},
        # ... other persons
    }
}
```

## Wordlist Categories

- **nouns_one**: First declension nouns
- **nouns_two**: Second declension nouns  
- **nouns_three**: Third declension nouns
- **nouns_four**: Fourth declension nouns
- **common_words**: Frequently used vocabulary
- **verbs_present**: Present tense verb conjugations
- **verbs_past**: Past tense verb conjugations
- **phrases_one**: Common phrases and expressions

## Audio Batches

The package includes pre-organized word lists in the `audiobatches/` directory, useful for text-to-speech generation:

- `words1.txt` through `words5.txt`: Lithuanian words organized in batches

## Contributing

1. Fork the repository
2. Create a feature branch
3. Add your wordlists following the existing structure
4. Submit a pull request

## License

MIT License - see LICENSE file for details.

## Related Projects

This wordlist package is part of the Trakaido language learning ecosystem.