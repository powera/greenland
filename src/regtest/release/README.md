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

The pipeline is **not** expected to reproduce `data/release` byte-for-byte on
the first pass. A release file can legitimately contain things the schema
cannot hold, and the import drops them:

* **Unlinked word hints.** A hint referencing neither a lemma nor a name
  violates `ck_word_hint_has_reference`, so it cannot be stored. These are word
  tokens predating per-word decomposition ("my", "bike", "math"); the export
  now drops them rather than writing rows no import can read back.
* **Hints pointing at a tombstoned lemma.** `S_00780` references `N27_003`,
  retired as `wrong_category`. The import correctly refuses to resolve a
  retired GUID.

The property that must hold is therefore **idempotence**: exporting a database
that was itself built from an export reproduces that export exactly. A first
pass may normalize; a second pass must change nothing. That is what these tests
pin, along with the specific losses that motivated them.
