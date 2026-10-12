# Mechanical sentence patterns

Barsukas → Trakaido → Activities → Sentence Patterns provides runtime sentence
translation practice. The English prompt is fixed independently of the Barsukas
interface language. Supported targets are lt, es, es-419, fr and zh. Spain and
Latin American Spanish use their own stored translations/forms and distinguish
vosotros from ustedes.

The language modules under `src/langtools/<language>/sentence_patterns.py` own
closed-class grammar: pronouns, conjugations, articles and numerals. The common
renderer combines these with database nouns and color/feeling adjectives, without
LLM calls or writes. Frames cover wanting, possession, liking, color, feelings,
and numbers, with singular/plural variants and seven subject choices. This is a
sentence translation drill; the slots are filled mechanically before display.

`sentences.pattern_pools.load_pools` reads translations, derivative forms and
facts. Missing translations are omitted; missing facts/forms are reported as
skips. Countability must be explicit in English and the target language. Mass
nouns cannot enter counting frames. Count/mass mismatches and plural-only nouns
are conservatively skipped pending dedicated frames. Countable food can enter
possession frames. There are no hardcoded mass-noun inventories.

Animacy is not required: subjects are fixed human pronouns, and these languages'
object frames do not inflect for animacy. Target gender, case/plural forms,
English plurals, adjective agreement and Chinese measure_words are required
where the language rule uses them. Missing data is never invented.

## Coverage and data backlog

Run read-only, with both the project import path and test-mode guard:

```sh
GREENLAND_TEST_MODE=1 PYTHONPATH=src python src/sentences/pattern_coverage.py --max-level 5 --skips
GREENLAND_TEST_MODE=1 PYTHONPATH=src python src/sentences/pattern_coverage.py --language lt --output /tmp/lt-patterns.jsonl
```

Audit of the local SQLite database on 2026-10-12: no countability or animacy facts
exist in en/lt/es/es-419/fr/zh. Seven Lithuanian number_type facts mark plural-only
nouns. Consequently noun frames are currently skipped; feeling frames work.
At level 5 these produce 49 lt, 42 es, 42 es-419, 28 fr and 49 zh sentences.
French gender and Chinese classifiers are the separately scheduled backfills.
Countability now supports generation in all pattern languages through the grammar
fact task registry; no generation or database backfill was run for this change.
English and target countability must be backfilled before noun drills open up.
Number paradigms and case/adjective forms also need checking as those words enter
coverage; rerun the report after each backfill to expose the next missing input.

The old stored-pattern generator, inventories, AJAX generation/batch UI and
buivolas pattern CLI mode have been removed. Existing stored sentences can still
be reviewed at `/pattern-sentences/view`. General LLM/guided examples remain a
separate buivolas use case. Old queued pattern jobs fail with a retirement message
rather than producing obsolete data. No database or release files were changed.
