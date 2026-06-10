# wireword

Exporters that convert linguistic data into the WireWord JSON format consumed
by the Trakaido language-learning app.

## Layout

- `export_wireword.py` — main word/lemma exporter
- `export_wireword_sentences.py` — sentence exports with translations and
  audio metadata
- `export_wireword_conversations.py` — conversation exports
- `export_manager.py` — orchestrates exports across formats
- `generate_manifest.py` — manifest files for audio and data exports
- `generate_categorychoice.py` — category-choice metadata for the app
- `helpers.py`, `readings.py`, `text_rendering.py`, `data_models.py` —
  formatting, pronunciation/reading data, and transfer objects

## Usage

Exports are normally run via the `ungurys` and `elnias` agents (see
`src/agents/README.md`) or workqueue handlers, rather than invoked directly.
