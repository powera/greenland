# Greenland

Greenland is the core data and tooling repository for the **Trakaido** language-learning app.
It combines a multilingual linguistic database, editing interfaces, automation agents,
and language-model evaluation tools.

**Python 3.12+** | **SQLite-backed** | **15 supported languages**

## Main Components

- **WordFreq data layer**: stores lemmas, translations, forms, sentences, and metadata.
- **Barsukas web editor**: Flask UI for browsing, editing, and reviewing linguistic content.
- **Automation agents**: task-focused scripts for data QA, generation, and maintenance.
- **Benchmarks**: framework for generating and scoring model responses on language tasks.
- **Langtools**: language-specific utilities (forms, romanization, sorting helpers).

## Supported Languages

English, Lithuanian, Chinese (Simplified), Chinese (Traditional), French,
German, Spanish, Portuguese, Korean, Swahili, Vietnamese, Japanese, Italian,
Dutch, Swedish.

## Quick Start

See [INSTALL.md](INSTALL.md) for full setup and initialization.

```bash
# Run the Barsukas editor (default: http://127.0.0.1:5555)
PYTHONPATH=src python src/barsukas/app.py

# Open an interactive shell with project imports
PYTHONPATH=src python -i src/interactive.py

# Run tests
python run_tests.py
```

## Repository Layout

```text
greenland/
├── src/                 # Application and tooling source code
├── api/                 # Typed HTTP client facade over the Barsukas API
├── data/                # Source corpora and versioned release data
├── audio/               # Audio tooling (git submodule: powera/audiotools)
├── prompts/             # Prompt templates used by agents/tools
├── docs/                # Project documentation
├── scripts/             # Bootstrap, pipeline, and pre-commit check scripts
├── strings/             # Localized UI string catalogs for Barsukas
├── prod/                # Production deployment configuration
├── .githooks/           # Git hooks (pre-commit config)
├── pyproject.toml       # Python/tooling configuration
└── run_tests.py         # Test runner entry point
```

## Documentation

- [INSTALL.md](INSTALL.md) — setup, database initialization, running tests
- [CONTRIBUTING.md](CONTRIBUTING.md) — contribution guidelines
- [src/README.md](src/README.md) — source-level structure and agent list
- [docs/](docs/README.md) — design documents and API reference
- Most directories have a short README describing their contents.
