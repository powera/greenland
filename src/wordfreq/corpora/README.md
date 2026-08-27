# Corpus generation

Builds the `data/wordfreq/*.json` word-frequency corpora. Two builders share
this directory, and everything after text extraction is common code in
`frequency_build.py` — proper-noun detection, per-document weighting and the
output format are the same for both:

| Builder | Source | Corpora |
| --- | --- | --- |
| `build_gutenberg.py` | Project Gutenberg books | the five below |
| `build_scotus.py` | Supreme Court opinions | `legal_scotus` |

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

Every corpus here — the five book lists and `legal_scotus` — is enabled in
`wordfreq.frequency.corpus.CORPUS_CONFIGS`, and each one's JSON exists.
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
