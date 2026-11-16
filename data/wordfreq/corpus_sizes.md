# Corpus sizes

Approximate size of each word-frequency corpus in this directory, as of
2026-11-16.  Read from the JSON files themselves; nothing is recomputed from
source text.

* **Tokens** is `generation.total_tokens`, every token the builder counted.
* **Published sum** is the sum of the `global_word_frequency` values, the
  estimate available from the published list alone.  It runs 3-15% under the
  token count because only the top `max_words` words are published.
* **Docs** is the number of documents (books, articles, opinions, interviews).
* **Last count** is the frequency of the last word that made the list.  It is
  the best guide to headroom: a corpus whose cutoff word still occurs 50+
  times could publish a longer list.  20 is the intended floor for a word to
  rank reliably; several corpora are below it and will be re-adjusted.
* **Weight** is `corpus_weight` in `wordfreq.frequency.corpus.CORPUS_CONFIGS`
  (blank: not registered).

| Corpus | Tokens | Published sum | Docs | Unique words | Published (cap) | Min docs | Last count | Weight |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| wiki_history | 17.5M | 15.9M | 2,600 | 276,122 | 20,000 | 25 | 44 | 0.6 |
| eu_parliament_debates | 9.9M | 9.7M | 1,332 | 47,686 | 11,000 | 8 | 24 | 0.5 |
| 19th_books | 8.0M | 7.7M | 54 | 71,130 | 15,000 | 3 | 19 | 0.8 |
| wiki_geography | 7.5M | 6.6M | 1,200 | 197,137 | 9,000 | 15 | 61 | 0.5 |
| wiki_society | 6.7M | 6.1M | 1,172 | 142,163 | 11,000 | 15 | 44 | 0.8 |
| religious_translated | 5.7M | 5.4M | 23 | 58,129 | 10,400 | 3 | 22 | 0.5 |
| wiki_modern_life | 5.6M | 5.0M | 1,199 | 115,950 | 10,000 | 15 | 42 | 0.8 |
| legal_scotus | 5.2M | 5.0M | 1,474 | 51,538 | 12,500 | 8 | 15 | 0.7 |
| 20th_books | 5.0M | 4.8M | 62 | 56,903 | 15,000 | 3 | 12 | 0.9 |
| wpa_life_histories | 4.9M | 4.6M | 2,622 | 230,322 | 15,000 | 10 | 13 | 0.5 |
| wiki_physical_science | 4.7M | 4.3M | 1,313 | 86,796 | 8,000 | 15 | 42 | 0.5 |
| wiki_arts | 3.7M | 3.3M | 702 | 118,453 | 10,000 | 11 | 29 | 0.8 |
| oanc_slate | 3.6M | 3.4M | 3,819 | 77,467 | 15,000 | 8 | 17 | 0.8 |
| wiki_biology | 3.4M | 3.0M | 1,004 | 108,425 | 9,000 | 15 | 23 | 0.5 |
| early_modern_science | 2.9M | 2.8M | 24 | 54,551 | 10,400 | 3 | 15 | 0.6 |
| openstax_society | 2.7M | 2.6M | 217 | 52,424 | 11,000 | 3 | 15 | 0.5 |
| openstax_science | 2.6M | 2.5M | 242 | 42,854 | 11,000 | 3 | 13 | 0.5 |
| wiki_linguistics | 2.2M | 1.9M | 591 | 95,947 | 8,000 | 10 | 13 | 0.5 |
| cooking | 0.95M | 0.90M | 10 | 14,806 | 3,500 | 3 | 14 | 0.7 |
| wiki_math | 0.92M | 0.87M | 292 | 22,711 | 4,500 | 5 | 12 | 0.5 |

## Count cutoffs

The last rank whose word occurs at least 20, 10 and 8 times, for the corpora
whose cutoff word is under 20.  "past cap" means the threshold lies beyond the
published list, so only an uncapped rebuild can say where.  Every other
corpus is at 20+ at its cap.

The values are per-document-weighted scores scaled to the token total, not
raw occurrence counts, so a word can sit in more documents than its "count".
That is why a list's tail drops steeply where the minimum-document rule ends
it: wiki_history (then min 30 articles), from an uncapped trial build, had
25,705 eligible words, stayed at 20+ to about rank 23,000, then fell to 1 by
the last of them.  The lowest of those are lowercase spellings of names
("wellington"), which pass the article test on the combined spelling.

The cooking, wiki_math, wiki_linguistics and legal_scotus rows below are from
before their caps were cut in Nov 2026 (to 3,500, 4,500, 8,000 and 12,500;
cutoff words now at 14, 12, 13 and 15).

| Corpus | Cap | Last count | Count >= 20 | Count >= 10 | Count >= 8 |
| --- | ---: | ---: | ---: | ---: | ---: |
| cooking | 5,200 | 5 | 2,863 | 4,189 | 4,599 |
| wiki_math | 6,000 | 6 | 3,362 | 4,995 | 5,545 |
| wiki_linguistics | 9,000 | 8 | 6,659 | 8,803 | past cap |
| legal_scotus | 15,000 | 8 | 11,052 | 14,524 | past cap |
| 20th_books | 15,000 | 12 | 11,246 | past cap | past cap |
| wpa_life_histories | 15,000 | 13 | 11,691 | past cap | past cap |
| openstax_science | 11,000 | 13 | 8,707 | past cap | past cap |
| openstax_society | 11,000 | 15 | 9,357 | past cap | past cap |
| early_modern_science | 10,400 | 15 | 8,763 | past cap | past cap |
| oanc_slate | 15,000 | 17 | 13,510 | past cap | past cap |
| 19th_books | 15,000 | 19 | 14,984 | past cap | past cap |

Changing a corpus's length means changing both its builder's default
`--max-words` and the `max_words` in its `CORPUS_CONFIGS` entry (with
`max_unknown_rank` at twice it), then rebuilding the JSON.  Published length
is also part of a corpus's influence on `combined_rank`, so a longer list is a
heavier corpus in the tail.
