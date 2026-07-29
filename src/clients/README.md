# Clients - Unified LLM Interface

Abstraction layer for multiple LLM providers, used throughout the project for
translation, word form generation, sentence creation, and benchmarking.

## Providers

| Provider | Module | Models |
|----------|--------|--------|
| OpenAI | `clients/openai/` | GPT-4o, GPT-4o-mini, etc. |
| Anthropic | `clients/anthropic/` | Claude models |
| Google Gemini | `clients/gemini_client.py` | Gemini models |
| DigitalOcean | `clients/digitalocean_client.py` | Gradient serverless inference (multi-vendor) |
| Ollama | `clients/ollama_client.py` | Local models |
| LM Studio | `clients/lmstudio_client.py` | Local models |

## Usage

```python
from clients.unified_client import UnifiedLLMClient
from clients.types import Schema, SchemaProperty

client = UnifiedLLMClient()

# Simple text query
response = client.generate_chat(prompt="Translate 'hello' to French", model="gpt-4o")
print(response.response_text)

# Structured output with schema
schema = Schema(
    "Translation",
    "A word translation",
    {
        "translation": SchemaProperty("string", "The translated word"),
        "confidence": SchemaProperty("number", "Confidence score 0-1"),
    }
)
response = client.generate_chat(prompt="...", model="gpt-4o", json_schema=schema)
data = response.structured_data
```

`generate_chat` is the single entry point every backend implements; there is no
`query()` method. It returns a `clients.types.Response` with `response_text`
(text mode), `structured_data` (schema mode), `usage`, and `additional_thought`.

## Model routing

`UnifiedLLMClient` picks a backend from the model name:

| Model name | Backend |
|------------|---------|
| `do/...` | DigitalOcean |
| `gpt-...` (not `gpt-oss`) | OpenAI |
| `claude-...` | Anthropic |
| `gemini-...` | Gemini |
| anything else | database lookup: `lmstudio/...` path → LM Studio, otherwise Ollama |

### The `do/` prefix

DigitalOcean Gradient exposes one OpenAI-compatible endpoint fronting models
from many vendors, with flat ids that embed the vendor name
(`anthropic-claude-fable-5`, `openai-gpt-5.6-sol`, `llama-4-maverick`). Those
collide with the first-party prefixes above, so a DO-routed model is written
`do/<digitalocean-model-id>`:

```python
client.generate_chat(prompt="...", model="do/anthropic-claude-fable-5")
```

The router strips `do/` and sends the remainder verbatim as the `model` field.
A slash cannot appear in a first-party model id, so this branch is checked
first with no risk of shadowing; it also matches the existing `lmstudio/` path
convention in the `model` database table. Note that anything keyed on the model
name downstream (`MODEL_OUTPUT_CEILINGS` in `lib.py`, `CostConfig` in
`util/telemetry.py`) sees the *stripped* name and needs its own DO entries.

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
