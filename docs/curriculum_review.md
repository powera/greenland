# Sense-aware curriculum placement review

`quality.curriculum_review` prepares review requests by GUID, then submits them
through **the regular batch queue**. The job is registered as
`curriculum_review`, operation `levels.placement`. It appears on Barsukas's
**Batch Operations** page; the existing batch poller and “check and finish”
completion action save suggestions and apply authorized placements.

Restart a running Barsukas process once after installing this code to load the
new job registration and curriculum bounds. No restart is needed for later
metadata or placement changes.

## Topic catalogue and bounds

[The topic catalogue](curriculum_topic_proposal.json) defines the additional
subjects, their boundaries, illustrative examples and editorial CEFR estimates.
[The metadata patch](curriculum_level_metadata.json) names 10 legacy untitled
levels and fills 40 missing C1/C2 estimates. Existing A2/B1/B2 classifications
remain unchanged. These estimates describe a unit, not a formal CEFR rating of
every sense in it.

Topic destinations can be **1000–1499 except 1399**. **1399 remains reserved
staging**, never a topic. The 1300–1380 range, and 1400–1499 if needed, can hold
advanced or numbered continuations of existing subjects, such as “Foods 7”.
No such continuation levels are created automatically to satisfy a size quota.
Roughly 80–120 entries per topic is a planning guideline, not a mandatory size.

The catalogue's boundaries and examples are stored in editorial notes and used
in placement prompts. Examples identify intended senses; they neither import
lemmas nor require example words to belong to the unit. Occupied numbers are
checked against both metadata and lemma assignments.

```sh
GREENLAND_DISABLE_LLM=1 PYTHONPATH=src python -m quality.curriculum_review install-topics \
  --review /tmp/new-topic-review.sqlite --catalogue docs/curriculum_topic_proposal.json
GREENLAND_DISABLE_LLM=1 PYTHONPATH=src python -m quality.curriculum_review update-levels \
  --review /tmp/new-topic-review.sqlite --catalogue docs/curriculum_level_metadata.json
```

Both commands validate before writing, use logged curriculum CRUD, and take a
**minor** backup before changes. Identical reruns are no-ops. Metadata patches
preserve prerequisites, extra fields and translations on existing rows. Notes are
preserved unless the patch explicitly supplies replacement editorial boundaries.
The metadata patch expects missing CEFR tags and refuses a conflicting edit.

## Offline preparation

```sh
GREENLAND_TEST_MODE=1 PYTHONPATH=src python -m quality.curriculum_review prepare \
  --review /tmp/new-topic-review.sqlite --phase topics \
  --catalogue docs/curriculum_topic_proposal.json
GREENLAND_TEST_MODE=1 PYTHONPATH=src python -m quality.curriculum_review preview \
  --review /tmp/new-topic-review.sqlite
```

By default, preparation compares committed release base records at
`6e3f0114` and `641589ba`; use `--old` and `--new` for another release pair.
It regenerates inventory from Git, so untracked review TSVs are optional.
Phases are `topics`, `staging` and `unlevelled`. Only new GUIDs are selected;
established placements in 1–499 and fixed cohorts are protected. Sibling
senses are context, never an instruction to move a whole headword. The original
1,164 topic senses with siblings were candidates, not presumed mistakes.

The local SQLite journal saves prepared prompts, sense/evidence fingerprints,
allowed destinations and settings. Repeating preparation with the same settings
resumes missing rows; use a fresh journal for changed settings. Preview mirrors
returned suggestions and application receipts from the main operation log.
This file is a preparation/review artifact, **not the batch lifecycle tracker**.

Destinations default to topics or staging. `fit=none, level=0` means **no suitable
level**, not a forced topic fit. With application authorized, no-fit results
are parked at 1399. Invalid results are held, not silently coerced into staging.

For a separate CEFR pass, use a fresh journal with `--cefr-pass`. A1/A2/B1 evidence
can open non-fixed units 100–499. B2 requires an explicit rare exception: a JSON
list of GUIDs passed to `--b2-exceptions`. C1, C2, unknown and missing CEFR evidence
never open 100–499. Conflicting CEFR evidence uses the highest level. Spelling
CEFR is evidence, not proof that a specialist sense belongs in a general unit.

## Regular batch submission and completion

Obtain approval before new paid calls. Plan without model calls or credentials:

```sh
GREENLAND_TEST_MODE=1 PYTHONPATH=src python -m quality.curriculum_review submit-all \
  --review /tmp/new-topic-review.sqlite --batch-size 325 --apply-results --dry-run
```

After approval, the same command without `--dry-run` submits:

```sh
PYTHONPATH=src python -m quality.curriculum_review submit-all \
  --review /tmp/new-topic-review.sqlite --batch-size 325 --apply-results
```

The script uses `BatchQueueManager` and `workqueue.llm_batch.start_batch_run`.
The shared runner partitions requests, records normal queue rows, and skips
in-flight items on a repeated invocation. Each row holds its GUID, lemma ID,
frozen review state, model, destination policy and application authorization.
**The completion handler does not read or require the local journal.** Its
queue row is enough, including when Barsukas runs from another directory.

`--apply-results` authorizes applying valid primary `good` or `acceptable`
placements, or staging `none` results. Without it, the handler only saves
suggestions. Nothing is applied solely because a level was an alternative.
Stale/edited senses and protected placements are held; one bad row does not
block other rows. The returned suggestion is retained for a stale sense.

The main database stores suggestions and receipts in its operation log. Moves
use `PlannedMove`/`apply_moves`, with SQLite locking and fingerprint checks.
One minor backup is taken before the first move in each planned chunk; a
transactional marker prevents a backup per word. A primary-database receipt
prevents repeating a move after a crash between the main commit and shared-queue
completion bookkeeping. Invalid model answers remain visible as failed outcomes
in the regular queue, with their provider responses retained there.

Barsukas's normal poller completes these jobs. To finish one by hand:

```sh
GREENLAND_DISABLE_LLM=1 PYTHONPATH=src python -m agents.common.batch complete --batch-id batch_...
```

No separate placement watcher is required. Before submitting staging, pass
`--topic-review <completed-topic-review.sqlite>`; the release pair must match
and all topic suggestions must be resolved. The `submit` action also uses the
regular queue, with `--limit` limiting the number considered.

## Single calls and explicit approvals

After approval of one synchronous test:

```sh
PYTHONPATH=src python -m quality.curriculum_review run-one \
  --review /tmp/new-topic-review.sqlite --guid N72_053 --apply-results
```

This requires installed topic metadata and unchanged sense evidence. The response
and usage are saved before application. The durable single-attempt marker prevents
spending again on an uncertain rerun. Omit `--apply-results` for suggestion only.

For editorial application of collected results, `apply-results` uses the same
validation and primary receipt checks. For individually approved moves, use a
JSON object mapping GUIDs to integer destinations and pass `--approvals` to
`preview`, then `apply`. A destination must be suggested or explicit staging.
The explicit apply path backs up, validates the complete move set and commits
it together. No backup pruning or direct release-file editing occurs.

## Historical run

The November 17 placement run used a separate journal before this integration.
Its completed records remain local and intact. Legacy `collect`, `collect-all`,
`watch` and `attach` commands exist only to recover old submissions; they do not
submit new requests. Journals with legacy batch jobs are blocked from new
submission to avoid replaying already completed or manually corrected work.
The five historical jobs are not retroactively inserted into Barsukas's queue.

Keep journals, generated inventories, approvals and database backups untracked.
Use the existing level-warning audit after placement and the ordinary database
release export workflow. Re-leveling 1399 and designing additional advanced or
numbered units remain the next curriculum task.

## Sampling the staging inventory and reporting outcomes

To choose a reproducible cohort from all current staging GUIDs, independently of
release-diff membership, prepare with `--inventory --phase staging --limit 1400
--seed 20261117`. The fixed-seed sample is selected uniformly, then frozen in
the journal with its population size. Resume uses the frozen GUIDs, not a fresh
sample. Use `--cefr-pass` to offer 100–499 to eligible A1/A2/B1 senses; B2 still
requires explicit exceptional GUIDs, and C1/C2/unranked stay in topics or staging.
The provider schema constrains both primary and alternative levels to the
per-sense menu, retaining 0 for “no suitable level”.

After the earlier topic review has been completed editorially (including manual
resolution of failures), `--topics-reviewed` records that explicit acknowledgement
when submitting staging. Alternatively, provide the completed `--topic-review`
journal as above. This acknowledgement does not edit or resubmit the earlier jobs.

```sh
GREENLAND_TEST_MODE=1 PYTHONPATH=src python -m quality.curriculum_review prepare \
  --review /tmp/staging-review.sqlite --phase staging --inventory --limit 1400 \
  --seed 20261117 --cefr-pass
PYTHONPATH=src python -m quality.curriculum_review submit-all \
  --review /tmp/staging-review.sqlite --batch-size 350 --apply-results --topics-reviewed
GREENLAND_TEST_MODE=1 PYTHONPATH=src python -m quality.curriculum_review stats \
  --review /tmp/staging-review.sqlite --output /tmp/staging-placement-stats.json
```

Statistics compare the frozen starting assignments with actual current database
levels. They report destination counts/titles/CEFR, moved senses, those still at
1399, no-fit suggestions, applied receipts, missing senses, and latest shared-queue
outcomes per GUID. “Still staging” while the job runs includes pending or failed
requests as well as valid no-fit decisions; queue outcomes distinguish them.


## Narrowing the advanced general units

The catch-all split reviews the senses at 1180 and 1182 together. The metadata
patch [curriculum_catchall_levels.json](curriculum_catchall_levels.json) gives
seven C1 units explicit boundaries, including five new units at 1300–1304:
physical description/degree; figurative imagery; character/thought/feelings;
actions/change/movement; everyday life/roles/objects; evaluation/value/certainty;
and abstract states/relations/consequences. Ordinary abstract vocabulary is not
inherently figurative, and an unfamiliar literal sense is not automatically a
candidate for either broad general unit.

The editorial split is by GUID and definition, not by headword. Recognizable
physical-image metaphors remain in 1182. Clear specialist senses return to their
existing topics (for example, scientific light to physics and a defense mechanism
to psychology). Future preparation reads the narrowed boundaries from database
notes. No capacity quota forces a fit, and 1399 remains a valid unresolved choice.
