# Wordfreq regeneration — October 17, 2026

Regenerated the 18 locally accessible corpora using the shared version-2 casing pipeline and `--phrases-from-db`. List limits are unchanged. Each new output retains all previously included source documents, parses through the production corpus importer, and has positive integer frequencies in descending order. The database was read for phrases but was not reimported or otherwise updated.

OpenStax society was regenerated and checked first before the remaining builds started: `Lgbtq` became `LGBTQ`, `US` stayed separate from `us`, and `AIDS` was preserved. `THE`, `The`, and uppercase article `A` did not appear in that list. Existing `U` and lowercase `i` artifacts predate this regeneration. Rare lowercase `aids` falls outside that corpus’s 5,500-entry limit.

## Rebuilt corpora

| Corpus | Entries | Documents before → after | Tokens counted |
| --- | ---: | ---: | ---: |
| `19th_books` | 10,000 | 54 → 54 | 8,033,558 |
| `20th_books` | 10,000 | 62 → 62 | 5,031,429 |
| `religious_translated` | 5,200 | 23 → 23 | 5,660,665 |
| `early_modern_science` | 5,200 | 24 → 24 | 2,931,926 |
| `cooking` | 2,600 | 10 → 10 | 950,819 |
| `legal_scotus` | 10,000 | 1,474 → 1,474 | 5,162,088 |
| `eu_parliament_debates` | 5,500 | 1,332 → 1,332 | 9,868,800 |
| `openstax_science` | 5,500 | 242 → 242 | 2,642,169 |
| `openstax_society` | 5,500 | 217 → 217 | 2,701,120 |
| `wiki_arts` | 5,000 | 702 → 702 | 3,763,680 |
| `wiki_society` | 5,500 | 1,172 → 1,172 | 6,747,778 |
| `wiki_linguistics` | 4,500 | 592 → 592 | 2,174,986 |
| `wiki_physical_science` | 4,000 | 1,313 → 1,313 | 4,691,616 |
| `wiki_history` | 4,500 | 2,600 → 2,600 | 17,780,915 |
| `wiki_math` | 4,000 | 292 → 292 | 924,640 |
| `wiki_geography` | 4,500 | 1,200 → 1,200 | 7,522,483 |
| `wiki_biology` | 4,500 | 1,004 → 1,004 | 3,393,122 |
| `wiki_modern_life` | 5,000 | 1,199 → 1,199 | 5,606,881 |

## Capitalization checks

| Corpus | Spelling | Previous count | Regenerated count |
| --- | --- | ---: | ---: |
| `openstax_society` | `Lgbtq` | 180 | — |
| `openstax_society` | `LGBTQ` | — | 180 |
| `openstax_society` | `US` | — | 350 |
| `openstax_society` | `us` | 939 | 940 |
| `openstax_society` | `Aids` | 73 | — |
| `openstax_society` | `AIDS` | — | 72 |
| `eu_parliament_debates` | `Ecu` | 865 | — |
| `eu_parliament_debates` | `ECU` | — | 866 |
| `eu_parliament_debates` | `Ngo` | — | — |
| `eu_parliament_debates` | `NGO` | — | 104 |
| `eu_parliament_debates` | `US` | — | 1407 |
| `eu_parliament_debates` | `us` | 15923 | 15917 |
| `eu_parliament_debates` | `AIDS` | — | 314 |
| `eu_parliament_debates` | `aids` | 109 | 110 |
| `openstax_science` | `pH` | — | 522 |
| `openstax_science` | `Ph` | — | — |

`THE` is absent from all 18 rebuilt lists. The malformed `Lgbtq` and `Ecu` spellings are absent as well. Title/letter uses of `The` and `A` remain in some Wikipedia lists; these spellings also existed in the previous outputs. Capitalization alone does not establish semantic readings.

### Existing capitalized forms to review separately

| Corpus | Spelling | Previous count | Regenerated count |
| --- | --- | ---: | ---: |
| `wiki_arts` | `The` | 11985 | 11883 |
| `wiki_arts` | `A` | 1991 | 2020 |
| `wiki_linguistics` | `A` | 998 | 1001 |
| `wiki_history` | `The` | 33627 | 33470 |
| `wiki_history` | `A` | — | 6954 |
| `wiki_math` | `A` | 1138 | 1145 |
| `wiki_biology` | `A` | 1715 | 1641 |

## WPA remains blocked

`wpa_life_histories.json` was not regenerated. macOS returned `Operation not permitted` for `/Volumes/Dorothy Day/wpalh/text`, including an attempted read outside the sandbox. Its existing output is unchanged. Regenerating it requires an accessible source-cache copy or macOS access to that external volume.

The initial regeneration did not modify the database. The subsequent authorized reimport is recorded below.

## Database reimport completed

Ran the existing `storage.admin --repopulate` workflow with LLM calls disabled: cleared derived frequency data, synchronized configuration, loaded all 19 corpus JSON files, refreshed tier annotations, rebuilt form links, and recalculated token and lemma ranks. WPA was loaded from its unchanged JSON file.

Took a **major** backup before rebuilding derived data: `data/wordfreq/backups/major/linguistics.sqlite.bak-20261017-reimport-wordfreq`.

Validated every corpus’s exact token set against its source JSON. All 32,249 English tokens have ranks. The old `Ngo`, `Ecu`, and `Lgbtq` tokens are absent; corrected spellings are present. WPA’s 10,000 stored token/rank/frequency rows exactly match the pre-import snapshot.

Dictionary counts remain unchanged: 10,179 lemmas, 189,299 derivative forms, and 2,932 variant forms. No annotation or form references a missing token. No release generation was performed.
