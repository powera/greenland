# Barsukas - Word Frequency Database Web Editor

**Barsukas** (Lithuanian for "badger") is a lightweight Flask web interface for manual edits and fixes to the linguistics database. It provides a user-friendly way to manage lemmas, translations, and difficulty levels without directly editing the database.

## Features

### Core Functionality
- **Browse and Search Lemmas** - Paginated list with search and filtering
- **Edit Lemma Details** - Update lemma text, definitions, POS types, and base difficulty levels
- **Manage Translations** - Edit translations across 9 supported languages with automatic storage handling
- **Difficulty Overrides** - Set per-language difficulty level overrides for Trakaido wordlists
- **Operation Logging** - All changes are automatically logged to the `operation_logs` table

### Supported Languages
- Chinese (zh)
- French (fr)
- Spanish (es)
- German (de)
- Portuguese (pt)
- Korean (ko)
- Swahili (sw)
- Lithuanian (lt)
- Vietnamese (vi)

## Installation

```bash
cd src/wordfreq/barsukas
pip install -r requirements.txt
```

## Usage

### Start the Server

Use the provided launch script which sets up the Python path correctly:

```bash
cd src/wordfreq/barsukas
./launch.sh
```

The web interface will be available at: **http://127.0.0.1:5555**

### Custom Configuration

You can pass command-line arguments to the launch script:

```bash
# Custom port
./launch.sh --port 8080

# Enable debug mode
./launch.sh --debug
```

Or use environment variables:

```bash
export BARSUKAS_PORT=8080
export BARSUKAS_DB_PATH=/path/to/linguistics.sqlite
./launch.sh
```

**Note:** The launch script automatically sets `PYTHONPATH` to include the `src/` directory, allowing proper imports of the `wordfreq` module.

## Validation Rules

### Difficulty Levels
- Must be **-1** (exclude from language) OR **1-20** (Trakaido levels)
- Empty/null means no difficulty level is set
- Per-language overrides take precedence over the base difficulty level

### Translations
- **Warning displayed** if translation contains "/" character (but still allowed to save)
- Translation cannot be empty
- Automatically uses correct storage (Lemma column vs LemmaTranslation table)

## How It Works

### Database Initialization
On startup, Barsukas automatically:
- Creates any missing tables (like `lemma_difficulty_overrides` if it doesn't exist)
- Adds any missing columns to existing tables
- Uses SQLAlchemy's `Base.metadata.create_all()` to ensure schema is up-to-date

This means you don't need to manually run migrations - the app will set up what it needs.

### Translation Storage
The application automatically handles the transition from legacy column-based translations to the newer `LemmaTranslation` table:
- Languages using **Lemma columns**: Chinese, French, Korean, Swahili, Lithuanian, Vietnamese
- Languages using **LemmaTranslation table**: Spanish, German, Portuguese

You don't need to worry about which storage method is used - the `translation_helpers` module handles it automatically.

### Difficulty Overrides
- **Base Difficulty Level**: Set on the lemma (applies to all languages by default)
- **Per-Language Override**: Override the base level for specific languages
- **Effective Level**: The final level used for a language (override takes precedence)

Example:
- Base level: 5
- Chinese override: 2 → Chinese uses level 2
- German override: -1 → German excludes this word
- French: (no override) → French uses base level 5

### Operation Logging
All changes are logged to `operation_logs` table with:
- **Source**: `barsukas-web-interface`
- **Operation Type**: `translation`, `lemma_update`, `difficulty_override_add`, etc.
- **Fact JSON**: Contains old/new values and metadata
- **Entity IDs**: Links to affected lemma, language, etc.

## Security

Barsukas binds to **127.0.0.1** (localhost only) by default. This means:
- ✅ Only accessible from the same machine
- ✅ No authentication needed (local-only access is sufficient)
- ❌ Not accessible from other machines on the network
- ❌ Not suitable for production deployment without additional security

## Troubleshooting

### Database Not Found
```
Error: Database not found at /path/to/linguistics.sqlite
```
**Solution**: Set the correct database path:
```bash
export BARSUKAS_DB_PATH=/Users/powera/repo/greenland/src/wordfreq/data/linguistics.sqlite
python app.py
```

### Port Already in Use
```
OSError: [Errno 48] Address already in use
```
**Solution**: Use a different port:
```bash
python app.py --port 5556
```

## Architecture

```
barsukas/
├── app.py              # Flask application entry point
├── config.py           # Configuration settings
├── routes/             # Blueprint routes
│   ├── lemmas.py       # Lemma CRUD operations
│   ├── translations.py # Translation management
│   └── overrides.py    # Difficulty override management
├── templates/          # Jinja2 HTML templates
│   ├── base.html       # Base layout
│   ├── index.html      # Home page
│   └── lemmas/         # Lemma-related templates
├── static/             # CSS and JavaScript
└── requirements.txt    # Python dependencies
```

## Dependencies

- **Flask 3.0.0** - Web framework
- **SQLAlchemy 2.0.23** - Database ORM (reuses existing models)

## Possible Future Features

The following features are not currently implemented but could be added:

- [ ] Add new lemmas via web interface
- [ ] View operation log history for a specific lemma
- [ ] Bulk translation operations (update multiple translations at once)
- [ ] Export lemma data as JSON
- [ ] Search by translation text (not just lemma text)
- [ ] Advanced filtering (by verified status, confidence range, etc.)
- [ ] Undo recent changes
- [ ] Batch import translations from CSV/JSON
- [ ] Audit trail viewer (who changed what and when)
- [ ] Readonly mode (view-only access)
- [ ] API endpoints for programmatic access

## Contributing

This tool is for internal use in the Greenland project. Changes should:
- Maintain operation logging for all edits
- Follow the existing validation rules
- Use the `translation_helpers` module for translation operations
- Use the `difficulty_override` CRUD functions for override management

## License

Part of the Greenland project.
