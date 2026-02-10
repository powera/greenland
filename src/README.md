# Source Code

## Directory Structure

```
src/
├── storage/               # Database layer (ORM, models, CRUD)
├── wordfreq/              # Linguistic database system (core)
│   ├── translation/       # LLM-based translation and form generation
│   ├── frequency/         # Word frequency analysis
│   ├── dictionary/        # Word list management and export
│   ├── prompts/           # LLM prompt templates
│   ├── tools/             # CLI utilities
│   ├── trakaido/          # Trakaido app integration
│   └── data/              # Data files (linguistics.sqlite, IPA dict)
│
├── agents/                # Autonomous data quality agents
├── barsukas/              # Flask web interface
├── clients/               # Unified LLM client (OpenAI, Anthropic, Gemini, Ollama)
├── benchmarks/            # LLM benchmark suite
├── util/                  # General utilities
├── wireword/              # WireWord format export
├── langtools/             # Language processing tools
├── audioshoe/             # Audio generation (eSpeak, Piper, Coqui)
├── scripts/               # Standalone scripts
├── sentences/             # Sentence processing
├── workqueue/             # Work queue infrastructure
├── tests/                 # Tests
└── constants.py           # Centralized path configuration
```

---

## Agents

Each agent is named after a Lithuanian animal and performs specific database
maintenance tasks. See [agents/README.md](agents/README.md) for detailed
usage and arguments.

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
| erelis | Eagle | False lemma match detection in sentences |
| gandras | Stork | Audio manifest downloader |

---

## Database

The primary database is **`src/wordfreq/data/linguistics.sqlite`** (gitignored).
Path constants are defined in `src/constants.py`.

Key tables: `lemmas`, `word_tokens`, `derivative_forms`, `lemma_translations`,
`sentences`, `sentence_translations`, `grammar_facts`, `operation_logs`.

See `storage/models/schema.py` for the full schema.
