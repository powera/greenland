# Benchmarks: Getting Started

## Prerequisites

- Python 3.12+ with PYTHONPATH set to `src/`
- API keys in `keys/` directory: `openai.key`, `anthropic.key`, `google.key`
- For local models: LM Studio running on the configured server

## Initial Setup

All commands assume you are in the project root directory.

### 1. Create the database

This creates the SQLite database at `src/benchmarks/schema/benchmarks.db`
with all required tables (model, benchmark, question, run, run_detail).

```bash
PYTHONPATH=src python src/benchmarks/schema/load_schema.py
```

### 2. Register models

This populates the model table with remote API models (OpenAI, Anthropic,
Gemini) and local models (TranslateGemma). To add or change models, edit
`src/benchmarks/schema/create_models.py`.

```bash
PYTHONPATH=src python src/benchmarks/schema/create_models.py
```

### 3. Generate benchmark questions

Each benchmark needs its questions loaded into the database before it can
be run. Questions are generated from JSON files in each benchmark directory.

```bash
# Generate for a specific benchmark
PYTHONPATH=src python src/benchmarks/run_benchmark.py generate 0016_antonym

# Available benchmarks: 0016_antonym, 0020_definitions, 0018_pinyin_letters, 0062_sentence_decomposition
```

### 4. Run a benchmark

```bash
# Run a single benchmark against a model
PYTHONPATH=src python src/benchmarks/run_benchmark.py run 0016_antonym claude-haiku-4-5

# Run all missing benchmark/model combinations
PYTHONPATH=src python src/benchmarks/run_benchmark.py missing
```

### 5. View results

```bash
# List available benchmarks
PYTHONPATH=src python src/benchmarks/run_benchmark.py list

# List registered models
PYTHONPATH=src python src/benchmarks/run_benchmark.py models

# Web dashboard
./launch_server.sh
# Visit http://localhost:5556/dashboard
```

## Rebuilding the database

If you need to start fresh (e.g. after model changes), delete the database
and repeat steps 1-3:

```bash
rm src/benchmarks/schema/benchmarks.db
PYTHONPATH=src python src/benchmarks/schema/load_schema.py
PYTHONPATH=src python src/benchmarks/schema/create_models.py
PYTHONPATH=src python src/benchmarks/run_benchmark.py generate 0016_antonym
PYTHONPATH=src python src/benchmarks/run_benchmark.py generate 0020_definitions
PYTHONPATH=src python src/benchmarks/run_benchmark.py generate 0018_pinyin_letters
PYTHONPATH=src python src/benchmarks/run_benchmark.py generate 0062_sentence_decomposition
```

Note: this will discard all previous run results.

## Adding a new model

1. Add an `insert_model()` call in `src/benchmarks/schema/create_models.py`
2. Rebuild the database (see above), or run `create_models.py` against an
   existing database (new models will be added; existing ones are unchanged)
3. The `model_path` field determines routing:
   - `gpt-*` routes to OpenAI
   - `claude-*` routes to Anthropic
   - `gemini-*` routes to Gemini
   - `lmstudio/*` routes to LM Studio
   - `translategemma/*` routes to TranslateGemma
   - Everything else routes to Ollama

## Current registered models

**Remote:**
- `gpt-5.2`, `gpt-5.4-mini`, `gpt-5-mini`, `gpt-5-nano` (OpenAI)
- `claude-opus-4-6`, `claude-sonnet-4-5`, `claude-haiku-4-5` (Anthropic)
- `gemini-2.5-pro`, `gemini-2.5-flash`, `gemini-2.5-flash-lite` (Google)

**Local:**
- `translategemma-3-4b` (TranslateGemma)
