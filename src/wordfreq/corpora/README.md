# Corpus generation

Builds the `data/wordfreq/*.json` word-frequency corpora. Three builders share
this directory, and everything after text extraction is common code in
`frequency_build.py` — proper-noun detection, per-document weighting and the
output format are the same for all of them:

| Builder | Source | Corpora |
| --- | --- | --- |
| `build_gutenberg.py` | Project Gutenberg books | the five below |
| `build_scotus.py` | Supreme Court opinions | `legal_scotus` |
| `build_wikipedia.py` | A Wikipedia dump snapshot | `wiki_vital`, `wiki_math` |

Five corpora have book lists here:

| Corpus | Books | Contents |
| --- | --- | --- |
| `19th_books` | 54 | Novels, children's books, essays and science first published 1800-1899, British / American / translated European |
| `20th_books` | 62 | Books first published 1900-1938, i.e. what Gutenberg carries of the 20th century |
| `early_modern_science` | 24 | Science writing from Boyle and Newton to the early twentieth century, written in English by its authors |
| `cooking` | 10 | Recipe writing, 1878-1920: general household cookery, vegetarian cookery, salads and baking |
| `religious_translated` | 23 | Old religious works in English translation: Bible (three translations), Apocrypha, Enoch, Talmud selections, Qur'an (two translations), Upanishads, Bhagavad-Gita, Mahabharata, Ramayana, Dhammapada, Tao Te Ching, Analects, Shih King, Eddas, Egyptian Book of the Dead, Augustine, Aquinas, à Kempis |

## Running it

Two steps. The first is the only one that touches the network.

```bash
# 0. Optional: re-confirm the book IDs against the catalogue (metadata only,
#    no book text). Required for any ID listed in book_lists.UNVERIFIED_IDS,
#    which is currently empty.
PYTHONPATH=src python src/wordfreq/corpora/download_gutenberg.py \
    --corpus early_modern_science --verify

# 1. Download the books to the cache (data/working/gutenberg, gitignored).
PYTHONPATH=src python src/wordfreq/corpora/download_gutenberg.py --corpus all

# 2. Build each corpus JSON from the cache.
PYTHONPATH=src python src/wordfreq/corpora/build_gutenberg.py --corpus 19th_books
PYTHONPATH=src python src/wordfreq/corpora/build_gutenberg.py --corpus 20th_books
PYTHONPATH=src python src/wordfreq/corpora/build_gutenberg.py --corpus religious_translated
PYTHONPATH=src python src/wordfreq/corpora/build_gutenberg.py --corpus early_modern_science
PYTHONPATH=src python src/wordfreq/corpora/build_gutenberg.py --corpus cooking
```

Six science books were removed from the list because Gutenberg has no
plain-text edition of them, only HTML, PDF or LaTeX source: Einstein (5001) and
Russell (41654) are HTML-only; Eddington (29782), Boole (15114), Poincare
(37157) and Whitehead (41568) are PDF and LaTeX only.  Their IDs were correct -
see the note in `book_lists.py` before re-adding any of them.  That cost the
corpus its relativity and mathematical-logic end.

The cache defaults to `$GREENLAND_GUTENBERG_CACHE`, else
`data/working/gutenberg` in the repo (gitignored, and persistent - Gutenberg
rate-limits, so a cache a reboot clears costs real re-download time);
`--dest` / `--source-dir` override it.
Downloads are skipped when the file is already cached, so step 2 can be redone
freely — it is deterministic and needs no network. `--delay` (default 1.5s)
paces requests to gutenberg.org; keep it polite.

Useful flags on the builder: `--dry-run` (report without writing),
`--report FILE` (per-book token/name counts), `--weighting pooled` (the old
behaviour, see below), `--min-books`, `--max-words`, `--skip-missing`.

## The SCOTUS corpus

`legal_scotus` is built from Supreme Court opinions rather than books, because
no book Project Gutenberg carries contains "credit card", "cruise ship" or
"elementary school": Gutenberg's copyright horizon is 1928, and those are
mid-twentieth-century terms. Federal judicial opinions are uncopyrightable
government edicts, and the Caselaw Access Project serves them as static JSON
with no API key.

```bash
# 1. Download the cases (data/working/scotus, gitignored).
PYTHONPATH=src python src/wordfreq/corpora/download_scotus.py --years 1997-2006

# 2. Build the corpus JSON from the cache.
PYTHONPATH=src python src/wordfreq/corpora/build_scotus.py --phrases-from-db
```

The unit of analysis is the **opinion**, not the case: a case carries a
majority and often several dissents and concurrences, each by a different
Justice, and counting them separately is what lets the per-document mean stop
one long opinion deciding a word's rank. The current corpus is 1,474 opinions
from 575 cases, about 5M tokens.

Two defaults differ from the book builder's, because opinions are not novels.
`--full-weight-tokens` is 4000 rather than 20000 (a long majority opinion runs
to about 10000 tokens, so the book threshold would down-weight every one), and
`--min-opinions` is 8 rather than 3 (there are 1,474 documents, not 54).

**Citation apparatus is stripped, case names are not.** About 5% of an
opinion's words are citations, and left in they would put `stat`, `ibid` and
`ante` into an English frequency list. Two rules do the work: a *run* rule
removes sequences of two or more abbreviations, numbers and section signs
(`La. Rev. Stat. Ann. §§27:301`), which is what covers the open-ended set of
jurisdictions without naming them; and a short list covers isolated
abbreviations (`Inc.`, `Cf.`, `e. g.`), which have no neighbour for the run
rule to catch. A 20-case sample holds 539 distinct abbreviation-shaped tokens,
so a list alone was never going to be complete. Party names stay in: the
per-document capitalization rule already routes them to `name_frequency`, and
removing them would take the surrounding syntax with them.

Editorial brackets are unwrapped before tokenizing. Quotations are altered in
brackets to fit the sentence quoting them (`"[w]hen"`, `"see[k]"`), and since
the tokenizer treats brackets as boundaries those would otherwise count as
`hen` and `see`.

## The Wikipedia corpora

`wiki_vital` and `wiki_math` are built from a Wikipedia dump snapshot rather
than per-document downloads, which is what makes this builder different from
the other two: there is no `download_wikipedia.py`. You fetch one
`pages-articles-multistream.xml.bz2` and its `-index.txt` companion by hand,
point `constants.WIKI_CORPUS_BASE_PATH` at the directory, and index it once.

```bash
# 0. The index file must be decompressed first; the dump itself stays bz2,
#    because the builder seeks into its multistream blocks.
bunzip2 -k enwiki-20220501-pages-articles-multistream-index.txt.bz2

# 1. Index the snapshot by page title (once per snapshot; slow).
PYTHONPATH=src python src/wordfreq/corpora/build_wikipedia.py --build-index

# 2. Build either corpus from it.
PYTHONPATH=src python src/wordfreq/corpora/build_wikipedia.py \
    --corpus wiki_vital --phrases-from-db
PYTHONPATH=src python src/wordfreq/corpora/build_wikipedia.py \
    --corpus wiki_math --phrases-from-db
```

**If the snapshot is on an exFAT drive** — the usual case for 21GB on an
external disk — step 1 fails part-way with `attempt to write a readonly
database`. exFAT lacks the byte-range locking SQLite needs to *write*, though
ordinary file writes to the same directory succeed. Build the index somewhere
local and copy it back afterwards; reading an exFAT-hosted index works fine, so
the finished index can live beside the dump:

```bash
PYTHONPATH=src python src/wordfreq/corpora/build_wikipedia.py \
    --build-index --offset-dir data/working/wiki_offset
rsync -a data/working/wiki_offset/ "$WIKI_BASE/offset/"
```

| Corpus | Articles | Contents |
| --- | --- | --- |
| `wiki_vital` | 1000 | Wikipedia's "Vital articles" selection, in eleven topic groups — a general sample of modern encyclopedic English |
| `wiki_math` | 299 | Mathematics in depth, from arithmetic to category theory. A strict superset of the vital list's 53-title Mathematics section |

`wiki_math` is now built and registered in `CORPUS_CONFIGS`, at weight 0.5 —
the lowest here. It is the smallest corpus (294 articles, ~1.1M tokens) and a
single narrow register, so it earns its place by covering mathematical
vocabulary the other seven barely touch rather than by describing how English
is weighted. Registration waited on the file existing: an enabled corpus with
no JSON file makes `combined_rank` charge every lemma that corpus's
unknown-rank floor.

The dump is a *multistream* bz2: it concatenates independently compressed ~2MB
blocks, so a block holding a given page can be seeked to and decompressed
alone. `wiki_dump.py` turns the index file into SQLite databases sharded by the
MD5 of the page title, and the builder then asks for its articles by name. A
title that has been renamed since the snapshot was taken is reported as missing
and costs the corpus one document rather than failing the run.

**Wikitext is parsed, not regex-stripped.** Its constructs nest — a template
argument holds another template, an infobox holds a table holding links — and a
pattern like `\{\{[^}]*\}\}` stops at the first `}}` it meets, so on
`{{convert|5|km|{{abbr|mi}}}}` it consumes through the inner close and leaves
`}}` behind as prose. The previous version of `wiki_vital.json` was built that
way. `wiki_text.py` instead runs a character-level tokenizer into a block tree,
so every construct closes where it actually closes. Links contribute their
display text (`[[Pablo Picasso|Picasso]]` → "Picasso"); templates, tables,
references, headings and `[[File:]]` links contribute nothing, except the few
templates in `RAW_TEMPLATES` that wrap running prose. An infobox is a data
table, and counting it would put "caption", "align" and "px" into an English
frequency list.

Two defaults differ from the book builder's. `--full-weight-tokens` is 2500
rather than 20000 (a substantial article runs to about 5000 tokens of prose
once apparatus is stripped), and `--min-articles` is 15 for `wiki_vital`
against `--min-books` 3, because there are 1000 documents rather than 54.
`--section` limits a run to one group of the article list.

## How words are counted

**Boilerplate is stripped.** Everything outside the
`*** START OF THE PROJECT GUTENBERG EBOOK ***` / `*** END OF ... ***` markers
is dropped, along with the "Produced by ..." credits, `[Illustration: ...]`
and transcriber's notes. Pre-2006 files that use the `*END*THE SMALL PRINT*`
header are handled too. A file with no recognizable markers is counted whole
rather than skipped.

**Proper nouns are separated per book.** A word is treated as a name in a
given book when its occurrences *away from a sentence or line start* are at
least 90% capitalized. Judging it per book means `rose` can be a character in
one novel and a flower in the next; judging it away from line starts keeps
verse and chapter headings from marking every word a name. Names are reported
in `name_frequency`, not silently dropped. `I`/`I'm`/`I've` and friends are
exempt — the previous 19th-century corpus lost the first-person pronoun
entirely to this rule.

**Apostrophes and dashes are folded before counting.** Books are individually
consistent in their typography but differ from each other, so `don't`, `don’t`
and `donʼt` would otherwise be three separate words and `--min-books` could
drop all three. Every apostrophe variant becomes ASCII `'`; every dash variant
(and `--`) becomes a word separator, because an unspaced em dash is ordinary
19th-century typesetting rather than a compound. A plain hyphen is left alone.

**Rank comes from a word's average rate across books, not pooled counts.**
Pooling lets one long book decide a word's rank: that is why `whale` sat near
rank 150 in the old 19th-century corpus, on the strength of one novel.
Averaging each book's rate divides such a word by the number of books, while a
word that is genuinely common everywhere is unaffected. Books shorter than
`--full-weight-tokens` (20k) count proportionally less, so a short text cannot
swing the average. `--min-books` (default 3) then drops words that never
spread beyond a couple of books — one book's jargon and invented vocabulary.

This is also why a topic-heavy book is safe to include: the method, not the
reading list, is what kept `whale` from looking like common English.

## Output format

Matches the existing corpus files, plus a `generation` block recording the
settings used:

```json
{
  "global_word_frequency": {"the": 406936, "and": 254889, ...},
  "name_frequency": {"84_Frankenstein__Or__The_Modern_Prometheus": {"elizabeth": 88, ...}},
  "books_processed": ["84_Frankenstein__Or__The_Modern_Prometheus", ...],
  "total_unique_words": 27758,
  "total_names_identified": 37795,
  "generation": {"corpus": "19th_books", "weighting": "per-book-mean", ...}
}
```

Counts in `global_word_frequency` are scaled to the size of the whole corpus,
so they read like occurrence counts; only their ratios are meaningful.

## After generating

Every corpus here — the five book lists, `legal_scotus`, `wiki_vital` and
`wiki_math` — is enabled in `wordfreq.frequency.corpus.CORPUS_CONFIGS`, and
each one's JSON exists.
**Import them before relying on `combined_rank`**: an enabled corpus with no annotations makes
`combined_rank` charge every lemma that corpus's unknown-rank floor, which
drags every rank down.

The `cooking` corpus replaces the older hand-built `cooking_wordfreq.json`
(the file is renamed to `cooking.json`, matching every other corpus). Five of
that file's seven books carried their Gutenberg IDs in the `books_processed`
keys and are carried over; the other two (`veg100`, `bread_500`) were locally
named files with no recoverable ID, so vegetarian cookery and a baking-heavy
volume stand in for them.

## Adding or changing books

Edit `book_lists.py`. **Check every new ID with `--verify` before committing
it** — of 35 IDs written from memory for the science list, 15 pointed at an
unrelated book, which would have fed the corpus the wrong text silently. Put
anything unchecked in `UNVERIFIED_IDS` in the meantime; a test fails if it is
not empty. Each entry's `title` and `author` are the Gutenberg catalogue values
for that ID, and `year` is the work's first publication,
which is what decides the century list it belongs in. Tests in
`src/tests/wordfreq/corpora/test_book_lists.py` check for duplicate IDs,
cross-corpus overlap, century boundaries, list size, a cap of two works per
author across all the lists together, and that no unverified ID ships. No work appears twice (a complete
posting and its volume splits are never both included). Volume splits of a
single work are deliberately excluded so no book is counted twice.
