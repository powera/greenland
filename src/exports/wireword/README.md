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

Exports are normally run through `exports.wireword.cli` or workqueue handlers.
The `agents.ungurys` entry points remain as thin compatibility wrappers.

### Regional registries and source-language coverage

`variants.json` describes regional **target** varieties, not every target/source
pair. It belongs only in `lang_<base>/generated/wireword/`. The export service
refreshes that canonical registry after exporting any variety or source in the
standard wordlists layout. Each entry's `source_languages` is discovered from
completed sibling `wireword_manifest_v2.json` files, checking their target and
source codes. Export directories without a manifest do not advertise support.
Trakaido copies this registry and the manifests with `scripts/sync-wordlists.sh`;
level content remains on the CDN.

Required coverage currently includes `es` and `es-419` from `en`, `fr`, `zh`, and
`lt` from `en`, `es`, `fr`, `zh`. Other completed source exports remain available.
Lithuanian has no regional picker and needs no `variants.json`: its source
bundles live in `lang_lt_from_<source>/generated/wireword/` (English: `lang_lt/`).
