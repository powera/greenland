# Clients - Unified LLM Interface

Abstraction layer for multiple LLM providers, used throughout the project for
translation, word form generation, sentence creation, and benchmarking.

## Providers

| Provider | Module | Models |
|----------|--------|--------|
| OpenAI | `clients/openai/` | GPT-4o, GPT-4o-mini, etc. |
| Anthropic | `clients/anthropic/` | Claude models |
| Google Gemini | `clients/gemini_client.py` | Gemini models |
| Ollama | `clients/ollama_client.py` | Local models |
| LM Studio | `clients/lmstudio_client.py` | Local models |

## Usage

```python
from clients.unified_client import UnifiedLLMClient
from clients.types import Schema, SchemaProperty

client = UnifiedLLMClient()

# Simple text query
response = client.query(prompt="Translate 'hello' to French", model="gpt-4o")

# Structured output with schema
schema = Schema(
    "Translation",
    "A word translation",
    {
        "translation": SchemaProperty("string", "The translated word"),
        "confidence": SchemaProperty("number", "Confidence score 0-1"),
    }
)
response = client.query(prompt="...", model="gpt-4o", schema=schema)
data = response.structured_data
```

The client routes requests to the correct provider based on model name prefix.

## Key Components

- **`unified_client.py`** - `UnifiedLLMClient` that routes to the right provider
- **`types.py`** - `Schema`, `SchemaProperty`, and `Response` dataclasses shared across providers
- **`lib.py`** - Schema conversion utilities for provider-specific formats
- **`keys.py`** - API key loading from `keys/` directory
- **`batch_queue.py`** - Batch request queue with SQLite tracking (OpenAI batch API)

## Additional Clients

### Audio (`clients/audio/`)

OpenAI TTS client for pronunciation audio generation. Used by the Vieversys
agent and the Barsukas audio routes.

- `openai_tts.py` - TTS API client
- `gpt_voices.py` - Voice configuration and language mappings
- `s3_uploader.py` - Upload generated audio to S3
- `audio_acceptance.py` - Validation for generated audio files

### Wiktionary (`clients/wiktionary/`)

Client for the Wiktionary API, used to fetch word forms and linguistic data.
Feeds into `langtools` parsers for structured extraction.

### Batch Processing (`clients/openai/batch_client.py`)

Support for OpenAI's batch API for high-volume, lower-cost requests. Managed
through `batch_queue.py` which tracks request lifecycle in a local SQLite database.

## API Keys

Keys are loaded from the `keys/` directory (gitignored) by `keys.py`. Each
provider expects its key in a separate file.
