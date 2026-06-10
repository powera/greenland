# util

General-purpose utilities shared across the codebase. These modules are
imported as libraries; there are no CLI entry points here.

- `prompt_loader.py` — loads prompt templates from the top-level `prompts/`
  directory (with caching)
- `telemetry.py` — LLM usage metrics and cost estimation
- `logging_config.py` — centralized logging setup
- `optional_imports.py` — graceful handling of optional dependencies
- `flesch_kincaid.py` — readability scoring
- `stopwords.py` — stopword lists
- `wiki_loader.py` — indexing and querying Wikimedia dump files
