# Release pipeline round-trip regression suite

These checks exercise the whole `data/release` <-> SQLite pipeline against the
**real, checked-in release tree**: they build a database from `data/release`,
export it back out, and assert the result is stable.

They live outside `src/tests` because they are slow (a full bootstrap reads
every JSONL file in the tree and populates ~3k lemmas and ~1.3k sentences) and
because their subject is *file content*, not code: they fail when the pipeline
starts writing different bytes, which is exactly the failure the unit tests
cannot see.

Run them with the `regtest` target when changing anything in
`src/storage/release`, `src/storage/backend/jsonl`, or the release CLI:

```bash
GREENLAND_TEST_MODE=1 ./run_tests.sh regtest src/regtest/release
```

## What "correct" means here

`data/release` is a **fixed point**: exporting a database built from the tree
reproduces the tree byte for byte. That is the strongest form of the property
and what these tests pin first.

It was not true until the tree was rewritten by the exporter. A release file
could hold things the schema cannot, and the import dropped them:

* **Unlinked word hints.** A hint referencing neither a lemma nor a name
  violates `ck_word_hint_has_reference`, so it could not be stored. 704 such
  hints were word tokens predating per-word decomposition ("my", "bike",
  "math"); they named no vocabulary and were dropped on every rebuild.
* **A hint pointing at a tombstoned lemma.** `S_00780` referenced `N27_003`,
  retired as `wrong_category`, which no import can resolve.

Both are now gone from the tree, so the first pass changes nothing. The
idempotence check is kept as well: it is the assertion that still holds if the
tree ever drifts again, and it localizes the failure to the pipeline rather
than to the data.
