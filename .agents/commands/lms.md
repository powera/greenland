# LM Studio CLI (`lms`) and HTTP Server API

LM Studio provides a local LLM inference server with a CLI tool (`lms`) and a REST API.
The server runs on `localhost:1234` by default and supports native, OpenAI-compatible,
and Anthropic-compatible endpoints.

## CLI: `lms`

The `lms` binary ships with LM Studio and is added to PATH on first launch.
Use `lms --help` for a full list of commands.

### Model Management

```bash
lms chat                        # Interactive chat with a loaded model
lms get <query>                 # Search and download models (from Hugging Face / LM Studio Hub)
lms load <model_key>            # Load a model into memory
lms load <model_key> --gpu 0.5  # Load with 50% GPU offload
lms load <model_key> --gpu max  # Full GPU offload
lms unload <model_key>          # Unload a model from memory
lms unload --all                # Unload all models
lms ls                          # List models on disk
lms ls --json                   # List models on disk (JSON)
lms ls --variants               # Show all quantization variants
lms ps                          # List currently loaded models
lms ps --json                   # List loaded models (JSON)
lms import <path>               # Import an external GGUF/MLX model file
```

### Server Control

```bash
lms server start                # Start the HTTP API server (default port 1234)
lms server start --port <port>  # Start on a specific port
lms server stop                 # Stop the server
lms status                      # Check LM Studio status
lms log                         # Stream live request/response logs (useful for debugging)
```

### Headless / Daemon Mode

```bash
lms daemon up                   # Start the LM Studio daemon (no GUI required)
```

### Runtime & Development

```bash
lms runtime                     # Manage inference runtime (llama.cpp, MLX)
lms login                       # Authenticate with LM Studio Hub
lms clone <artifact>            # Clone an artifact from Hub
lms push                        # Upload artifact in current dir to Hub
lms dev                         # Start plugin dev server with hot-reload
```

---

## HTTP Server API

If authentication is enabled, include `Authorization: Bearer $LM_API_TOKEN` in requests.

### Base URL

All examples below use `${LOCALHOST}` as the base URL. Set this to your LM Studio
server address (default `http://localhost:1234`):

```bash
export LOCALHOST="http://localhost:1234"
```

### API Layers

| Prefix           | Description                                           |
| ---------------- | ----------------------------------------------------- |
| `/api/v1/*`      | **Native v1 REST API** (recommended, LM Studio 0.4+) |
| `/api/v0/*`      | Native v0 REST API (legacy, enhanced stats)           |
| `/v1/*`          | OpenAI-compatible endpoints                           |
| `/v1/messages`   | Anthropic-compatible endpoint                         |

### When to Use Which API

- **Status / inspection operations** (list models, check loaded state, get model info):
  Prefer the **v0 API** (`/api/v0/*`). It returns richer metadata including model state
  (`loaded` / `not-loaded`), architecture, quantization, and max context length.
- **Query / inference operations** (chat, completions, embeddings, tool use):
  Prefer the **v1 API** (`/api/v1/*`). It supports stateful chats, MCP, structured output,
  and streaming with the latest features.

---

### Native v1 REST API (`/api/v1`)

#### Chat with a Model

```
POST /api/v1/chat
```

```json
{
  "model": "openai/gpt-oss-20b",
  "input": "Who are you, and what can you do?"
}
```

Supports stateful chats, MCP tool use, streaming, structured output (JSON schema),
and embeddings. See https://lmstudio.ai/docs/developer/rest for full details.

---

### Native v0 REST API (`/api/v0`)

Responses include extra `stats` (tokens/sec, TTFT) and `model_info` fields.

#### List Models

```
GET /api/v0/models
```

Returns all loaded and downloaded models with type, arch, quantization, state, and max context length.

#### Get Model Info

```
GET /api/v0/models/{model_id}
```

#### Chat Completions

```
POST /api/v0/chat/completions
```

```json
{
  "model": "granite-3.0-2b-instruct",
  "messages": [
    { "role": "system", "content": "Always answer in rhymes." },
    { "role": "user", "content": "Introduce yourself." }
  ],
  "temperature": 0.7,
  "max_tokens": -1,
  "stream": false
}
```

#### Text Completions

```
POST /api/v0/completions
```

```json
{
  "model": "granite-3.0-2b-instruct",
  "prompt": "the meaning of life is",
  "temperature": 0.7,
  "max_tokens": 10,
  "stream": false,
  "stop": "\n"
}
```

#### Text Embeddings

```
POST /api/v0/embeddings
```

```json
{
  "model": "text-embedding-nomic-embed-text-v1.5",
  "input": "Some text to embed"
}
```

---

### OpenAI-Compatible Endpoints (`/v1`)

Drop-in replacement for the OpenAI API. Point any OpenAI client at `http://localhost:1234/v1`.

| Method | Endpoint                | Description                          |
| ------ | ----------------------- | ------------------------------------ |
| GET    | `/v1/models`            | List models                          |
| POST   | `/v1/chat/completions`  | Chat completions (text + images)     |
| POST   | `/v1/completions`       | Text completions (legacy)            |
| POST   | `/v1/embeddings`        | Text embeddings                      |
| POST   | `/v1/responses`         | Responses API (stateful, MCP, tools) |

#### Python Example (OpenAI SDK)

```python
from openai import OpenAI

client = OpenAI(base_url=f"{LOCALHOST}/v1", api_key="lm-studio")

response = client.chat.completions.create(
    model="<model-identifier>",
    messages=[{"role": "user", "content": "Say this is a test!"}],
    temperature=0.7,
)
print(response.choices[0].message.content)
```

#### Tool / Function Calling

Supported via `/v1/chat/completions` and `/v1/responses`. Pass tools in the `tools`
parameter using the same schema as OpenAI's Function Calling API.

#### MCP via Responses API

```bash
curl ${LOCALHOST}/v1/responses \
  -H "Content-Type: application/json" \
  -d '{
    "model": "openai/gpt-oss-20b",
    "tools": [{
      "type": "mcp",
      "server_label": "my-mcp",
      "server_url": "https://example.com/mcp",
      "allowed_tools": ["some_tool"]
    }],
    "input": "Use the tool to answer my question."
  }'
```

---

### Anthropic-Compatible Endpoint

```
POST /v1/messages
```

Uses the same request/response format as the Anthropic Messages API.

---

## Key Features

- **Streaming**: Set `"stream": true` on any completion endpoint to receive SSE events.
- **Structured Output**: JSON schema support via OpenAI-compatible endpoints.
- **Stateful Chats**: Pass `previous_response_id` in `/v1/responses` to continue a session.
- **Idle TTL / Auto-Evict**: Models can be automatically unloaded after a period of inactivity.
- **Authentication**: Enable via Developer settings; uses `LM_API_TOKEN` env var as Bearer token.

## Useful Links

- Docs: https://lmstudio.ai/docs/developer
- REST API Reference: https://lmstudio.ai/docs/developer/rest
- CLI Reference: https://lmstudio.ai/docs/cli
- API Changelog: https://lmstudio.ai/docs/developer/api-changelog
