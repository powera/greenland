# Benchmarks API Reference

## CLI (`run_benchmark.py`)

All commands use `PYTHONPATH=src python src/benchmarks/run_benchmark.py`.

### run

Run a benchmark against a model. Returns a run ID on success.

```bash
PYTHONPATH=src python src/benchmarks/run_benchmark.py run 0016_antonym gpt-5-nano
```

### generate

Generate and load questions for a benchmark into the database.

```bash
PYTHONPATH=src python src/benchmarks/run_benchmark.py generate 0062_sentence_decomposition
```

### list

List all registered benchmarks with descriptions.

```bash
PYTHONPATH=src python src/benchmarks/run_benchmark.py list
```

### models

List all registered model codenames.

```bash
PYTHONPATH=src python src/benchmarks/run_benchmark.py models
```

### missing

Run all benchmark/model combinations that don't have results yet.

```bash
PYTHONPATH=src python src/benchmarks/run_benchmark.py missing
PYTHONPATH=src python src/benchmarks/run_benchmark.py missing --blacklist-models translategemma-3-4b --blacklist-benchmarks 0062_sentence_decomposition
```

## Python API (`run_benchmark` module)

```python
from benchmarks.run_benchmark import (
    run_benchmark,              # run_benchmark("0016_antonym", "gpt-5-nano") -> run_id
    run_all_benchmarks_for_model,  # run all benchmarks for one model
    run_missing_benchmarks,     # run all missing benchmark/model pairs
    generate_benchmark_questions,  # generate questions for a benchmark
    get_all_model_codenames,    # list model codenames from DB
    get_all_benchmarks,         # list benchmark codes
    get_benchmark_info,         # list benchmarks with metadata
)
```

## Factory (`lib/utils/factory.py`)

Lower-level access to runners and generators.

```python
from benchmarks.lib.utils.factory import get_runner, get_generator

# Run with scoring and DB storage
runner = get_runner("0016_antonym", "gpt-5-nano")
run_id = runner.run()

# Quick test with N questions, no DB storage
results = runner.run_sample(num_questions=3)

# Generate questions
generator = get_generator("0016_antonym")
generator.load_to_database()
```

## Benchmark codes

| Code | Name |
|------|------|
| `0016_antonym` | Antonym Identification |
| `0020_definitions` | Word Definitions |
| `0051_pinyin_letters` | Pinyin Letter Count |
| `0062_sentence_decomposition` | Sentence Decomposition |

## Model codenames

Use codenames (not full model paths) when running benchmarks:

| Codename | Provider |
|----------|----------|
| `gpt-5.2` | OpenAI |
| `gpt-5-mini` | OpenAI |
| `gpt-5-nano` | OpenAI |
| `claude-opus-4-6` | Anthropic |
| `claude-sonnet-4-5` | Anthropic |
| `claude-haiku-4-5` | Anthropic |
| `gemini-2.5-pro` | Google |
| `gemini-2.5-flash` | Google |
| `gemini-2.5-flash-lite` | Google |
| `translategemma-3-4b` | Local |
