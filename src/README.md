# Source Code

## Directory Structure

```
src/
├── storage/               # Database layer (ORM, models, CRUD, administration)
│   └── admin/             # Empty-DB and data/release bootstrap workflows
├── wordfreq/              # Linguistic database system (core)
│   ├── translation/       # LLM-based translation and form generation
│   ├── frequency/         # Word frequency analysis
│   ├── dictionary/        # Word list management and export
│   ├── tiers/             # Difficulty tier importers (CEFR, Cambridge YLE)
│   ├── tools/             # CLI utilities
│   └── data/              # Python data modules (family_relations)
│
├── agents/                # Autonomous data quality agents
├── barsukas/              # Flask web interface
├── clients/               # Unified LLM client (OpenAI, Anthropic, Gemini, Ollama)
├── benchmarks/            # LLM benchmark suite
├── exports/               # Export services and formats
│   └── wireword/          # WireWord format export
├── util/                  # General utilities
├── langtools/             # Language processing tools
├── ipa/                   # IPA pronunciation utilities
├── audioshoe/             # Audio generation (eSpeak, Piper, Coqui, Qwen)
├── scripts/               # Standalone maintenance scripts
├── sentences/             # Sentence processing
├── strings/               # Barsukas UI string localization tooling
├── words/                 # Word-level LLM helpers
├── verbalator/            # Text analysis tooling
├── workqueue/             # Background task queue
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
| lokys | Bear | English lemma validation |
| dramblys | Elephant | Missing words detector |
| bebras | Beaver | Database integrity checker |
| voras | Spider | Translation validator |
| vilkas | Wolf | Word forms checker |
| sernas | Boar | Synonym/alternative form generator |
| papuga | Parrot | Pronunciation validation |
| zvirblis | Sparrow | Finds sentence translation work |
| buivolas | Water Buffalo | Finds pattern/LLM sentence generation work |
| lape | Fox | Grammar facts generator |
| sarka | Magpie | Plans vocabulary-driven conversation work |
| strazdas | Thrush | eSpeak-NG audio generation |
| vieversys | Lark | OpenAI TTS audio generation |
| povas | Peacock | HTML report generator |
| ungurys | Eel | Compatibility wrapper for `exports.wireword` |
| elnias | Deer | WireWord bootstrap export |
| erelis | Eagle | False lemma match detection in sentences |
| gandras | Stork | Audio manifest downloader |
| genys | Woodpecker | Document parser and pending import stager |
| seskas | Ferret | Multi-model verb-conjugation consensus |

---


## Configuration convention

Pass runtime backend/model settings via `storage.backend.config.DataSourceConfig`
rather than passing `db_path`, `model_name`, or similar values directly.

---

## Database

The primary database is **`data/wordfreq/linguistics.sqlite`** (gitignored).
Path constants are defined in `src/constants.py`.

Key tables: `lemmas`, `word_tokens`, `derivative_forms`, `lemma_translations`,
`sentences`, `sentence_translations`, `grammar_facts`, `operation_logs`.

See `storage/models/schema.py` for the full schema.
