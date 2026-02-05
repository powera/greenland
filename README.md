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

## Repository Structure

```
greenland/
├── src/
│   ├── wordfreq/              # Linguistic database system (core)
│   │   ├── storage/           # Database layer (ORM, models, CRUD)
│   │   ├── translation/       # LLM-based translation and form generation
│   │   ├── frequency/         # Word frequency analysis
│   │   ├── dictionary/        # Word list management and export
│   │   ├── prompts/           # LLM prompt templates
│   │   ├── tools/             # CLI utilities
│   │   ├── trakaido/          # Trakaido app integration
│   │   └── data/              # Data files (linguistics.sqlite, IPA dict)
│   │
│   ├── agents/                # Autonomous data quality agents
│   ├── barsukas/              # Flask web interface
│   ├── clients/               # Unified LLM client (OpenAI, Anthropic, Gemini, Ollama)
│   ├── benchmarks/            # LLM benchmark suite
│   ├── lib/                   # Shared libraries
│   ├── util/                  # General utilities
│   ├── wireword/              # WireWord format export
│   ├── langtools/             # Language processing tools
│   ├── audioshoe/             # Audio generation (eSpeak, Piper, Coqui)
│   ├── tests/                 # Tests
│   └── constants.py           # Centralized path configuration
│
├── data/release/              # Release data files (wordlists, sentences)
├── prompts/                   # LLM prompt templates
├── docs/                      # Documentation
├── hooks/                     # Git hooks (pre-commit for black)
├── pyproject.toml             # Project configuration
└── run_tests.py               # Test runner
```

---

## Agents

Each agent is named after a Lithuanian animal and performs specific database
maintenance tasks. Agents support `--check` (read-only), `--fix` (repair),
and `--dry-run` (preview) modes.

| Agent | Animal | Purpose |
|-------|--------|---------|
| pradzia | Beginning | Database initialization |
| lokys | Bear | English lemma validation |
| dramblys | Elephant | Missing words detector |
| bebras | Beaver | Database integrity checker |
| voras | Spider | Translation validator |
| vilkas | Wolf | Word forms checker |
| sernas | Boar | Synonym/alternative form generator |
| papuga | Parrot | Pronunciation validation |
| zvirblis | Sparrow | Example sentence generator |
| buivolas | Water Buffalo | Pattern-based sentence generator |
| lape | Fox | Grammar facts generator |
| sarka | Magpie | Conversation sentence generator |
| strazdas | Thrush | eSpeak-NG audio generation |
| vieversys | Lark | OpenAI TTS audio generation |
| povas | Peacock | HTML report generator |
| ungurys | Eel | WireWord export |
| elnias | Deer | WireWord bootstrap export |

---

## Database

The primary database is **`src/wordfreq/data/linguistics.sqlite`** (gitignored).
Path constants are defined in `src/constants.py`.

Key tables: `lemmas`, `word_tokens`, `derivative_forms`, `lemma_translations`,
`sentences`, `sentence_translations`, `grammar_facts`, `operation_logs`.

See `src/wordfreq/storage/models/schema.py` for the full schema.

---

## Development

- **Formatting:** `black` with 100-char line length
- **Type checking:** `mypy` on all modified files
- **Testing:** `python run_tests.py` (pytest-based)
- **Imports:** Always use absolute imports from `src/` root
- **Running scripts:** Always use `PYTHONPATH=src python src/...`
- **Pre-commit hooks:** `git config core.hooksPath hooks`

See [INSTALL.md](INSTALL.md) for full setup instructions.
