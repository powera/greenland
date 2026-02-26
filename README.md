# Greenland

Greenland is the core data and tooling repository for the **Trakaido** language-learning app.
It combines a multilingual linguistic database, editing interfaces, automation agents,
and language-model evaluation tools.

**Python 3.12+** | **SQLite-backed** | **14 supported languages**

## Main Components

- **WordFreq data layer**: stores lemmas, translations, forms, sentences, and metadata.
- **Barsukas web editor**: Flask UI for browsing, editing, and reviewing linguistic content.
- **Automation agents**: task-focused scripts for data QA, generation, and maintenance.
- **Benchmarks**: framework for generating and scoring model responses on language tasks.
- **Langtools**: language-specific utilities (forms, romanization, sorting helpers).

## Supported Languages

English, Lithuanian, Chinese (Simplified), French, German, Spanish, Portuguese,
Korean, Swahili, Vietnamese, Japanese, Italian, Dutch, Swedish.

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
├── data/release/        # Versioned release data files
├── prompts/             # Prompt templates used by agents/tools
├── docs/                # Project documentation
├── hooks/               # Git hooks (pre-commit config)
├── pyproject.toml       # Python/tooling configuration
└── run_tests.py         # Test runner entry point
```

For source-level structure, see [src/README.md](src/README.md).
