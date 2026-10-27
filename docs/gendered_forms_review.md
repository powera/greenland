# Gender counterparts: review before database application

Applied to the local database on October 25, 2026 after review, using the
user-requested minor backup `linguistics.sqlite.bak-20261025-gender-variants`.
The cousin merge, variant metadata column, and selected counterpart additions
are now in SQLite. All `data/release` files remain unchanged. Preview still
uses a read-only SQLite connection and does not initialize the storage backend.

## Scope and defaults

One concept owns the ordinary unspecified translation and its paradigm.
Male and female counterparts are variants, with kind `gender` and keys `male`
and `female`. The key is semantic identity, not spelling: a male entry may
repeat the default's text without collapsing into it.

The default's grammatical gender remains its existing `GrammarFact`. Each
variant records its grammatical gender independently; neither the default's
text nor its gender is inferred from the male entry. Languages without
noun gender can leave the grammatical-gender value absent. Absence for a
language with noun gender means unclassified, not masculine.

Use this for explicitly selected counterparts of one concept: cousin,
actor/actress, German person. Do not infer counterparts by spelling, scan all
nationalities/occupations, or merge aunt/uncle, boy/girl, age distinctions, or
maternal/paternal kinship distinctions.

## SQLite

Reuse `variant_forms`, including its existing grammatical slots,
pronunciations, verification, and token links. Add one nullable string column,
`grammatical_gender`, repeated consistently on the variant's form rows.

The unspecified word stays in `lemma_translations` and `derivative_forms`.
There is no `unspecified` variant row: it is the existing base paradigm.
Thus unspecified and male are separate entries even when both say `primo`.

## Release

The base record still contains `translations.es = "primo"`. Its ordinary
Spanish `forms` and `grammar_facts` remain separate from `variants`.
The per-language `es.jsonl` record adds:

```json
{
  "guid": "N35_076",
  "variants": [
    {
      "kind": "gender",
      "key": "male",
      "grammatical_gender": "masculine",
      "forms": [
        {"grammatical_form": "noun/es_singular", "text": "primo", "is_base_form": true},
        {"grammatical_form": "noun/es_plural", "text": "primos", "is_base_form": false}
      ]
    },
    {
      "kind": "gender",
      "key": "female",
      "grammatical_gender": "feminine",
      "forms": [
        {"grammatical_form": "noun/es_singular", "text": "prima", "is_base_form": true},
        {"grammatical_form": "noun/es_plural", "text": "primas", "is_base_form": false}
      ]
    }
  ]
}
```

Existing release filtering may omit inflections when they are mechanically
regenerable; it keeps the variant base and its grammatical gender. Both SQLite
import and the JSONL backend restore the metadata. Barsukas sync compares,
shows, imports, and exports it.

## Wireword

Existing `base_target`, source word, `grammatical_forms`, `grammar_metadata`,
and `audio` retain their default meaning. For a target language with gender
variants, a new `gendered_forms` array exposes the unspecified default first,
then the stored male/female variants. This is one Wireword object and one GUID.
An abbreviated example:

```json
{
  "guid": "N35_076",
  "base_english": "cousin",
  "base_target": "primo",
  "grammar_metadata": {"grammatical_gender": "masculine"},
  "gendered_forms": [
    {
      "referent_gender": "unspecified",
      "base_english": "cousin",
      "base_target": "primo",
      "grammar_metadata": {"grammatical_gender": "masculine"}
    },
    {
      "referent_gender": "male",
      "base_english": "cousin",
      "base_target": "primo",
      "grammar_metadata": {"grammatical_gender": "masculine"},
      "grammatical_forms": [
        {"grammatical_form": "noun/es_singular", "text": "primo", "is_base_form": true},
        {"grammatical_form": "noun/es_plural", "text": "primos", "is_base_form": false}
      ]
    },
    {
      "referent_gender": "female",
      "base_english": "cousin",
      "base_target": "prima",
      "grammar_metadata": {"grammatical_gender": "feminine"},
      "grammatical_forms": [
        {"grammatical_form": "noun/es_singular", "text": "prima", "is_base_form": true},
        {"grammatical_form": "noun/es_plural", "text": "primas", "is_base_form": false}
      ]
    }
  ]
}
```

Gender counterparts do not become `target_alternatives`. A client consuming
`gendered_forms` must qualify male/female prompts using `referent_gender`.
Where the source also has a stored counterpart (actress), that source word is
included; otherwise its concept word is retained with the explicit qualifier.
Non-English sources use `base_source` instead of `base_english`.

Each variant carries its own exported paradigm and optional audio. Existing
lemma/default fields remain available to older clients, which will continue
to teach the unspecified form until they support the new array. Updating the
Trakaido client is outside this repository change.

## Audio

Reuse `AudioQualityReview.grammatical_form` with a variant namespace:

- Unspecified base: existing null key.
- Female base: `variant/gender/female/base`.
- Female plural: `variant/gender/female/noun/es_plural`.

The migration moves existing gendered-cousin audio to the surviving GUID,
retaining hashes and asset URLs. No audio is generated or uploaded. New
actor/actress and German-person variants initially have text/forms only;
the exporter attaches audio when a record with the corresponding key exists.
The existing TTS batch UI/CLI does not yet schedule gender-variant generation.

## Prepared migration

`migrations/20261024_gender_variants.py` defaults to read-only preview.
It was run with `--apply --backup-tier minor` after user approval.

The proposed data edits are deliberately narrow:

1. Keep `N35_076` as cousin. Remove the obsolete English `gender-neutral`
   disambiguator and its language exclusions, allowing the one concept at 18.
2. Move `N35_047` into its male variant and `N35_048` into its female variant,
   preserving recorded translations, inflections, and pronunciation.
3. Repoint sentence links and other supported references, move audio using
   variant keys, and tombstone both old GUIDs with replacement `N35_076`.
4. Archive retired metadata, facts, tiers, and overrides in the merge log.
   Preserve matching concept facts. The male-cousin entry's erroneous
   `concreteness=abstract` is superseded by the default's existing `physical`;
   other conflicting concept facts or unsupported dependencies abort the
   transaction for review.
5. Add male/female actor and German-person paradigms for **en, es, es-419**
   only, using an explicit seed list. Defaults remain unchanged. Other
   languages' new counterparts are not guessed.
6. The family curriculum configuration and generator now name the single
   cousin GUID, preventing recreation of separate gendered-cousin lemmas.

Applying defaults to a **major backup** through `storage.backup` because it
retires lemma rows; `--backup-tier minor` honors an explicit request for a
minor backup. The nullable column addition precedes the
transactional data changes; if data validation fails, data changes roll back
but that additive column can remain. No release export runs automatically.
The schema change has now been applied to the local database.

## Review command

```sh
GREENLAND_TEST_MODE=1 PYTHONPATH=src python migrations/20261024_gender_variants.py
```

The preview includes selected existing records, grammatical/concept facts,
reference counts, and the exact seed vocabulary. It does not take a backup,
change SQLite pragmas, or load a writable storage session.

## October 27 implementation update

The generation gap described in the original migration review is now addressed:
see [gendered_lemma_support.md](gendered_lemma_support.md) for shared assets,
variant/inflection generation, review behavior, and the remaining data rollout.
