# Noun concept facts

`individuation` and `concreteness` are language-independent `lemma_facts`.
They describe the concept in a specific lemma sense, not the English label or
any translation. Both apply only to noun lemmas. Missing rows mean unclassified;
there is no default, `mixed`, or `unknown` enum value.

## Dimensions

| Fact | Value | Meaning |
|---|---|---|
| individuation | individual | A discrete entity with its own identity, physical or abstract. |
| individuation | non_individuated | Material, a quality, or a condition without an inherent individual unit. |
| individuation | collection | An aggregate of members viewed as a whole. |
| concreteness | physical | Material entities, material, or aggregates of physical things. |
| concreteness | abstract | Informational, mental, social or conceptual referents. |

When the sense explicitly denotes an aggregate, collection takes precedence over
individual even for a bounded aggregate. Sand denotes an amount of material;
it is not collection merely because grains exist. A grain of sand is individual.
Classify the referent, not its representation: a disk is physical, data on it
is abstract. A definition mixing distinct senses needs sense review, not a
forced category. The fact generator should lower confidence and explain such cases.

These are project classification conventions. They do not infer grammatical
countability, articles, case, plural forms, or Chinese classifiers. Those remain
language-specific grammar facts and rules. No sentence renderer should equate
`individual` with grammatical `countable`, or `abstract` with grammatical mass.

## Reviewed examples

| Concept/sense | Individuation | Concreteness |
|---|---|---|
| cat, the animal | individual | physical |
| chair, a seat | individual | physical |
| apple, the fruit | individual | physical |
| water, the material | non_individuated | physical |
| flour, the food material | non_individuated | physical |
| chicken, the animal | individual | physical |
| chicken, the meat | non_individuated | physical |
| furniture, furnishings collectively | collection | physical |
| data, collected observations or measurements | collection | abstract |
| justice, the principle of fairness | non_individuated | abstract |
| idea, a particular thought or proposal | individual | abstract |
| pants, a garment | individual | physical |
| picture, a physical photograph or drawing | individual | physical |
| picture, the depicted visual content | individual | abstract |
| orange, the fruit | individual | physical |
| religion, a particular belief system | individual | abstract |
| religion, the general practice or phenomenon | non_individuated | abstract |
| tarantula, the animal | individual | physical |
| lingerie, undergarments collectively | collection | physical |
| swagger, a manner of conspicuous confidence | non_individuated | abstract |
| sand, the material | non_individuated | physical |

## Release migration and client contract

`migrations/20261012_migrate_noun_concept_facts.py` contains the reviewed GUID
inventory of all 30 senses previously carrying `quantifiable` or
`has_individual_instances`. All are animals or whole food items, independently
reviewed as individual/physical. It assigns both new fields, preserves unrelated
facts and record fields, and removes both retired fields. This is not boolean
coercion. Unknown legacy GUIDs, missing reviewed senses, changed labels,
duplicate GUIDs, or conflicting new classifications fail preflight before writes.
Rerunning after migration validates coverage and makes no changes.

```sh
# Read-only validation / dry run:
GREENLAND_TEST_MODE=1 PYTHONPATH=src python migrations/20261012_migrate_noun_concept_facts.py
# Apply to release files only, without any database or model access:
GREENLAND_DISABLE_LLM=1 PYTHONPATH=src python migrations/20261012_migrate_noun_concept_facts.py --apply
```

Release records use:

```json
"facts": {"individuation": "individual", "concreteness": "physical"}
```

The SQLite schema needs no column changes: `lemma_facts` stores these as
key/value rows. Rebuild SQLite from the migrated release tree; no production
SQLite migration is performed here. Imports reject retired fact names instead
of guessing their replacements. Release exports omit stale retired rows.

Wireword exports use string fields `individuation` and `concreteness` at the top
level, with identical values in every target language. Unclassified dimensions
are omitted. The boolean `quantifiable` and `has_individual_instances` fields
are removed; clients must consume the new fields explicitly. There is no legacy
alias or inferred conversion.

The lape lemma-fact CLI accepts either new fact independently. Its default
coverage mode is read-only; `--populate` requires deliberately authorized live
model use and persists through the ordinary confidence-gated writer. No live
model calls were made to classify the 30 migrated senses.

To import just these dimensions into an existing SQLite database, run:

```sh
GREENLAND_DISABLE_LLM=1 PYTHONPATH=src python migrations/20261012_import_noun_concept_facts.py --apply
```

Omit `--apply` for a preview. The importer validates GUIDs and sense labels,
requires reviewed release replacements for every retired fact, saves a
WAL-aware backup, and commits atomically. It preserves unrelated facts and
lemma content. Repeating the import makes no changes once synchronized.
