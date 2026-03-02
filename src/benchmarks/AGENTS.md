# Benchmarks System

Automated evaluation framework for comparing language model performance on
linguistic tasks. Designed to test both remote API models (OpenAI, Anthropic,
Gemini) and local models (LM Studio, Ollama, TranslateGemma).

## How it works

1. **Benchmarks** define a task (e.g. "identify the antonym"). Each has a
   generator that produces questions and a runner that scores model responses.
2. **Questions** are generated from curated data files and stored in SQLite.
3. **Runners** send questions to models via the unified LLM client, evaluate
   responses, and store scored results.
4. **The web dashboard** displays results across models and benchmarks.

## Key directories

- `lib/generators/` - question generation per benchmark
- `lib/runners/` - benchmark execution and scoring per benchmark
- `lib/utils/` - base classes: `BenchmarkRunner`, `BenchmarkGenerator`
- `datastore/` - SQLAlchemy models and DB access
- `schema/` - database setup scripts (see `schema/GETTING_STARTED.md`)
- `server/` - Flask web UI for viewing results
- `0016_antonym/`, `0062_sentence_decomposition/`, etc. - test data per benchmark

## Adding a new benchmark

1. Create a directory `NNXX_name/` with test data (JSON)
2. Add a generator in `lib/generators/` using the `@generator` decorator
3. Add a runner in `lib/runners/` using the `@runner` decorator
4. Register metadata with the `@benchmark` decorator in either file
5. Generate questions: `run_benchmark.py generate NNXX_name`

See existing benchmarks (e.g. `0016_antonym`) for examples.

## Model path naming conventions

LM Studio model entries in the database use these fields:

- `model_path`: `"lmstudio/<org>/<model-name>"` — e.g.
  `"lmstudio/lmstudio-community/Qwen3-4B-GGUF/Qwen3-4B-Q4_K_M.gguf"`.
  The `lmstudio/` prefix routes to the LMStudio backend; the remainder is
  passed to LMStudio's load and chat APIs as the model identifier.
- `lmstudio_model_name`: the short bare `id` that LM Studio returns in API
  responses — e.g. `"qwen3-4b"`. This is what `/api/v0/models` returns in
  the `"id"` field (no publisher prefix, no path or quantization suffix).
  Used for response-model verification and for the load API payload.

The canonical source of truth for these values is PostgreSQL (Supabase).
After updating Postgres, sync local SQLite with:

```bash
PYTHONPATH=src python src/benchmarks/schema/create_models.py
```

(runs in upsert mode by default, so existing rows are updated)

## Quick reference

```bash
# Setup (one-time)
PYTHONPATH=src python src/benchmarks/schema/load_schema.py
PYTHONPATH=src python src/benchmarks/schema/create_models.py
PYTHONPATH=src python src/benchmarks/run_benchmark.py generate 0016_antonym

# Run
PYTHONPATH=src python src/benchmarks/run_benchmark.py run 0016_antonym claude-haiku-4-5

# See API.md for full command reference
```
