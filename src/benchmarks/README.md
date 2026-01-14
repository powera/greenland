# Benchmarks

Framework for evaluating language model performance on linguistic and cognitive tasks.

## Directory Structure

```
benchmarks/
├── lib/                    # Core benchmark framework
│   ├── generators/         # Question generation for each benchmark
│   ├── runners/            # Benchmark execution and scoring
│   ├── exemplars/          # Qualitative model comparison framework
│   └── utils/              # Shared base classes and data models
├── server/                 # Flask web UI for viewing results
├── datastore/              # Database access layer
├── schema/                 # SQLAlchemy models and migrations
├── 00XX_*/                 # Benchmark-specific test data
├── benchmark_constants.py  # Paths and configuration
└── config.py               # Server configuration
```

## Available Benchmarks

| Code | Name | Description |
|------|------|-------------|
| 0015 | Spell Check | Identify misspelled words |
| 0016 | Antonym | Identify antonyms from candidates |
| 0020 | Definitions | Match words to definitions |
| 0022 | Unit Conversion | Convert between measurement units |
| 0032 | Part of Speech | Identify word grammatical roles |
| 0033 | Lemma | Find base/dictionary form of words |
| 0061 | English to IPA | Convert to phonetic transcription |

## Usage

### Running a Benchmark

```python
from benchmarks.lib.utils.factory import get_runner
from benchmarks.lib.utils.data_models import BenchmarkMetadata

runner = get_runner("0016_antonym", model="gpt-4o-mini")
run_id = runner.run()
```

### Generating Questions

```python
from benchmarks.lib.utils.factory import get_generator

generator = get_generator("0016_antonym")
questions = list(generator.generate_questions_iter(count=10))
```

### Web Interface

```bash
./launch_server.sh
# Visit http://localhost:5556/dashboard
```

## Architecture

- **Generators** create benchmark questions using file, local, or LLM strategies
- **Runners** execute benchmarks against models and store results
- **Exemplars** compare model responses qualitatively (no scoring)

Each benchmark has a generator in `lib/generators/` and runner in `lib/runners/`.
Base classes in `lib/utils/` provide shared functionality.

## Database

Results stored in `schema/benchmarks.db` (SQLite). The datastore layer
provides CRUD operations for benchmarks, questions, runs, and models.
