# VOVERE Agent - Data Import Agent

**"Vovere"** means "squirrel" in Lithuanian - gathering and storing things for later!

## Purpose

The VOVERE agent is responsible for importing trakaido vocabulary data from JSON exports into the wordfreq database. It was created to replace the `json_to_database.py` script and follows the established agent pattern used throughout the wordfreq system.

## Key Features

- **JSON Import**: Loads vocabulary data from JSON files
- **GUID-based Management**: Uses GUIDs to track and update vocabulary entries
- **Validation**: Validates JSON structure before import
- **Alternative Forms**: Automatically creates alternative word forms (e.g., "bike" for "bicycle")
- **Dry Run Support**: Can validate without making changes
- **Separation of Concerns**: Core vocabulary data is separate from difficulty levels

## JSON Format

### Expected Format for `exported_nouns.json`

The VOVERE agent expects a JSON file with the following structure:

```json
[
  {
    "English": "house",
    "Lithuanian": "namas",
    "GUID": "N07_001",
    "POS": "noun",
    "subtype": "building_structure"
  },
  {
    "English": "cat",
    "Lithuanian": "katė",
    "GUID": "N01_001",
    "POS": "noun",
    "subtype": "animal"
  }
]
```

### Required Fields

- **English**: English word (may contain parenthetical information like "orange (fruit)")
- **Lithuanian**: Lithuanian translation
- **GUID**: Global Unique Identifier (format: `[CATEGORY][NUMBER]_[SEQUENCE]`, e.g., `N07_001`)
- **POS**: Part of speech (noun, verb, adjective, adverb, pronoun, preposition, conjunction, interjection, determiner, article, numeral, auxiliary, modal)
- **subtype**: POS subtype (e.g., building_structure, animal, food_drink, etc.)

### Optional/Deprecated Fields

- **trakaido_level**: This field should **NOT** be in the `exported_nouns.json` file. Difficulty levels should be stored in a separate file (see below).

### Valid POS Types

- `noun` - Nouns (person, place, thing)
- `verb` - Verbs (actions)
- `adjective` - Adjectives (descriptive words)
- `adverb` - Adverbs (manner, time, place)
- `pronoun` - Pronouns (I, you, he, she, it, etc.)
- `preposition` - Prepositions (in, on, at, etc.)
- `conjunction` - Conjunctions (and, but, or, etc.)
- `interjection` - Interjections (oh, wow, etc.)
- `determiner` - Determiners (the, a, some, etc.)
- `article` - Articles (a, an, the)
- `numeral` - Numbers (one, two, first, second, etc.)
- `auxiliary` - Auxiliary verbs (be, have, do)
- `modal` - Modal verbs (can, could, should, etc.)

## Difficulty Levels

Difficulty levels (trakaido_level) should be stored in a **separate JSON file** that maps GUIDs to difficulty levels:

### Example: `trakaido_levels.json`

```json
{
  "N07_001": 1,
  "N07_002": 1,
  "N01_001": 2,
  "N01_002": 3
}
```

This separation allows:
- Core vocabulary data to be managed independently
- Difficulty levels to be updated without regenerating the entire export
- Different difficulty level schemes for different use cases

## Usage

### Standalone Usage

#### Check Database State
```bash
python src/wordfreq/agents/vovere.py --check
```

#### Import Data (Dry Run)
```bash
python src/wordfreq/agents/vovere.py --import-file src/wordfreq/trakaido/exported_nouns.json --dry-run
```

#### Import Data
```bash
python src/wordfreq/agents/vovere.py --import-file src/wordfreq/trakaido/exported_nouns.json
```

#### Import with Difficulty Levels
```bash
python src/wordfreq/agents/vovere.py --import-file exported_nouns.json --levels trakaido_levels.json
```

#### Debug Mode
```bash
python src/wordfreq/agents/vovere.py --import-file exported_nouns.json --debug
```

#### Save Report
```bash
python src/wordfreq/agents/vovere.py --import-file exported_nouns.json --output import_report.json
```

### Integration with PRADZIA

VOVERE is integrated with the PRADZIA (beginning) agent for database initialization:

```bash
# Bootstrap database with vocabulary data
python src/wordfreq/agents/pradzia.py --bootstrap src/wordfreq/trakaido/exported_nouns.json

# Bootstrap with difficulty levels
python src/wordfreq/agents/pradzia.py --bootstrap exported_nouns.json --levels trakaido_levels.json

# Dry run to preview changes
python src/wordfreq/agents/pradzia.py --bootstrap exported_nouns.json --dry-run
```

## How VOVERE Works

### Import Process

1. **Load and Validate**: Reads JSON file and validates structure
2. **Process Each Entry**:
   - Clean English word (remove parenthetical info)
   - Look for existing lemma by GUID
   - Create or update lemma with English and Lithuanian text
   - Set POS type and subtype
   - Apply difficulty level if provided
   - Create English derivative form
   - Create alternative forms (e.g., "bike" for "bicycle")
3. **Commit Changes**: Saves all changes to database
4. **Report Results**: Provides detailed statistics

### GUID-Based Updates

VOVERE uses GUIDs as the primary key for identifying vocabulary entries. This means:

- If a lemma with the same GUID exists, it will be **updated**
- If no lemma with the GUID exists, it will be **created**
- This allows the same import to be run multiple times safely (idempotent)

### Alternative Forms

VOVERE automatically creates alternative forms for common words:

- `bicycle` → `bike`
- `telephone` → `phone`
- `television` → `TV`
- `refrigerator` → `fridge`
- etc.

These alternatives are linked to the main lemma and inherit its properties.

## Integration with Other Agents

VOVERE is typically used early in the data pipeline:

1. **PRADZIA** - Initializes database and imports vocabulary via VOVERE
2. **BEBRAS** - Checks database integrity after import
3. **VILKAS** - Generates Lithuanian word forms for imported vocabulary
4. **VORAS** - Validates translations
5. **PAPUGA** - Generates pronunciations
6. **POVAS** - Creates HTML pages
7. **UNGURYS** - Exports to WireWord format

## Migration from json_to_database.py

The VOVERE agent replaces the older `json_to_database.py` script. Key differences:

### Old Approach (json_to_database.py)
- Standalone script
- Required `trakaido_level` in JSON
- Direct function calls
- Limited reporting

### New Approach (VOVERE Agent)
- Follows agent pattern
- Separates difficulty levels into separate file
- CLI with argparse
- Comprehensive JSON reporting
- Better integration with other agents
- Dry-run support

### Backward Compatibility

The current `exported_nouns.json` file still contains `trakaido_level` fields. VOVERE will:
- Issue a warning if it sees `trakaido_level` in the JSON
- Continue to work with the old format
- Recommend moving to the new separated format

## Error Handling

VOVERE includes comprehensive error handling:

- **File Not Found**: Clear error if JSON file doesn't exist
- **Invalid JSON**: Reports JSON parsing errors
- **Missing Fields**: Lists which entries are missing required fields
- **Invalid POS Types**: Reports invalid part-of-speech values
- **Database Errors**: Rolls back changes on failure

## Default File Path

The default JSON file path is: `src/wordfreq/trakaido/exported_nouns.json`

If no file path is specified, VOVERE will look for the file at this location.

## Output Reports

VOVERE generates detailed JSON reports with:

- Timestamp
- File path
- Validation results
- Import statistics (created, updated, failed)
- Alternative forms created
- Duration
- Error messages (if any)

Example output:
```json
{
  "timestamp": "2025-10-27T10:30:00",
  "json_path": "exported_nouns.json",
  "dry_run": false,
  "total_entries": 500,
  "successful_imports": 498,
  "created": 450,
  "updated": 48,
  "failed_imports": 2,
  "alternatives_created": 25,
  "duration_seconds": 12.5
}
```

## Future Enhancements

Potential improvements for VOVERE:

- Support for multiple file formats (CSV, YAML)
- Incremental imports (only process changed entries)
- Rollback capability
- Import from remote URLs
- Automatic backup before import
- Integration with version control for vocabulary tracking
