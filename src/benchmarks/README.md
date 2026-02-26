# Benchmarks

`src/benchmarks` provides Greenland's benchmark harness for evaluating LLMs on
linguistic and reasoning-oriented tasks.

## What it includes

- **Question generation** from benchmark datasets.
- **Runner execution** against local or remote model backends.
- **Scoring + persistence** into SQLite via the datastore layer.
- **Web dashboard** for browsing runs and comparing outcomes.
- **Exemplars workflow** for qualitative model comparisons.

## Directory overview

```text
benchmarks/
├── lib/               # Framework core: generators, runners, utilities
├── datastore/         # Database access and persistence helpers
├── schema/            # DB schema/model setup scripts
├── server/            # Flask UI for run/result browsing
├── 00XX_*/            # Benchmark-specific source datasets
└── run_benchmark.py   # Main CLI entry point
```

## Common commands

```bash
# One-time setup
PYTHONPATH=src python src/benchmarks/schema/load_schema.py
PYTHONPATH=src python src/benchmarks/schema/create_models.py

# Generate questions for a benchmark
PYTHONPATH=src python src/benchmarks/run_benchmark.py generate 0016_antonym

# Run a benchmark against a model
PYTHONPATH=src python src/benchmarks/run_benchmark.py run 0016_antonym gpt-4o-mini
```

See `BENCHMARK_INDEX.md` for benchmark numbering/inventory and `API.md` for CLI details.
