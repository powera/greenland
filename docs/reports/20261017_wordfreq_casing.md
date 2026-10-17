# Wordfreq casing comparison — October 17, 2026

Baseline commit: `fb66f54fd3a351635cfb47e5b0bd2c9dd0629fda`.

Offline comparison against the pre-change HEAD implementation on identical cached text. No database, phrase index, downloads, or generated corpus files were used or modified. These are sample rankings, not replacement production corpora. The old OpenStax spread filter and Europarl rank cutoff are included in the baseline. Gutenberg uses three novels without the database vocabulary allowlist. Europarl spelling folds and WPA OCR corrections are outside this casing comparison.

WPA extracted text is on an external volume that this session cannot read; its shared path and pooled-name retention are covered by regression tests.

## Gutenberg (three novels)

3 documents; 419,021 tokens. Uncapped entries: 3,073 old → 3,102 new. At a comparable 3,073-entry cap, 32 former entries leave the list (including spellings corrected or folded). Retaining every surviving old top-3,073 spelling would require 3,099 slots.

| Spelling | Old rank | New rank | New estimated count |
| --- | ---: | ---: | ---: |
| `us` | 117 | 120 | 398 |
| `it` | 11 | 11 | 4319 |
| `the` | 1 | 1 | 22272 |

Highest-ranked newly published spellings: `Mr`, `Elizabeth`, `Mrs`, `Miss`, `chapter`, `Captain`, `God`, `aunt`, `William`, `Chapter`, `London`, `captain`, `England`, `Mary`, `Henry`, `English`, `St`, `French`, `Christian`, `Scotland`, `lakes`, `god`, `Sunday`, `God's`, `John`.

## OpenStax society (all cached chapters)

217 documents; 2,723,145 tokens. Uncapped entries: 22,797 old → 22,728 new. At a comparable 5,500-entry cap, 44 former entries leave the list (including spellings corrected or folded). Retaining every surviving old top-5,500 spelling would require 6,310 slots.

| Spelling | Old rank | New rank | New estimated count |
| --- | ---: | ---: | ---: |
| `Ngo` | 12196 | — | — |
| `NGO` | — | 15382 | 7 |
| `Lgbtq` | 1877 | — | — |
| `LGBTQ` | — | 1879 | 180 |
| `US` | — | 987 | 349 |
| `us` | 322 | 323 | 941 |
| `it` | 17 | 17 | 13350 |
| `AIDS` | — | 3858 | 72 |
| `aids` | 7406 | 7270 | 28 |
| `the` | 1 | 1 | 179858 |

Highest-ranked newly published spellings: `GDP`, `BCE`, `US`, `CE`, `COVID`, `LGBTQ`, `AD`, `UN`, `DC`, `EU`, `CDC`, `MC`, `IQ`, `AIDS`, `ADHD`, `SES`, `ACA`, `APA`, `NGOs`, `NATO`, `DNA`, `SRAS`, `Songhai`, `PPF`, `MR`.

## Europarl (first 150 selected chapters)

150 documents; 1,030,420 tokens. Uncapped entries: 8,833 old → 9,260 new. At a comparable 5,500-entry cap, 439 former entries leave the list (including spellings corrected or folded). Retaining every surviving old top-5,500 spelling would require 9,097 slots.

| Spelling | Old rank | New rank | New estimated count |
| --- | ---: | ---: | ---: |
| `NGO` | — | 5375 | 9 |
| `Ecu` | 265 | — | — |
| `ECU` | — | 265 | 478 |
| `US` | — | 1830 | 56 |
| `us` | 71 | 71 | 1648 |
| `IT` | — | 6793 | 5 |
| `it` | 12 | 12 | 10701 |
| `AIDS` | — | 1798 | 57 |
| `aids` | 2850 | 2971 | 27 |
| `the` | 1 | 1 | 81584 |

Highest-ranked newly published spellings: `EU`, `ECU`, `SMEs`, `PHARE`, `NGOs`, `IGC`, `CFSP`, `EMU`, `BSE`, `EU's`, `OECD`, `AIDS`, `ACP`, `US`, `CAP`, `UK`, `UN`, `USA`, `Cooperation`, `Croatian`, `SAVE`, `Denmark`, `Conciliation`, `Customs`, `Act`.

## SCOTUS (first 30 cached cases)

73 documents; 208,227 tokens. Uncapped entries: 4,236 old → 4,294 new. At a comparable 4,236-entry cap, 130 former entries leave the list (including spellings corrected or folded). Retaining every surviving old top-4,236 spelling would require 4,294 slots.

| Spelling | Old rank | New rank | New estimated count |
| --- | ---: | ---: | ---: |
| `us` | 278 | 293 | 90 |
| `IT` | — | 4259 | 2 |
| `it` | 14 | 14 | 1385 |
| `the` | 1 | 1 | 16899 |

Highest-ranked newly published spellings: `Board's`, `Michigan`, `ACA`, `Elwell`, `Georgia`, `Rome`, `Halper`, `Immunities`, `Privileges`, `Jonathan`, `Missouri`, `Seventh`, `ADEA`, `OWBPA`, `Williams`, `Eleventh`, `Louisiana`, `Monroe`, `Powers`, `Secretary's`, `Washington`, `NLRB`, `Richardson`, `York's`, `Bell`.

## Wikipedia (first 60 cached articles)

60 documents; 278,556 tokens. Uncapped entries: 6,343 old → 6,432 new. At a comparable 5,500-entry cap, 213 former entries leave the list (including spellings corrected or folded). Retaining every surviving old top-5,500 spelling would require 6,431 slots.

| Spelling | Old rank | New rank | New estimated count |
| --- | ---: | ---: | ---: |
| `US` | — | 335 | 77 |
| `us` | 2599 | 2559 | 13 |
| `IT` | — | 5154 | 4 |
| `it` | 19 | 19 | 1189 |
| `AIDS` | — | 6412 | 1 |
| `aids` | 5665 | 6401 | 2 |
| `the` | 1 | 1 | 21099 |
| `pH` | — | 2908 | 11 |

Highest-ranked newly published spellings: `Montreal`, `Jane`, `US`, `Dutch`, `El`, `Mr`, `Canadian`, `Catholic`, `Muslim`, `Islamic`, `Iraq`, `Quebec`, `BCE`, `UK`, `Montréal`, `Tamil`, `Austria`, `England`, `Bond`, `Scottish`, `Allied`, `Indonesia`, `Club`, `Iranian`, `Jews`.

## Review implications

The comparison deliberately leaves production list limits unchanged. New names and corrected case-sensitive spellings compete for those limits. Full-corpus regeneration should be reviewed before choosing larger limits: sample-only rank movement cannot establish the right production cap.

Known case-sensitive exceptions preserve rare US/IT/AIDS readings without converting lowercase occurrences into acronyms. Unknown forms still need reliable spelling coverage and the count/share thresholds; uppercase passages provide counts but no casing evidence. This is a casing heuristic, not contextual semantic disambiguation.
