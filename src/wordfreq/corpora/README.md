# Gutenberg corpus generation

Builds the `data/wordfreq/*.json` word-frequency corpora from Project
Gutenberg books. Three corpora have book lists here:

| Corpus | Books | Contents |
| --- | --- | --- |
| `19th_books` | 64 | Novels, children's books, essays and science first published 1800-1899, British / American / translated European |
| `20th_books` | 70 | Books first published 1900-1938, i.e. what Gutenberg carries of the 20th century |
| `early_modern_science` | 37 | Science writing from Boyle and Newton to Einstein and Eddington, written in English by its authors (Einstein excepted) |
| `religious_translated` | 23 | Old religious works in English translation: Bible (three translations), Apocrypha, Enoch, Talmud selections, Qur'an (two translations), Upanishads, Bhagavad-Gita, Mahabharata, Ramayana, Dhammapada, Tao Te Ching, Analects, Shih King, Eddas, Egyptian Book of the Dead, Augustine, Aquinas, à Kempis |

## Running it

Two steps. The first is the only one that touches the network.

```bash
# 0. Confirm the book IDs point at the books they claim (metadata only, no
#    book text). Needed for any ID listed in book_lists.UNVERIFIED_IDS.
PYTHONPATH=src python src/wordfreq/corpora/download_gutenberg.py \
    --corpus early_modern_science --verify

# 1. Download the books to a scratch directory (not the repo).
PYTHONPATH=src python src/wordfreq/corpora/download_gutenberg.py --corpus all

# 2. Build each corpus JSON from the cache.
PYTHONPATH=src python src/wordfreq/corpora/build_wordfreq.py --corpus 19th_books
PYTHONPATH=src python src/wordfreq/corpora/build_wordfreq.py --corpus 20th_books
PYTHONPATH=src python src/wordfreq/corpora/build_wordfreq.py --corpus religious_translated
PYTHONPATH=src python src/wordfreq/corpora/build_wordfreq.py --corpus early_modern_science
```

The cache defaults to `$GREENLAND_GUTENBERG_CACHE`, else
`<tempdir>/greenland-gutenberg`; `--dest` / `--source-dir` override it.
Downloads are skipped when the file is already cached, so step 2 can be redone
freely — it is deterministic and needs no network. `--delay` (default 1.5s)
paces requests to gutenberg.org; keep it polite.

Useful flags on the builder: `--dry-run` (report without writing),
`--report FILE` (per-book token/name counts), `--weighting pooled` (the old
behaviour, see below), `--min-books`, `--max-words`, `--skip-missing`.

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

`religious_translated` and `early_modern_science` ship **disabled** in
`wordfreq.frequency.corpus.CORPUS_CONFIGS`. Enable each once its JSON exists
and has been imported — an enabled corpus with no annotations makes
`combined_rank` charge every lemma that corpus's unknown-rank floor.

## Adding or changing books

Edit `book_lists.py`. IDs listed in `UNVERIFIED_IDS` were written from memory
and have not been checked against the catalogue — run `--verify` (above), fix
any mismatch, and clear the ID from that set. Every other entry's `title` and
`author` are the Gutenberg catalogue values for that ID, and `year` is the work's first publication,
which is what decides the century list it belongs in. Tests in
`src/tests/wordfreq/corpora/test_book_lists.py` check for duplicate IDs,
cross-corpus overlap, century boundaries and list size. Volume splits of a
single work are deliberately excluded so no book is counted twice.
