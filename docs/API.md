# BARSUKAS REST API Documentation

## Overview

BARSUKAS provides a read-only REST API for accessing lemma (word) information from the multilingual linguistic database. All endpoints return JSON responses and use the `/api/v1/` prefix.

## Base URL

```
http://<host>:<port>/api/v1/
```

## Authentication

Currently, no authentication is required. The API is read-only.

## Common Response Format

All successful responses follow this format:

```json
{
  "data": { ... },
  "metadata": { ... }
}
```

Error responses:

```json
{
  "error": "Error message description"
}
```

## Endpoints

### 1. API Information

**GET** `/api/v1`

Get information about the API and available endpoints.

**Example Response:**
```json
{
  "version": "1.0",
  "description": "Read-only API for accessing lemma information",
  "endpoints": [ ... ]
}
```

### 2. Search Lemmas

**GET** `/api/v1/search`

Search for lemmas by keyword across multiple fields (lemma text, definition, disambiguation, and translations).

**Parameters:**
- `q` (query, required): Search query string
- `pos_type` (query, optional): Filter by part of speech (e.g., `noun`, `verb`)
- `difficulty` (query, optional): Filter by difficulty level (1-20, `-1` for excluded, `null` for not set)
- `limit` (query, optional): Maximum number of results to return (default: 20, max: 100)
- `offset` (query, optional): Number of results to skip for pagination (default: 0)

**Example Request:**
```
GET /api/v1/search?q=tire
GET /api/v1/search?q=dog&pos_type=noun&difficulty=1
GET /api/v1/search?q=gyventi&limit=10&offset=0
```

**Example Response:**
```json
{
  "data": [
    {
      "guid": "N01_234",
      "lemma_text": "tire",
      "definition": "A rubber covering around a wheel",
      "pos_type": "noun",
      "pos_subtype": "small_movable_object",
      "difficulty_level": 5,
      "disambiguation": "wheel component",
      "translations": {
        "zh": "轮胎",
        "fr": "pneu",
        "lt": "padanga"
      },
      "verified": true
    },
    {
      "guid": "V03_156",
      "lemma_text": "tire",
      "definition": "To become weary or fatigued",
      "pos_type": "verb",
      "pos_subtype": "physical_state",
      "difficulty_level": 3,
      "disambiguation": "to become weary",
      "translations": {
        "zh": "疲劳",
        "fr": "se fatiguer",
        "lt": "pavargti"
      },
      "verified": true
    }
  ],
  "metadata": {
    "query": "tire",
    "total_results": 2,
    "limit": 20,
    "offset": 0,
    "returned": 2,
    "has_more": false
  }
}
```

**Fields:**
- `guid`: The lemma's unique identifier
- `lemma_text`: The lemma's base form (in English)
- `definition`: The English definition (truncated to 200 chars if longer)
- `pos_type`: Part of speech type
- `pos_subtype`: Part of speech subtype (or `null`)
- `difficulty_level`: Difficulty level (or `null`)
- `disambiguation`: Disambiguation text to distinguish homonyms (or `null`)
- `translations`: Sample of available translations (up to 3 languages shown)
- `verified`: Whether the lemma has been verified

**Metadata:**
- `query`: The search query that was used
- `total_results`: Total number of matching results (before pagination)
- `limit`: The limit parameter used
- `offset`: The offset parameter used
- `returned`: Number of results in this response
- `has_more`: Whether there are more results available
- `next_offset`: The offset value to use for the next page (if `has_more` is true)

**Notes:**
- Results are ordered by relevance: exact matches first, then starts-with, then contains
- The search is case-insensitive
- For lemmas with many translations, only a sample (up to 3) is shown. Use the `/api/v1/lemma/<guid>/translations` endpoint to get all translations
- Use the `disambiguation` field to distinguish between homonyms (e.g., "tire" the noun vs "tire" the verb)

### 3. Get Lemma Information

**GET** `/api/v1/lemma/<guid>`

Get basic information about a lemma by its GUID (e.g., `N01_001`, `V02_015`).

**Parameters:**
- `guid` (path, required): The lemma's unique identifier

**Example Request:**
```
GET /api/v1/lemma/N01_001
```

**Example Response:**
```json
{
  "data": {
    "guid": "N01_001",
    "lemma_text": "dog",
    "definition": "A domesticated carnivorous mammal",
    "pos_type": "noun",
    "pos_subtype": "animal",
    "difficulty_level": 1,
    "verified": true,
    "tags": null,
    "disambiguation": null
  }
}
```

**Fields:**
- `guid`: The lemma's unique identifier
- `lemma_text`: The lemma's base form (in English)
- `definition`: The English definition
- `pos_type`: Part of speech type (noun, verb, adjective, etc.)
- `pos_subtype`: Part of speech subtype (if populated, otherwise `null`)
- `difficulty_level`: Difficulty level (1-20, or -1 for excluded, or `null` if not set)
- `verified`: Whether the lemma has been human-verified
- `tags`: JSON array of tags (or `null` if not set)
- `disambiguation`: Disambiguation text (or `null`)

### 3. Get Lemma Translations

**GET** `/api/v1/lemma/<guid>/translations`

Get translations of a lemma in various languages.

**Parameters:**
- `guid` (path, required): The lemma's unique identifier
- `language` (query, optional): Filter to a specific language code (e.g., `zh`, `fr`, `lt`)

**Example Request:**
```
GET /api/v1/lemma/N01_001/translations
GET /api/v1/lemma/N01_001/translations?language=zh
```

**Example Response:**
```json
{
  "data": {
    "zh": "狗",
    "fr": "chien",
    "lt": "šuo",
    "ko": "개"
  },
  "metadata": {
    "guid": "N01_001",
    "available_languages": ["zh", "fr", "lt", "ko", "es", "de"]
  }
}
```

**Notes:**
- Only populated translations are returned (unpopulated languages are omitted)
- The `metadata.available_languages` field lists all languages with translations
- When filtering by language, `metadata.is_populated` indicates if that language has a translation

### 4. Get Lemma Forms

**GET** `/api/v1/lemma/<guid>/forms`

Get derivative/declined forms of a lemma (conjugations, declensions, etc.).

**Parameters:**
- `guid` (path, required): The lemma's unique identifier
- `language` (query, optional): Filter to a specific language code (e.g., `zh`, `fr`, `lt`)

**Example Request:**
```
GET /api/v1/lemma/V01_001/forms
GET /api/v1/lemma/V01_001/forms?language=lt
```

**Example Response:**
```json
{
  "data": [
    {
      "form_text": "gyventi",
      "language_code": "lt",
      "grammatical_form": "infinitive",
      "is_base_form": true,
      "ipa_pronunciation": "/ɡʲiːˈvʲɛnʲtʲɪ/",
      "phonetic_pronunciation": null,
      "verified": true
    },
    {
      "form_text": "gyvenu",
      "language_code": "lt",
      "grammatical_form": "1s_present",
      "is_base_form": false,
      "ipa_pronunciation": "/ɡʲiːˈvʲɛnʊ/",
      "phonetic_pronunciation": null,
      "verified": true
    }
  ],
  "metadata": {
    "guid": "V01_001",
    "count": 2,
    "languages_present": ["lt"]
  }
}
```

**Fields:**
- `form_text`: The actual derivative form
- `language_code`: Language of this form
- `grammatical_form`: The grammatical form (e.g., "gerund", "1st_person_singular_present")
- `is_base_form`: Whether this is the base/dictionary form
- `ipa_pronunciation`: IPA pronunciation (or `null` if not populated)
- `phonetic_pronunciation`: Phonetic pronunciation (or `null` if not populated)
- `verified`: Whether this form has been verified

### 5. Get Lemma Grammar Facts

**GET** `/api/v1/lemma/<guid>/grammar`

Get grammar facts about a lemma (e.g., gender, plurale tantum, declension class).

**Parameters:**
- `guid` (path, required): The lemma's unique identifier
- `language` (query, optional): Filter to a specific language code (e.g., `zh`, `fr`, `lt`)

**Example Request:**
```
GET /api/v1/lemma/N05_012/grammar
GET /api/v1/lemma/N05_012/grammar?language=lt
```

**Example Response:**
```json
{
  "data": [
    {
      "language_code": "lt",
      "fact_type": "gender",
      "fact_value": "masculine",
      "notes": null,
      "verified": true
    },
    {
      "language_code": "lt",
      "fact_type": "declension",
      "fact_value": "1",
      "notes": null,
      "verified": true
    }
  ],
  "metadata": {
    "guid": "N05_012",
    "count": 2,
    "languages_present": ["lt"]
  }
}
```

**Fields:**
- `language_code`: Language this fact applies to
- `fact_type`: Type of grammatical fact (e.g., "gender", "number_type", "declension")
- `fact_value`: The value of this fact (e.g., "masculine", "plurale_tantum", "1")
- `notes`: Any additional notes (or `null`)
- `verified`: Whether this fact has been verified

**Common fact types:**
- `gender`: masculine, feminine, neuter
- `number_type`: plurale_tantum (scissors, pants), singulare_tantum (information, furniture)
- `declension`: declension class (1, 2, 3, etc.)
- `defective_verb`: missing certain conjugations
- `indeclinable`: doesn't decline/conjugate

### 6. Get Lemma Example Sentences

**GET** `/api/v1/lemma/<guid>/sentences`

Get example sentences that use this lemma.

**Parameters:**
- `guid` (path, required): The lemma's unique identifier
- `language` (query, optional): Filter sentence translations to a specific language code

**Example Request:**
```
GET /api/v1/lemma/V01_001/sentences
GET /api/v1/lemma/V01_001/sentences?language=lt
```

**Example Response:**
```json
{
  "data": [
    {
      "sentence_id": 123,
      "translations": {
        "en": "I live in a house",
        "lt": "Aš gyvenu name"
      },
      "minimum_level": 1,
      "pattern_type": "SVO",
      "tense": "present",
      "verified": true,
      "word_info": [
        {
          "position": 1,
          "part_of_speech": "verb",
          "english_text": "live",
          "target_language_text": "gyventi",
          "grammatical_form": "1s_present",
          "declined_form": "gyvenu",
          "language_code": "lt"
        }
      ]
    }
  ],
  "metadata": {
    "guid": "V01_001",
    "count": 1
  }
}
```

**Fields:**
- `sentence_id`: The sentence's database ID
- `translations`: Dictionary mapping language codes to sentence text
- `minimum_level`: Minimum difficulty level needed to understand this sentence (or `null`)
- `pattern_type`: Sentence pattern type (or `null` if not populated)
- `tense`: Sentence tense (or `null` if not populated)
- `verified`: Whether this sentence has been verified
- `word_info`: Information about how this lemma is used in the sentence
  - `position`: Word position in the sentence (0-indexed)
  - `part_of_speech`: Lexical category (e.g., "noun", "verb", "pronoun"); this
    is not the syntactic role (subject/object).
  - `english_text`: English form of the word
  - `target_language_text`: Base form in target language
  - `grammatical_form`: Grammatical form used (e.g., "1s_present")
  - `declined_form`: Actual form used in the sentence
  - `language_code`: Language code

## Error Responses

### 404 Not Found

Returned when a GUID doesn't exist in the database.

```json
{
  "error": "Lemma with GUID 'INVALID_GUID' not found"
}
```

### 400 Bad Request

Returned for invalid requests.

```json
{
  "error": "Invalid parameter value"
}
```

## Data Semantics

### Null vs False vs Absent

The API distinguishes between different states of data:

1. **`null`**: The field hasn't been populated yet, or is intentionally empty
2. **`false`**: The field is explicitly set to false (for boolean fields)
3. **Absent**: The field doesn't exist in the response (e.g., unpopulated translations are omitted from the translations endpoint)

### Language Codes

The API uses ISO 639-1 language codes:
- `en`: English
- `zh`: Chinese
- `fr`: French
- `lt`: Lithuanian
- `ko`: Korean
- `es`: Spanish
- `de`: German
- `pt`: Portuguese
- `sw`: Swahili
- `vi`: Vietnamese

## Future Enhancements

The current version is read-only. Future versions may include:
- Write endpoints (POST/PUT/DELETE) for authenticated users
- Batch operations for retrieving multiple lemmas
- Search and filtering capabilities
- Pagination for large result sets
- Rate limiting and API keys
