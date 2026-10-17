# Lape2: bundled grammar backfill

Lape2 is the bundled grammar workflow alongside Lape and keeps the name `lape2`. The old
agent, scalar service, Barsukas endpoint, and queued Lape jobs remain intact.

## Usage

```sh
# Read-only: report pending questions across all supported translations.
GREENLAND_TEST_MODE=1 PYTHONPATH=src python -m agents.lape2 coverage --level 1-9

# Read-only: print the exact saved manifest, fixed context, prompt and schema.
# Without --limit, preview stops at the first actionable lemma.
GREENLAND_TEST_MODE=1 PYTHONPATH=src python -m agents.lape2 preview --languages en fr zh --limit 1

# Read-only: restrict the question set. Missing prerequisites are included.
GREENLAND_TEST_MODE=1 PYTHONPATH=src python -m agents.lape2 preview --languages en --facts plural

# Read-only: plan a population run without constructing a client or writing.
GREENLAND_TEST_MODE=1 PYTHONPATH=src python -m agents.lape2 populate --languages en fr zh --limit 20 --dry-run

# LIVE: only after deliberately authorizing model use. Results are persisted.
PYTHONPATH=src python -m agents.lape2 populate --languages en fr zh --limit 20

# LIVE: same planner and validator, submitted through the OpenAI Batch API.
PYTHONPATH=src python -m agents.lape2 populate --languages en fr zh --limit 20 --batch
```

The direct-script entry point is `src/agents/lape2.py`. `coverage` is the default
command. Languages default to the catalog's supported languages; only existing
translations qualify. Concept facts are requested once per noun sense,
independently of the language selection. `--facts` narrows the question set;
there are no task presets. `--limit` counts actionable lemmas after checking
existing facts, applicability, translations, and prior uncertainty.

Population adds missing facts without overwriting existing values, so it does
not automatically back up on every invocation. Before a risky bulk backfill,
take one **minor** backup for the whole operation through `storage.backup`,
using the same database configuration as the backfill. Individual word tests
do not need separate backups. Existing backups are never automatically pruned.
Preview, coverage and dry runs do not write data, load credentials, or construct
a model client. PostgreSQL uses the configured database through
`DataSourceConfig`; the JSONL backend is deliberately excluded from this agent.

## Request construction

`src/agents/lape2/catalog.py` defines question semantics and kinds. Language
and POS applicability comes from the existing storage registries; language
names and mappings are not duplicated. Gender, auxiliary and reflexivity
enums reuse the existing language systems. The legacy registry's `generatable`
flag continues to describe legacy scalar generation during this migration;
Lape2's catalog also includes facts the old scalar agent cannot generate.

The planner reads one lemma sense, its translations, target definitions and
disambiguations, existing grammar/concept facts, and uncertainty records. It
creates only applicable missing questions. A plural check includes a missing
number classification, and English comparison checks include a missing
gradability classification, in the same request.

`prompts/grammar/lape2/context.txt` is fixed across words and language subsets.
The prompt lists the sense, supplied translations, known facts, and missing
questions. The schema requires exactly those questions; each answer contains
`value`, `confidence`, and `explanation`. One question's confidence never gates
an unrelated answer. Output allowance scales with the number of questions.
Question instructions appear only in the prompt, not repeated as schema
descriptions. Lape2 explicitly allows up to 3,072 input-schema tokens; other
callers retain the shared 2,048-token default. This budget is independent of
the output-token allowance.

The catalog covers noun gender, countability, number paradigm, classifiers,
animacy; verb transitivity, reflexivity, auxiliary and registered principal
parts; English adjective/adverb gradability; noun plurals, French adjective
feminines and comparative/superlative form checks; and noun individuation and
concreteness. Language support follows the existing registries, not a claim
that every relevant language has already been registered. Derived Lithuanian
declension classes, decorative collectives, legacy third-person aliases and
arbitrary verb-slot overrides are outside this workflow.

## Explicit completion and overrides

Every classification has an explicit value, including `number_type=regular`,
`verb_reflexivity=non_reflexive`, and ordinary auxiliaries. Missing means not
classified. The number-type values produced by Lape2 are `regular`,
`plurale_tantum` and `singulare_tantum`; legacy mass/count values are not emitted.
Countability is a separate dimension. Principal parts are stored even when
regular.

For each form check the model supplies the actual form, including regular
forms. Application code compares it with `langtools.inflection.inflect`, using
the confidently accepted classifications and excluding the target override.
It stores an explicit `<fact_type>_status` grammar fact:

| Value | Meaning |
|---|---|
| `regular` | The current mechanical builder reproduces the confirmed form. |
| `override` | The builder declines or produces a different form; keep the actual form too. |
| `not_applicable` | The grammatical slot does not apply to this sense. |

These are generator dispositions, not a claim of linguistic regularity: a
built-in exception can be mechanically reproducible, and a regular compound
can require an override when the builder declines it. The four registered
status types are `plural_status`, `feminine_form_status`, `comparative_status`
and `superlative_status`. They ship through the ordinary grammar-fact release
path, so a rebuild preserves paid completion decisions. Regular forms are not
written as new override rows. No schema migration or direct release edits are
needed.

Empty form answers mean no applicable slot, never "regular" or "unknown".
English comparison answers are checked against gradability, and plural answers
against number type. Confident forms whose required classification is missing
or uncertain remain unfinished. For comparison languages without a registered
gradability dimension, an explicit empty form is a confidence-gated decision
that comparison does not apply.

## Application and batch behavior

Inline and batch execution share `LAPE2_JOB`, registered separately from `lape`.
The request manifest is saved with every staged call. Batch completion applies
the saved question set, not a newly computed list of missing facts. There is
one in-flight batch item per lemma, preventing overlapping language filters
from spending twice on the same word within Lape2.

The validator checks enums, answer shape, finite confidence bounds, required
text, applicable slots, and dependencies. Unexpected answers are ignored and
reported; malformed or uncertain answers do not discard valid siblings.
Low-confidence answers use the existing confidence gate and uncertainty table.
They are skipped on later runs unless `--retry-uncertain` is supplied.

Existing nonempty values, including human edits made while the request was out,
are preserved. A conflicting existing override needs review rather than an
overwrite. Changes to sense text, translations, target disambiguations or
definitions, or previously supplied known facts reject a stale response before
any writes. Each accepted answer is logged with its model and confidence.
The caller commits the lemma's accepted answers and uncertainty records
together; override/status pairs are staged in the same transaction.

Lape2 does not currently perform spelling-ending cross-checks or rule-only
shortcuts from the old scalar tasks. Its default is to ask for every missing
classification. Offline tests validate orchestration and persistence. An
authorized live pilot exercised cat, wolf, eat (verb), bear (animal), and salt
(food), including multilingual persistence. Spot-checking found Portuguese
`sal` incorrectly classified as feminine with full confidence; it is masculine.
Linguistic review remains necessary before bulk backfilling: confidence and
schema validation do not establish factual correctness.
