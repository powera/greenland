# reading_lexicon

Exports one JSON file per **text language** — the language being read — for
word-by-word annotated reading: click any word of running text to get its
dictionary form, grammar, definition and glosses.  newslettr and pow3 consume
it.  This is not the WireWord export: WireWord is a quiz curriculum (level
caps, decoy pools, one target per run); this is a dictionary of every surface
form Greenland knows.

```bash
PYTHONPATH=src python -m exports.reading_lexicon --language en es fr zh lt \
  --output-dir data/exports
PYTHONPATH=src python -m exports.reading_lexicon --language en \
  --output /tmp/reading-lexicon.en.json --db-path /path/to/linguistics.sqlite
```

Files are named `reading-lexicon.<lang>.json`.  On the release data they are
5–10 MB each (0.8–1.2 MB gzipped).  Pass `--include-staging` to add the
unreviewed staging band, and `--stored-forms-only` to skip rule-built forms
(they are normally filled in, so a database whose forms were never generated
still exports full paradigms).

## Format (`_meta.schema` = `greenland-reading-lexicon/1`)

```jsonc
{
  "_meta": {
    "schema": "greenland-reading-lexicon/1",
    "language": "es",                         // the text language
    "gloss_languages": ["en", "fr", "zh", "lt"],
    "exported_at": "2026-11-07T15:42:47+00:00",
    "lemma_count": 8592, "form_count": 32714, "analysis_count": 61000,
    "function_word_count": 83,
    "include_staging": false, "derived_forms": true
  },
  "lemmas": {
    "V06_004": {
      "lemma": "comprar",                     // dictionary form in the text language
      "pos": "verb", "subtype": "possession", "level": 7,
      "definition": {"en": "to purchase in exchange for money."},
      "sense": {"en": "…"},                   // disambiguation, when the lemma has one
      "gloss": {"en": "buy", "fr": "acheter", "zh": "买", "lt": "pirkti"},
      "facts": {"verb_reflexivity": "non_reflexive"},
      "reading": {                            // zh only
        "pinyin": "zhèngquè de", "syllables": ["zhèng", "què", "de"],
        "source": "pypinyin",                 // or "override" (the lemma's pinyin fact)
        "review": true                        // a polyphone no phrase settled: a guess
      }
    }
  },
  "forms": {                                  // lookup key -> every analysis
    "compraba": [{"g": "V06_004", "f": "verb/es_1s_imperfect", "src": "rule"},
                 {"g": "V06_004", "f": "verb/es_3s_imperfect", "src": "rule"}],
    "como":     [{"g": "R99_050", "src": "base"},
                 {"g": "V01_001", "f": "verb/es_1s_present", "src": "rule"}]
  },
  "function_words": {                         // no GUID: articles, clitics, particles…
    "lo": [{"pos": "pronoun", "category": "personal_pronouns"}]
  },
  "redirects": {"A02_012": "A04_005"},         // tombstoned GUID -> live GUID
  "deleted": ["N09_002"]                      // tombstoned with no replacement
}
```

### Lookup

* Keys are trimmed, lowercased, and typographic apostrophes are folded to
  `'` (`exports.reading_lexicon.surface_key`).  Consumers must normalise the
  same way.
* Keys may contain spaces ("will exist", "se lever", "renunciar a"): match the
  longest key first.
* An analysis is `{g, f?, src}`: the lemma GUID, the grammatical-form slot
  (a stable `GrammaticalForm` value such as `verb/fr_3s_ps`; absent for a
  base form with no named slot), and where the analysis came from —
  `base` (the headword), `stored` (a derivative_forms row), `rule` (the
  mechanical builders), `variant` (an accepted spelling variant).
* A key often has several analyses: homographs and syncretic slots
  ("hablaba" is 1s and 3s).  Choosing between them is the consumer's job.

### IDs

GUIDs encode part of speech and subtype, so recategorising a word gives it a
new one.  Store the GUID together with a snapshot of `lemma`, `pos` and `f`,
and resolve stored GUIDs through `redirects` on read.  A GUID in `deleted`
(or absent from both) should fall back to the snapshot.  Slot names are
stable registry values.

### Coverage notes

* Every lemma with a translation in the text language is included at any
  level, except words excluded for that language (level -1) and the staging
  band.  Multi-word translations are present as phrase keys but have no
  inflected forms.
* Spanish includes the imperfect, conditional, present subjunctive and
  imperative; French the conditional, present subjunctive, passé simple and
  imperative.  These are `mechanical_forms` in each `forms_config`: stored
  for reading, outside the LLM schema and the WireWord export.  Spanish
  imperfect subjunctive (-ra/-se) and the compound tenses are not yet built.
* Lithuanian verbs conjugate only where the `3s_present`/`3s_past` principal
  parts are stored; participles and pronominal adjectives are not built.
* Definitions are English only.  Function words carry part of speech and
  category but no gloss.
