# Per-Language Difficulty Level Overrides

## Overview

The Trakaido wordlist system now supports per-language difficulty level overrides. This allows different words to appear at different levels depending on the target language.

For example:
- 筷子 (chopsticks) can be level 2 in Chinese but level 10 in German
- Words can be excluded from specific languages entirely using level `-1`

## How It Works

### Default Behavior
Every `Lemma` has a `difficulty_level` field that serves as the default level across all languages.

### Language-Specific Overrides
The `LemmaDifficultyOverride` table stores language-specific exceptions:
- `lemma_id`: References the lemma
- `language_code`: Two-letter language code (e.g., 'zh', 'fr', 'de')
- `difficulty_level`: Override level (1-20) or -1 to exclude
- `notes`: Optional explanation for the override

### Effective Difficulty Level
When generating wordlists or exporting to WireWord format, the system:
1. Checks for a language-specific override
2. If found, uses the override level
3. Otherwise, uses the default `difficulty_level`
4. Excludes words with effective level of -1

## Database Schema

```sql
CREATE TABLE lemma_difficulty_overrides (
    id INTEGER PRIMARY KEY,
    lemma_id INTEGER NOT NULL REFERENCES lemmas(id),
    language_code TEXT NOT NULL,
    difficulty_level INTEGER NOT NULL,
    notes TEXT,
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(lemma_id, language_code)
);
```

## Usage

### Managing Overrides with CLI Tool

The `manage_difficulty_overrides.py` script provides a command-line interface:

```bash
# Set chopsticks to level 2 in Chinese
python src/wordfreq/tools/manage_difficulty_overrides.py set N01_123 zh 2 \
  --notes "Common eating utensil in Chinese culture"

# Exclude a word from German wordlists
python src/wordfreq/tools/manage_difficulty_overrides.py set N01_456 de -1 \
  --notes "Not relevant for German learners"

# View overrides for a specific word
python src/wordfreq/tools/manage_difficulty_overrides.py view N01_123

# List all overrides for Chinese
python src/wordfreq/tools/manage_difficulty_overrides.py list zh

# Import overrides from CSV
python src/wordfreq/tools/manage_difficulty_overrides.py import overrides.csv

# Export overrides to CSV
python src/wordfreq/tools/manage_difficulty_overrides.py export \
  --language zh --output zh_overrides.csv
```

### CSV Format for Bulk Import

```csv
guid,language_code,difficulty_level,notes
N01_001,zh,2,"Chopsticks are common in Chinese"
N01_001,de,10,"Less common in German culture"
N05_042,fr,-1,"Not used in French"
```

### Programmatic Access

```python
from wordfreq.storage.crud.difficulty_override import (
    add_difficulty_override,
    get_effective_difficulty_level,
    get_difficulty_override
)

# Add an override
add_difficulty_override(
    session=session,
    lemma_id=lemma.id,
    language_code='zh',
    difficulty_level=2,
    notes='Common word in Chinese'
)

# Get effective level for a language
effective_level = get_effective_difficulty_level(session, lemma, 'zh')

# Get a specific override
override = get_difficulty_override(session, lemma.id, 'zh')
```

## Impact on Wordlist Generation

### dict_generator.py
The `get_lemmas_by_subtype_and_level()` function now:
- Joins with `lemma_difficulty_overrides` table
- Uses `COALESCE` to prefer override over default
- Filters out words with level -1 for the target language

### export_manager.py / export_wireword.py
All export functions now:
- Use effective difficulty levels when filtering
- Exclude words marked with level -1
- Include the effective level in exported data

### ungurys.py (WireWord Export Agent)
The agent automatically uses effective levels for each language when exporting wordlists.

## Design Rationale

### Why Overrides Instead of Separate Levels?
- **Efficiency**: Most words use the default level
- **Maintainability**: Only store exceptions, not redundant data
- **Backward Compatibility**: Existing data continues to work
- **Clustering**: Words of the same subtype still cluster by default

### Why Level -1 for Exclusion?
- Clear semantic meaning: "not included"
- Allows filtering with simple SQL: `WHERE effective_level != -1`
- Distinguished from NULL (level not set) vs. -1 (explicitly excluded)

## Migration Notes

### Updating Existing Code
The changes are largely backward compatible:
- Lemmas without overrides behave exactly as before
- New filtering is transparent to most code

### Populating Initial Overrides
After deploying this feature:
1. Review words that should differ by language
2. Use the CLI tool or CSV import to add overrides
3. Re-generate wordlists for affected languages

## Examples of Good Override Candidates

### Cultural Items
- 筷子 (chopsticks): Early in Chinese/Korean, later in European languages
- Kimchi: Early in Korean, later elsewhere
- Baguette: Early in French, later elsewhere

### False Friends / Overlapping Meanings
- Lithuanian: eiti vs. vykti (both "to go")
- Chinese: 能 vs. 可以 (both "can/able")
- French: savoir vs. connaître (both "to know")

One word might be taught early (default level 3), the other later (override to level 8) in the same language.

### Technical or Specialized Terms
Some technical terms might be:
- Level 5 by default (general intermediate)
- Level -1 in languages where they're not commonly used
- Level 2 in languages where they're basic vocabulary

## Future Enhancements

Possible future improvements:
- UI for managing overrides in a web interface
- Automated suggestions based on frequency data per language
- Batch operations by subtype or pattern
- Override history/versioning for tracking changes
