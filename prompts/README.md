# prompts

Prompt templates used by agents and tools, loaded via
`src/util/prompt_loader.py`. Each task directory contains a `prompt.txt`
and/or `context.txt`.

## Subdirectories

- `analysis/` — word/sentence analysis and disambiguation
- `audio/` — context for TTS audio generation
- `benchmarks/` — coding benchmark prompts
- `classification/` — POS subtype and word categorization
- `conversations/` — dialog and definition generation
- `grammar/` — grammar facts (animacy, gender, declension, transitivity, …)
- `language_forms/` — per-language morphological form generation, organized
  by language code and POS subtype
- `pronunciation/` — IPA and pronunciation generation
- `sentence_decomposition/` — sentence parsing and translation breakdown
- `sentences/` — example sentence generation by difficulty level
- `synonyms/` — synonym discovery
- `translation/` — word, definition, and sentence translation
- `validation/` — definition/lemma/translation validation
- `verbalator/` — text analysis prompts for the verbalator tooling
