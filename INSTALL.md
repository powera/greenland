# Installation & Setup

## Prerequisites

- Python 3.12+
- pip

## Environment Setup

```bash
# Install core dependencies
pip install -e .

# Install development dependencies (black, mypy, pytest)
pip install -e ".[dev]"

# Install ML dependencies (optional, for benchmarks)
pip install -e ".[ml]"
```

## Submodules (Optional)

`audio/`, `data/greenland_input/`, and `data/trakaido_wordlists/` are git
submodules. Initialize them only if you need their contents:

```bash
git submodule update --init <path>
```

## Pre-commit Hooks

Enable black formatting checks on commit:

```bash
git config core.hooksPath .githooks
```

## Database Initialization

The primary database (`data/wordfreq/linguistics.sqlite`) is gitignored.
When setting up a new environment, initialize it:

```bash
PYTHONPATH=src python src/agents/pradzia.py
```

A secondary benchmarks database (`src/benchmarks/schema/benchmarks.db`) is also
gitignored and created on first use.

## API Keys

LLM API keys are stored in `keys/` (gitignored). Create this directory and add
key files as needed by the providers you use (OpenAI, Anthropic, Google).

## Running the Web Editor

```bash
# Start Barsukas on port 5555
PYTHONPATH=src python src/barsukas/app.py

# Or use the launch script:
src/barsukas/launch.sh
```

Access at `http://127.0.0.1:5555`.

## Running Tests

```bash
# Fast import/startup checks; run on every commit
./run_tests.sh smoke

# The tests known to pass; run often, not every commit
./run_tests.sh base

# Everything, including known-failing suites
./run_tests.sh all
```

Extra arguments are passed through to pytest, so you can narrow a run:

```bash
# Specific directory
./run_tests.sh base src/tests/wordfreq

# Specific file
./run_tests.sh base src/tests/wordfreq/test_storage.py

# By keyword, stopping at the first failure
./run_tests.sh base -k combined_rank -x
```

## Running Agents

All agents are run from the repo root with `PYTHONPATH=src`:

```bash
# Check mode (read-only)
PYTHONPATH=src python src/agents/voras.py --mode coverage

# Fix mode (make changes)
PYTHONPATH=src python src/agents/dramblys.py --fix --limit 20

# Dry run (preview changes)
PYTHONPATH=src python src/agents/sernas.py --dry-run
```

## Interactive Shell

```bash
PYTHONPATH=src python -i src/interactive.py
# Provides: cl (LinguisticClient), rv (LinguisticReviewer), session, prcs (WordProcessor)
```

## Code Style

- **Black:** `black --line-length 100 src/`
- **Mypy:** `mypy src/` (type hints required on all new code)
- **Imports:** Absolute imports only (e.g., `from agents.common_args import ...`)

## Gitignored Data Files

These are not checked in and must be initialized or copied:

- `keys/` - API keys
- `data/wordfreq/linguistics.sqlite` - Linguistics database
- `src/benchmarks/schema/benchmarks.db` - Benchmarks database
- `src/clients/data/batch_tracking.sqlite` - Batch tracking
- `src/wordfreq/output/` - Generated outputs

## Key Path Constants

All important paths are defined in `src/constants.py`:

| Constant | Path |
|----------|------|
| `SRC_DIR` | `src/` |
| `PROJECT_ROOT` | Repository root |
| `WORDFREQ_DB_PATH` | `data/wordfreq/linguistics.sqlite` |
| `SQLITE_DB_PATH` | `src/benchmarks/schema/benchmarks.db` |
| `KEY_DIR` | `keys/` |
| `OUTPUT_DIR` | `../greenland_output` |
