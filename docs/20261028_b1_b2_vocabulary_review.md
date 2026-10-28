# B1/B2 category population proposal — 2026-10-28

Status: **live import completed successfully with user approval on 2026-10-28**, using `gpt-6-luna`; process exit code 0. Output: `/tmp/greenland-b1-b2-live-20261028.log`. Minor backup: `data/wordfreq/backups/minor/linguistics.sqlite.bak-20261028-b1-b2-additions`. Results: 202 created senses, 2 covered existing senses, all 30 explicit moves verified at their destination in a read-only database check, no reported failures. The log records 25 low-confidence translation drops across 18 missing-translation reports; these require later review rather than assuming full translation coverage. Level populations after import: 134=31, 151=19, 176=26, 216=29, 227=37, 296=32, 312=28, 341=30. Category metadata/names remain absent, as expected: this script does not create level metadata. No release export or audio generation was run.

The script contains **204 proposed sense additions and 30 explicit existing-GUID moves**, across the eight requested semantic categories. These are 234 planned operations, not 234 guaranteed new lemmas: the server may match an existing sense or defer an uncertain result for review. Existing-GUID moves run after the sense additions. No audio generation or release export is included.

## Current script and category breakdown

Canonical headwords, intended senses, fixed POS and explicit GUIDs live in `scripts/wordlists/import_b1_b2_categories.py`. Default execution prints the plan with no network/database access. Only `--execute` uses the existing paid Barsukas `add_sense` pipeline and applies the GUID moves. That requires separate approval before running. No level metadata is created by this script; category titles are proposed names. The caller must arrange the normal database backup before execution.

The names describe semantic/lexical categories rather than situations such as “at the office.” Health moved from the initially suggested 451 to **134**, beside Health and Body (133). Level numbers identify categories, not teaching order or CEFR difficulty. Previously verified live metadata and assignment checks found all eight slots free.

| Level | Proposed category | Sense additions | Existing moves | Existing coverage boundary |
| --- | --- | ---: | ---: | --- |
| 134 | Health, Symptoms and Treatment | 28 | 3 | Keep existing health/body 133 and illness/medicine 450 senses. |
| 151 | Judgment and Communication Verbs | 8 | 11 | Keep already taught thinking 150 and speaking 480 senses. |
| 176 | Money, Payments and Agreements | 24 | 2 | Keep payment/debt/profit/currency and borrowing/lending prerequisites. |
| 216 | Scheduling and Service Terms | 26 | 3 | Keep complaint, repair, replace and other already placed service vocabulary. |
| 227 | Linking, Time and Degree Adverbs | 36 | 1 | Keep existing 105 adverbs and 304 connectors; extend with time/degree/stance. |
| 296 | Employment Terms | 28 | 5 | Keep existing professions, employer, applicant, interview and application. |
| 312 | Social Relationships and Reactions | 26 | 2 | Keep existing emotions, trust, forgiveness and support senses. |
| 341 | Digital Information and Access | 28 | 3 | Keep existing devices 185 and computer vocabulary 140. |

## Curation and verified provenance

The shortlist started with the previous 47-entry draft, expanded with practical everyday vocabulary and a **live top-400 English unmatched-token review**. The existing `storage.word_token_view.unlinked_word_tokens(session, "en", limit=400)` helper was called with its normal function-word filtering. It measures unclaimed token forms, not missing dictionary senses. Inspection used `DataSourceConfig` for the SQLite path, URI `mode=ro`, `PRAGMA query_only=ON`, an SQLAlchemy session bound to that read-only connection, and `GREENLAND_TEST_MODE=1 PYTHONPATH=src`. No schema/session initialization helper capable of migration was used.

317 candidate term/POS combinations were checked against exact live English lemma text, English translation rows, pending `english_word` and `queried_word`, and the definitions of existing matches. Already taught matching senses were removed, wrong-sense/POS matches were retained with explicit hints, and matching higher-level senses became exact GUID moves. All 204 selected additions currently have **no exact pending-import headword/query match**. Relationship remains excluded because pending IDs 10–13 already cover candidate senses; none is approved by this script. This preflight is a snapshot, not a future guarantee: recheck the pending queue before live execution.

47 distinct selected headwords also occur in the current top-400 list. Their token ranks are shown below; these ranks do not certify the particular intended sense. The other proposals come from the eight reviewed semantic categories, not an invented claim that all 204 were among the top 400.

financial (1415), besides (1459), professional (1483), nevertheless (1541), similarly (1560), specifically (1619), conflict (1673), occasionally (1719), moreover (1768), income (1796), currently (1843), initially (1888), necessarily (1915), equally (1929), ultimately (1932), significantly (1949), consequently (1995), roughly (2024), rarely (2069), normally (2071), increasingly (2096), permanent (2108), shift (2130), formerly (2190), subsequently (2211), constantly (2237), namely (2270), essentially (2280), accurate (2283), relevant (2313), afterwards (2350), notably (2384), readily (2438), effectively (2515), sufficiently (2528), shortly (2529), thoroughly (2558), responsibility (2559), furthermore (2601), assistance (2607), literally (2614), partially (2625), precisely (2646), confidence (2693), regularly (2714), sensitive (2726), electronic (2787).

Obvious names, capitalization variants, fragments and noise were excluded (e.g. God, Mr, Union, BC, non, pre). Inflected strings such as stated, consists, employed, scholars and patients were not turned into new headword lemmas. Their base-sense/forms/linking paths need separate review. Existing broad senses that cover the intended use were preserved rather than split unnecessarily (for example save, network, source and performance).

## CEFR evidence and limitations

Local `external_lexeme_annotations` entries from source `cefr`, joined through English `word_tokens`, provide **same-POS** evidence for 162 of the 204 addition proposals: A1 1, A2 25, B1 82, B2 54. The remaining 42 have no same-POS CEFR annotation in this snapshot; their inclusion is editorial, based on useful everyday communication and category fit. Token/POS annotations do not establish sense-specific or multilingual CEFR certification.

The following were deferred after local C1-only evidence: fatigue, numb, collaborate and reassure. Invoice was also excluded (C1 noun), and arguably was left out rather than padding the adverb category. No selected addition has a local same-POS C1/C2 annotation in the checked dataset. Missing annotations do not prove A/B level. Ordinary prominent intended senses are marked `prominence="common"` in this draft; this is an editorial prominence choice, not corpus-derived per-sense measurement.

The new 227 title is **Linking, Time and Degree Adverbs**: it includes useful temporal/frequency/degree items as well as connectors, avoiding a forced pile of rare formal connectors. Existing whereas moves there as a clearly marked conjunction exception, just as practical categories may include more than one POS.

## Sense distinctions and duplicate protection

Every addition fixes its POS and intended meaning. Examples: patient noun vs the existing patient adjective; payment bill vs the performer-listing verb; online account vs bank account; employment promotion/resign vs sport/game meanings; medical treatment vs material processing; digital link vs a chain component; and work shift vs astronomical redshift. The script keeps the natural headword **treatment**, with a medical hint, rather than inventing “medical treatment” merely to bypass existing-headword checks.

The normal `add_sense` matcher reviews **same-headword** existing senses and can preserve an existing placement (`move=False`). It does not automatically deduplicate cross-headword synonyms: nevertheless/however and consequently/therefore may be legitimate distinct lexical items even when their definitions overlap, and require editorial judgment rather than a promise of automatic conceptual deduplication. No translations are guessed in the script; translations/forms/persistence use the existing Barsukas pipeline after execution approval.

GUID moves are separate from model sense matching. They preserve existing facts/forms/translations and do not reset prominence through `relevel_existing`. The shared `LevelMove` helper checks GUID/headword and skips an already completed move, but **does not require an expected old level**. Recheck intervening manual placements before a live run. The current 30 sources are all above 999; no already placed prerequisite below 999 is moved.

## Complete addition shortlist

The script is canonical for precise sense hints; these lists provide a compact review of all 204 proposed additions.

### 134 — Health, Symptoms and Treatment

**noun:** symptom, treatment, recovery, side effect, patient, checkup, bruise, swelling, rash, nausea, appetite, vaccination, emergency.

**verb:** recover, diagnose, heal, bleed, faint, vomit, prescribe.

**adjective:** dizzy, painful, swollen, contagious, chronic, acute, mild, unconscious.

### 151 — Judgment and Communication Verbs

**verb:** negotiate, suspect, propose, acknowledge, emphasize, question, reconsider, weigh up.

### 176 — Money, Payments and Agreements

**noun:** rent, budget, deposit, bill, charge, loan, savings, expense, income, discount, bargain, installment, bank transfer, landlord, tenant.

**verb:** afford, owe, repay, purchase, invest, withdraw.

**adjective:** affordable, costly, financial.

### 216 — Scheduling and Service Terms

**noun:** appointment, deadline, delay, refund, booking, reservation, queue, request, confirmation, cancellation, enquiry, assistance, fault, guarantee, warranty, replacement, service charge, opening hours.

**verb:** cancel, reschedule, postpone, reserve, resolve.

**adjective:** urgent, convenient, flexible.

### 227 — Linking, Time and Degree Adverbs

**adverb:** nevertheless, consequently, moreover, furthermore, similarly, specifically, occasionally, currently, initially, necessarily, equally, ultimately, significantly, roughly, rarely, normally, increasingly, formerly, subsequently, constantly, namely, essentially, afterwards, notably, readily, effectively, sufficiently, shortly, thoroughly, literally, partially, precisely, regularly, besides, presumably, admittedly.

### 296 — Employment Terms

**noun:** colleague, salary, responsibility, shift, unemployment, promotion, qualification, vacancy, staff, workforce, profession, wage, overtime, pension, retirement, workload, skill, probation.

**verb:** resign, recruit, retire, supervise.

**adjective:** qualified, professional, experienced, competent, permanent, temporary.

### 312 — Social Relationships and Reactions

**noun:** expectation, misunderstanding, apology, compromise, confidence, sympathy, resentment, conflict, cooperation, commitment, boundary, rejection, encouragement.

**verb:** apologize, appreciate, respect, blame, insult, comfort.

**adjective:** considerate, thoughtful, supportive, sincere, awkward, sensitive.

**adverb:** politely.

### 341 — Digital Information and Access

**noun:** account, password, notification, permission, link, attachment, folder, backup, subscription, update, headline, rumor, misinformation.

**verb:** download, upload, subscribe, browse, install, delete, log in, log out, forward.

**adjective:** reliable, misleading, secure, accurate, relevant, electronic.

## Exact existing moves

| GUID | Headword | Verified current level | Proposed level |
| --- | --- | ---: | ---: |
| V18_001 | prevent | 1399 | 134 |
| N16_019 | prescription | 1070 | 134 |
| N16_015 | dose | 1050 | 134 |
| V04_082 | disagree | 1399 | 151 |
| V09_122 | advise | 1399 | 151 |
| V09_121 | refuse | 1399 | 151 |
| V09_034 | justify | 1070 | 151 |
| V04_087 | intend | 1399 | 151 |
| V09_117 | predict | 1399 | 151 |
| V04_078 | conclude | 1399 | 151 |
| V04_092 | infer | 1399 | 151 |
| V04_096 | deduce | 1399 | 151 |
| V04_076 | contrast | 1399 | 151 |
| V09_107 | admit | 1399 | 151 |
| N59_064 | contract | 1399 | 176 |
| N55_051 | lease | 1070 | 176 |
| N24_301 | schedule | 1399 | 216 |
| N17_312 | requirement | 1070 | 216 |
| V09_162 | arrange | 1399 | 216 |
| C99_044 | whereas | 1399 | 227 |
| N36_107 | employee | 1070 | 296 |
| N36_153 | occupation | 1399 | 296 |
| N50_215 | reference | 1399 | 296 |
| V06_065 | employ | 1399 | 296 |
| V08_047 | dismiss | 1399 | 296 |
| N23_038 | loyalty | 1030 | 312 |
| N23_039 | relief | 1070 | 312 |
| N52_025 | browser | 1040 | 341 |
| N54_065 | privacy | 1070 | 341 |
| N17_316 | consent | 1070 | 341 |

Move sources: 1 at 1030, 1 at 1040, 1 at 1050, 8 at 1070, 19 at 1399.

## Conversation and narrative affordances

These remain ideas for future authoring, not generated/approved sentence records:

- Health: describe symptoms, understand a prescription and ask about recovery or side effects.
- Thought/communication verbs: explain reasoning, challenge an assumption and negotiate a decision.
- Money: explain a deposit, compare expenses and resolve a payment problem.
- Scheduling/services: change an appointment, explain a fault and ask about a refund.
- Adverbs/connectors: narrate the sequence of events and qualify an explanation.
- Employment: describe a shift, responsibilities, qualifications or a job change.
- Social relationships: explain a misunderstanding, apologize and reach a compromise.
- Digital information: manage access, exchange files and evaluate a misleading claim.

## Validation completed

Black and mypy pass for the script. A no-network preview check patched `requests.sessions.Session.request` to raise on any HTTP attempt and ran the actual default entry point successfully. Assertions verify 204 unique term/POS additions, fixed POS/hints, `move=False` on sense matches, common prominence, eight categories, no relationship approval, and 30 distinct existing GUID moves. Live read-only checks verified all move headwords/source levels above 999, absence of selected exact pending terms, and the local CEFR summary above. No paid execution was performed.

Before running live: review the shortlist and level metadata names, recheck changed placements/pending rows, arrange the required backup, approve the live model call, and retain its normal persistent results/logs. A successful preview validates the plan structure, not model output quality or translation completeness.

## Mechanical forms qualification

An unmatched token does not establish an absent lemma. Parent inspection found all 1,793 level-1399 lemmas have some English forms, while sampled state/consist/employ senses have only infinitives and no English grammar facts. `src/langtools/en/mechanical.py` requires past and past-participle facts before expanding a verb paradigm and has no level filter. Inflected-token gaps can therefore be missing source facts/forms or linking problems; do not create duplicate lemmas to cover them.
