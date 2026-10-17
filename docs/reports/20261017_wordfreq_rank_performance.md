# Bulk wordfreq rank loading — October 17, 2026

The previous full refresh spent about 615 seconds recalculating lemma ranks,
versus 17 seconds importing corpus annotations. Its ranking path called the
interactive single-lemma loader for each of 10,179 lemmas in each of 19 corpora.
That repeatedly queried forms, annotation ranks, homograph claimants, and corpus
sizes.

The full-ranking path now loads derivative/variant ownership and prominence
weights once, computes token shares once, and loads each corpus's annotation
ranks in one query. Exponents and unknown-rank ceilings are calculated once per
corpus. Rank combination runs in memory; the existing batched writes and
interactive single-lemma scoring API are unchanged.

## Read-only production-data benchmark

With `GREENLAND_TEST_MODE=1` and SQLite `PRAGMA query_only=ON`, the updated
`calculate_lemma_combined_ranks(..., dry_run=True)` processed all 19 corpora and
10,179 lemmas in **0.704 seconds**, issuing **82 SELECT queries**. The exponent
cache was cleared before timing. Instrumentation captured each calculated rank
and compared it with the ranks written by the previous full refresh:
**zero differences**. The benchmark made no database writes and excludes rank
write time; the previous timing includes calculation and final writes.

Regression tests compare bulk shares/ranks with the independent single-lemma
path for shared senses, archaic variants, duplicate forms, language eligibility,
variant-only owners, duplicate annotations, invalid ranks, and corpus ceilings.
A query-growth test confirms that increasing a fixture from 1 to 101 lemmas
(with two forms each) adds no SELECT queries. Existing ranking tests continue
to exercise the final weighting and write behavior.
