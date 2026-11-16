# Chinese measure words: primary plus alternates (design, Nov 15 2026)

Status: implemented Nov 15 2026; the rerun has not been done.

## Problem

`measure_words` (zh) holds one classifier per noun sense.  The app builds
"one X" questions from it and draws wrong options from other nouns'
classifiers.  When a noun has more than one correct classifier the app marks a
right answer wrong: 椅子 (N39_001) is stored as 把, and 张 (stored for
桌子, 床, 纸) shows up as a "wrong" option for it.

There are three different things a learner might be asked about, and one
string can't hold them:

| Field | Meaning | Example |
|---|---|---|
| primary | the default word after 一 for this noun | 椅子 → 把, 汤 → 碗 |
| alternates | other classifiers equally correct for one item | 椅子 → 张 |
| portions | other containers/measures, which change the quantity | 汤 → 杯, 锅, 份 |

A portion word is a different quantity (a bowl vs a pot of soup), not an
interchangeable answer.  It is still never a wrong answer for that noun.

Current state: 616 of 10,688 levelled zh nouns have `measure_words`, all single
values (222 are 个), none verified.  `grammar_fact_tasks/measure_words.py`
already asks the model for `alternative_measure_words` and only logs them;
Lape2 (which wrote all 616 rows) asks for one string.

## Fact types

`measure_words` keeps its meaning: the primary.  Its consumers
(`langtools/zh/sentence_patterns.py`, `sentences/pattern_pools.py`, the
reading lexicon, wireword `grammar_metadata`) keep working unchanged.

Add, in `storage/config/grammar_fact_registry.py`:

* `measure_words_alternates` (zh, noun): other classifiers equally correct
  for one item, most common first, excluding the primary.
* `measure_words_portions` (zh, noun): container and measure words natural
  for this noun (碗, 杯, 瓶, 块, 克 ...), most common first, excluding the
  primary.

Both are `generatable=True` and go in `EXPORTED_FACT_TYPES` next to
`measure_words` (an LLM writes them; the release file is the record).

Storage: `grammar_facts.fact_value` stays a plain string, the list joined by
`", "` (`张, 个`), or the literal `none` once checked with nothing to add.
`none` matters for the same reason as `gender_variant_status`: an empty row
is otherwise indistinguishable from "never asked".  CJK classifiers never
contain a comma, so no JSON or escaping is needed.  The list shape lives in
the model schema and the export, not in the column.

### Mass nouns: the primary is never `none`

Liquids and other mass nouns have no individual classifier in the strict
sense: 水, 茶, 咖啡, 牛奶 → 杯 and 汤 → 碗 today are all containers.  But the
primary's job is "what goes after 一 in ordinary speech", and every concrete
noun the app counts has one; for soup it is 碗 (一碗汤).  So:

* primary = the default word after 一, container or not (汤 → 碗, 盐 → 克 is
  questionable; 一勺盐/一包盐 may be better, and the rerun will settle it);
* the primary is not repeated in `portions`;
* 汤 → alternates 道 (a soup as a course, 一道汤) or `none`, portions 杯, 锅, 份.

Soup's only non-portion classifier is 道, and only in the "course of a meal"
sense; 种 (a kind of) fits every noun and is excluded as noise.  The prompt
says both explicitly.

This keeps `measure_words` non-empty for every countable use, so the
sentence patterns (`not noun.measure_word` → skip) need no change.  If the
model has no natural primary at all (abstract nouns), the existing path
applies: the question stays unanswered or uncertain, and patterns skip it.

### 个

The prompt mentions 个 directly: list it as an alternate where native
speakers would accept it for this noun, and as the primary only when it is
the normal choice.  The client never uses 个 as a decoy, so a missing 个 in
`alternates` costs nothing in grading; it is there for display and for the
sentence patterns' accepted answers.

## Generation (Lape2)

### Native list schema

`clients.types.SchemaProperty` already supports `"array"` with
`items={"type": "string"}`, inside object properties (used by
`grammar_fact_tasks/measure_words.py`).  Lape2's per-question schema becomes
type-specific:

```python
value = (
    SchemaProperty("array", items={"type": "string"})
    if question.list_valued
    else SchemaProperty("string")
)
properties[question.key] = SchemaProperty(
    "object", properties={"value": value, "confidence": SchemaProperty("number")}
)
```

An empty array means "none"; no sentinel in the model's vocabulary.

`FactSpec` gains `list_valued: bool = False`, carried onto `Question`.
`PLAN_VERSION` bumps to 2.  Version-1 manifests (batches already in flight)
are still read: they carry no list-valued questions, so the field's default
is correct for them.

### `validate_answer`

`Answer.value` stays `str` (the stored form).  For list-valued questions:

* the raw value must be a list of strings;
* strip, drop empties and duplicates, keep order;
* each item: 1-3 CJK characters, no digits, no 一/两, no pinyin;
* store `", ".join(items)`, or `none` for an empty list.

Non-list questions keep today's checks.

### Cross-fact cleanup

In `apply_answers` (classifications land first, so the primary is known):
remove the primary from `alternates` and `portions` with a note, rather than
rejecting the answer; a model repeating the primary is the predictable
mistake.  `alternates` and `portions` may overlap (块 for 蛋糕 is both).

### Catalog instructions

```
measure_words: The default word after 一 for ONE of this noun in this sense:
  its classifier (只 for a cat, 把 for a chair), or for mass nouns the default
  container or measure (一碗汤, 一杯水). Use 个 only where it is the normal
  choice. No numeral or pinyin.
measure_words_alternates: Other classifiers a native speaker would accept for
  ONE of this noun in this sense, besides measure_words (张 for a chair).
  Include 个 if it is acceptable for this noun. Do not include containers or
  measures (those go in measure_words_portions), and never 种. Most common
  first; empty if none.
measure_words_portions: Other container or measure words commonly used with
  this noun (杯, 锅, 份 for soup; 片, 块 for bread). Exclude measure_words.
  Most common first; empty if none.
```

The old `lape` task (`grammar_fact_tasks/measure_words.py`) is not extended;
it writes the primary only.  Note that in its docstring.

## Export

Wireword (`exports/wireword/export_wireword.py`): `grammar_metadata` already
copies every effective grammar fact as a string.  For zh, replace the two new
strings with lists:

```json
"grammar_metadata": {
  "measure_words": "把",
  "measure_words_alternates": ["张"],
  "measure_words_portions": []
}
```

* `measure_words` stays a string (back-compat with the shipped app).
* Lists are empty for `none`; the key is omitted when unchecked, so the app
  can tell "not checked" from "checked, nothing else".
* Client rule (in `docs/grammar_activities.md`): primary, alternates and
  portions are all correct-or-related for that noun and never decoys; 个 is
  never a decoy for any noun.

A small helper (`langtools/zh/measure_words.py`: `parse_measure_word_list`)
does the split/`none` handling, shared by the exporter, the reading lexicon
and the sentence patterns.

`langtools/zh/sentence_patterns.py`: add alternates to each pattern's
`accepted` answers (一张椅子 alongside 一把椅子).  The reading lexicon adds both
fact types to `READER_FACT_TYPES`.

`docs/grammar_facts.md`: replace the unused `个 (alt: 只, 头)` format with
the three fact types.

Barsukas: grammar facts are edited as strings, so the new types appear
without changes; a "comma-separated, or none" hint on the form is enough.

## Rerun of the existing 616

Rerun all of them, since the primary instruction changes for mass nouns and
portions must not repeat it.  Lape2 never overwrites a stored fact, so:

1. `python -m storage.backup create --label zh-measure-rerun` (minor).
2. One-off delete of the 616 `measure_words` rows (all unverified, all ours).
   Not committed, per the cleanup-script rule.
3. Populate all three facts for levels 1-499.

## Tests

* registry: both types exported and generatable (existing quadrant test).
* `build_query`: list-valued questions get an array `value`.
* `validate_answer`: list normalization, empty → `none`, rejects non-lists,
  digits, pinyin.
* `apply_answers`: primary removed from alternates/portions.
* helper: parse ordering, `none`, unchecked.
* wireword export: list fields present/absent as above.

## Runs (after implementation)

```
GREENLAND_TEST_MODE=1 PYTHONPATH=src python src/agents/lape2.py coverage \
  --languages zh --facts measure_words measure_words_alternates measure_words_portions --level 1-499
PYTHONPATH=src python src/agents/lape2.py populate \
  --languages zh --facts measure_words measure_words_alternates measure_words_portions --level 1-499 --batch
```

Then re-export zh.
