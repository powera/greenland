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
  the best guide to headroom: a corpus whose cutoff word still occurs 100+
  times could publish a much longer list, and one at 5-8 is near the floor its
  minimum-document rule allows.
* **Weight** is `corpus_weight` in `wordfreq.frequency.corpus.CORPUS_CONFIGS`
  (blank: not registered).

| Corpus | Tokens | Published sum | Docs | Unique words | Published (cap) | Min docs | Last count | Weight |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| wiki_history | 17.5M | 14.9M | 2,600 | 275,236 | 9,000 | 30 | 165 | 0.6 |
| eu_parliament_debates | 9.9M | 9.7M | 1,332 | 47,686 | 11,000 | 8 | 24 | 0.5 |
| 19th_books | 8.0M | 7.7M | 54 | 71,130 | 15,000 | 3 | 19 | 0.8 |
| wiki_geography | 7.5M | 6.6M | 1,200 | 197,137 | 9,000 | 15 | 61 | 0.5 |
| wiki_society | 6.7M | 6.1M | 1,172 | 142,163 | 11,000 | 15 | 44 | 0.8 |
| religious_translated | 5.7M | 5.4M | 23 | 58,129 | 10,400 | 3 | 22 | 0.5 |
| wiki_modern_life | 5.6M | 5.0M | 1,199 | 115,950 | 10,000 | 15 | 42 | 0.8 |
| legal_scotus | 5.2M | 5.0M | 1,474 | 51,203 | 15,000 | 8 | 8 | 0.7 |
| 20th_books | 5.0M | 4.8M | 62 | 56,903 | 15,000 | 3 | 12 | 0.9 |
| wpa_life_histories | 4.9M | 4.6M | 2,622 | 230,322 | 15,000 | 10 | 13 | 0.5 |
| wiki_physical_science | 4.7M | 4.3M | 1,313 | 86,796 | 8,000 | 15 | 42 | 0.5 |
| oanc_slate | 4.1M | 3.9M | 4,530 | 79,662 | 20,000 | 8 | 12 | |
| wiki_arts | 3.7M | 3.3M | 702 | 118,453 | 10,000 | 11 | 29 | 0.8 |
| wiki_biology | 3.4M | 3.0M | 1,004 | 108,425 | 9,000 | 15 | 23 | 0.5 |
| early_modern_science | 2.9M | 2.8M | 24 | 54,551 | 10,400 | 3 | 15 | 0.6 |
| openstax_society | 2.7M | 2.6M | 217 | 52,424 | 11,000 | 3 | 15 | 0.5 |
| openstax_science | 2.6M | 2.5M | 242 | 42,854 | 11,000 | 3 | 13 | 0.5 |
| wiki_linguistics | 2.2M | 2.0M | 591 | 95,688 | 9,000 | 10 | 8 | 0.5 |
| cooking | 0.95M | 0.92M | 10 | 14,741 | 5,200 | 3 | 5 | 0.7 |
| wiki_math | 0.92M | 0.88M | 292 | 22,592 | 6,000 | 5 | 6 | 0.5 |

Changing a corpus's length means changing both its builder's default
`--max-words` and the `max_words` in its `CORPUS_CONFIGS` entry, then
rebuilding the JSON.  Published length is also part of a corpus's influence on
`combined_rank`, so a longer list is a heavier corpus in the tail.
