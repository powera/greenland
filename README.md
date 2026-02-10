# Greenland

A multilingual linguistic database and content generation system for the
**Trakaido** language-learning app.

**Python 3.12+** | **14 languages** | **SQLite-based**

---

## What It Does

1. **Linguistic Database (WordFreq)** - Multi-language word frequency and translation database with LLM-powered analysis
2. **Web Editor (Barsukas)** - Flask interface for browsing and editing the linguistics database
3. **Autonomous Agents** - Lithuanian-animal-named scripts for bulk database maintenance via LLM calls
4. **LLM Benchmarks** - Framework for testing and comparing language model capabilities

### Supported Languages

English, Lithuanian, Chinese (simplified), French, German, Spanish, Portuguese,
Korean, Swahili, Vietnamese, Japanese, Italian, Dutch, Swedish

---

## Getting Started

See [INSTALL.md](INSTALL.md) for environment setup, dependencies, and database initialization.

### Quick Commands

```bash
# Run the web editor (port 5555)
PYTHONPATH=src python src/barsukas/app.py

# Interactive shell with preloaded tools
PYTHONPATH=src python -i src/interactive.py

# Run an agent (example: translation coverage check)
PYTHONPATH=src python src/agents/voras.py --mode coverage

# Run tests
python run_tests.py
```

---

## Repository Layout

```
greenland/
├── src/                       # Source code (see src/README.md)
├── data/release/              # Release data files (wordlists, sentences)
├── prompts/                   # LLM prompt templates
├── docs/                      # Documentation
├── hooks/                     # Git hooks (pre-commit for black)
├── pyproject.toml             # Project configuration
└── run_tests.py               # Test runner
```

See [src/README.md](src/README.md) for source code structure, agent details,
and database schema.

---

## Development

- **Formatting:** `black` with 100-char line length
- **Type checking:** `mypy` on all modified files
- **Testing:** `python run_tests.py` (pytest-based)
- **Imports:** Always use absolute imports from `src/` root
- **Running scripts:** Always use `PYTHONPATH=src python src/...`
- **Pre-commit hooks:** `git config core.hooksPath hooks`

See [INSTALL.md](INSTALL.md) for full setup instructions.
