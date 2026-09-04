#!/usr/bin/env python3
"""Import the hyphenated compounds the corpora attest, which the tokenizer loses.

The corpus tokenizer splits "non-linear" into "non" and "linear" on purpose --
a plain hyphen is deliberately not in ``gutenberg_text.DASH_VARIANTS``, because
without a lemma to match against, joining every hyphen would invent compounds
out of line-broken words.  The cost of that default is visible in the frequency
list: ``non`` ranks 301 and ``self`` 381, with ``re``, ``pre``, ``anti``,
``semi``, ``multi`` and ``ex`` all inside the top 4000.  None is a lemma, none
is excluded.  Each is a fragment of a compound nobody counted.

Breaking that cycle needs the lemmas first.  The phrase index
(``wordfreq.corpora.lemma_phrases``) joins only forms the database already
holds, so the tokenizer cannot be taught to keep "non-linear" until
"non-linear" exists as a word.  This script is that step; the tokenizer change
follows it, not the other way round.

Sourced from ``scripts/find_hyphenated_candidates.py``, which re-reads the
cached corpus source text -- Gutenberg (173 books), SCOTUS (1393 opinions) and
Wikipedia (10085 articles) -- where the hyphens still survive.  It found 12851
candidates the database does not already account for; the full ranked list is
kept at ``data/working/hyphenated_candidates.txt`` and there is plenty more
worth importing below this cut.  These are the top 500 by document spread,
which is the cap for one script.

Ordering is by how many documents a compound appears in, not by raw count: a
word used forty times in one book is one author's habit, while one used across
sixty documents is vocabulary.  The weakest entry here still appears in 63
documents.

Removed by hand from the mechanical top 500:

* Anything with a nationality, language, religion or region in either half --
  ``Anglo-Saxon``, ``Indo-European``, ``African-American``, ``Sub-Saharan``,
  ``non-Jewish``, ``European-style``.  These are proper adjectives: they are
  written with a capital whichever half carries it, and the corpus confirms it
  (``African-American`` is capitalized in 137 of 137 occurrences,
  ``Anglo-Saxon`` in 29 of 29).  They are a coherent group and probably want
  their own treatment rather than being scattered through a vocabulary level.
* ``jean-jacques`` and ``notre-dame`` -- a forename and a place, picked up as
  compounds only because a hyphen joins them.
* ``al-din``, ``ad-din``, ``al-andalus``, ``al-qaeda`` -- Arabic name particles
  and proper nouns.
* ``wiley-blackwell`` -- a publisher, from Wikipedia citations.
* ``blu-ray`` and ``wi-fi`` -- brand names, capitalized in ordinary use.
* ``to-day``, ``to-morrow``, ``to-night`` -- the 19th-century hyphenation of
  words we already hold unhyphenated.  Gutenberg attests them heavily and they
  are real English, but they are archaic spellings of existing lemmas, so they
  belong wherever "saith" and "doeth" end up rather than here.
* ``centre-right`` and ``self-defence`` -- British spellings of forms whose
  American spelling we hold or will hold; these are ``variant_forms`` rows.
* ``anglo-saxons``, ``non-muslims``, ``t-shirts`` -- plurals of words that are
  either in the list already or dropped above.

Capitalization was checked rather than assumed: the discovery script lowercases
what it counts, so the case evidence was re-gathered from the Gutenberg and
SCOTUS source text before this list was cut.  Seven entries here are still
capitalized in a majority of their (few) attestations, and each was kept
deliberately:

* ``non-violence`` -- 22 of 22 from one document's section headings.
* ``secretary-general``, ``commander-in-chief``, ``major-general`` -- titles,
  capitalized when attached to a named holder and lowercase in general use.
* ``x-ray`` -- lowercase in modern use; the capitalized evidence is Gutenberg-era.
* ``south-western``, ``south-eastern`` -- roughly half and half, which is
  sentence-initial position rather than a capitalized word.

The senses these get are the server's to decide, but each is expected to be an
ordinary lowercase lemma.

Level 56 is a placeholder: it is the next free level today and carries no
claim about difficulty.  These will be re-leveled with everything else when
the level plan lands, and the level here should be changed before this runs.
Unlike the general-vocabulary levels there is no word-count target for it.

This script deliberately uses the public ``ROOT/api`` facade.  In particular,
``api.lemmas.add_word`` runs Barsukas' intelligent word workflow: the server's
LLM identifies the senses and supplies their translations, then the server
selects and stores the useful senses.  The script never supplies definitions or
translations itself.

Running without ``--execute`` only prints the plan and makes no HTTP requests.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Sequence

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.wordlist_import_helper import run_import

DIFFICULTY_LEVEL = 56

# Ordered by document spread across the three corpora, commonest first.  The
# comment on each line is the evidence: how many documents it appeared in, and
# how many times in total.
WORDS: Sequence[str] = (
    "so-called",  # 2103 docs, 3018 uses
    "well-known",  # 1561 docs, 2250 uses
    "present-day",  # 1449 docs, 2817 uses
    "large-scale",  # 1265 docs, 1818 uses
    "long-term",  # 1206 docs, 1836 uses
    "modern-day",  # 1033 docs, 1555 uses
    "short-lived",  # 765 docs, 932 uses
    "best-known",  # 755 docs, 919 uses
    "two-thirds",  # 719 docs, 1062 uses
    "second-largest",  # 458 docs, 704 uses
    "post-war",  # 452 docs, 727 uses
    "long-distance",  # 434 docs, 695 uses
    "three-dimensional",  # 400 docs, 635 uses
    "high-speed",  # 397 docs, 1065 uses
    "well-being",  # 391 docs, 641 uses
    "full-time",  # 385 docs, 524 uses
    "five-year",  # 384 docs, 560 uses
    "short-term",  # 380 docs, 540 uses
    "pre-existing",  # 365 docs, 507 uses
    "x-ray",  # 359 docs, 1166 uses
    "middle-class",  # 359 docs, 525 uses
    "well-established",  # 352 docs, 382 uses
    "long-standing",  # 351 docs, 380 uses
    "high-quality",  # 349 docs, 427 uses
    "north-west",  # 347 docs, 510 uses
    "south-east",  # 345 docs, 480 uses
    "co-operation",  # 337 docs, 576 uses
    "man-made",  # 334 docs, 439 uses
    "north-east",  # 328 docs, 454 uses
    "small-scale",  # 325 docs, 378 uses
    "non-fiction",  # 323 docs, 566 uses
    "state-owned",  # 323 docs, 507 uses
    "decision-making",  # 315 docs, 447 uses
    "year-round",  # 313 docs, 411 uses
    "commander-in-chief",  # 297 docs, 452 uses
    "non-profit",  # 295 docs, 387 uses
    "well-defined",  # 291 docs, 362 uses
    "left-wing",  # 287 docs, 505 uses
    "south-west",  # 285 docs, 400 uses
    "re-established",  # 282 docs, 330 uses
    "right-wing",  # 277 docs, 527 uses
    "high-ranking",  # 274 docs, 324 uses
    "city-states",  # 269 docs, 617 uses
    "three-quarters",  # 267 docs, 679 uses
    "well-developed",  # 267 docs, 321 uses
    "day-to-day",  # 266 docs, 296 uses
    "four-year",  # 255 docs, 348 uses
    "full-scale",  # 250 docs, 312 uses
    "avant-garde",  # 249 docs, 531 uses
    "working-class",  # 248 docs, 363 uses
    "two-year",  # 248 docs, 292 uses
    "common-law",  # 247 docs, 763 uses
    "medium-sized",  # 243 docs, 413 uses
    "three-year",  # 242 docs, 300 uses
    "far-reaching",  # 241 docs, 277 uses
    "nineteenth-century",  # 235 docs, 274 uses
    "mass-produced",  # 228 docs, 313 uses
    "best-selling",  # 227 docs, 502 uses
    "third-largest",  # 226 docs, 325 uses
    "re-elected",  # 225 docs, 311 uses
    "semi-arid",  # 223 docs, 289 uses
    "all-time",  # 222 docs, 380 uses
    "half-brother",  # 222 docs, 318 uses
    "award-winning",  # 222 docs, 268 uses
    "city-state",  # 221 docs, 350 uses
    "socio-economic",  # 221 docs, 281 uses
    "old-fashioned",  # 219 docs, 477 uses
    "high-level",  # 216 docs, 340 uses
    "long-time",  # 215 docs, 240 uses
    "jean-baptiste",  # 214 docs, 291 uses
    "wide-ranging",  # 214 docs, 243 uses
    "two-dimensional",  # 212 docs, 333 uses
    "full-length",  # 211 docs, 274 uses
    "high-profile",  # 210 docs, 242 uses
    "twentieth-century",  # 207 docs, 255 uses
    "north-western",  # 206 docs, 258 uses
    "non-existent",  # 205 docs, 239 uses
    "self-government",  # 203 docs, 333 uses
    "pre-war",  # 203 docs, 267 uses
    "latter-day",  # 202 docs, 300 uses
    "vice-president",  # 202 docs, 282 uses
    "part-time",  # 202 docs, 244 uses
    "long-lasting",  # 201 docs, 218 uses
    "cross-section",  # 200 docs, 287 uses
    "north-eastern",  # 197 docs, 236 uses
    "same-sex",  # 196 docs, 645 uses
    "south-eastern",  # 196 docs, 252 uses
    "low-cost",  # 195 docs, 245 uses
    "upper-class",  # 195 docs, 229 uses
    "long-lived",  # 190 docs, 246 uses
    "x-rays",  # 189 docs, 620 uses
    "self-determination",  # 187 docs, 399 uses
    "right-hand",  # 187 docs, 259 uses
    "low-lying",  # 184 docs, 229 uses
    "non-native",  # 180 docs, 296 uses
    "high-tech",  # 178 docs, 286 uses
    "high-energy",  # 177 docs, 295 uses
    "co-founded",  # 177 docs, 222 uses
    "anti-communist",  # 174 docs, 335 uses
    "co-founder",  # 173 docs, 241 uses
    "governor-general",  # 172 docs, 388 uses
    "non-governmental",  # 172 docs, 250 uses
    "long-range",  # 170 docs, 225 uses
    "real-time",  # 169 docs, 284 uses
    "follow-up",  # 169 docs, 190 uses
    "would-be",  # 169 docs, 190 uses
    "austria-hungary",  # 167 docs, 420 uses
    "self-sufficient",  # 167 docs, 210 uses
    "one-half",  # 166 docs, 2292 uses
    "hunter-gatherers",  # 166 docs, 308 uses
    "black-and-white",  # 166 docs, 266 uses
    "re-establish",  # 166 docs, 192 uses
    "half-life",  # 165 docs, 716 uses
    "built-in",  # 164 docs, 247 uses
    "real-world",  # 164 docs, 203 uses
    "open-air",  # 164 docs, 202 uses
    "third-party",  # 163 docs, 390 uses
    "by-product",  # 161 docs, 230 uses
    "real-life",  # 161 docs, 189 uses
    "time-consuming",  # 160 docs, 172 uses
    "self-governing",  # 159 docs, 237 uses
    "non-human",  # 158 docs, 265 uses
    "state-court",  # 155 docs, 464 uses
    "secretary-general",  # 155 docs, 277 uses
    "multi-party",  # 152 docs, 249 uses
    "state-run",  # 150 docs, 200 uses
    "self-contained",  # 150 docs, 179 uses
    "high-pressure",  # 148 docs, 245 uses
    "pre-eminent",  # 148 docs, 161 uses
    "low-level",  # 145 docs, 208 uses
    "non-religious",  # 145 docs, 193 uses
    "self-control",  # 144 docs, 274 uses
    "pre-modern",  # 144 docs, 180 uses
    "well-preserved",  # 144 docs, 162 uses
    "re-election",  # 143 docs, 228 uses
    "fastest-growing",  # 142 docs, 187 uses
    "purpose-built",  # 142 docs, 180 uses
    "self-defense",  # 141 docs, 247 uses
    "non-standard",  # 141 docs, 195 uses
    "low-income",  # 140 docs, 223 uses
    "second-highest",  # 139 docs, 174 uses
    "state-law",  # 136 docs, 330 uses
    "middle-aged",  # 135 docs, 232 uses
    "land-based",  # 135 docs, 164 uses
    "nation-state",  # 134 docs, 185 uses
    "left-hand",  # 134 docs, 175 uses
    "second-most",  # 134 docs, 156 uses
    "proto-germanic",  # 133 docs, 255 uses
    "non-zero",  # 133 docs, 219 uses
    "first-class",  # 131 docs, 271 uses
    "jean-paul",  # 131 docs, 211 uses
    "stand-alone",  # 131 docs, 161 uses
    "make-up",  # 130 docs, 185 uses
    "high-rise",  # 129 docs, 284 uses
    "self-interest",  # 129 docs, 172 uses
    "south-western",  # 129 docs, 165 uses
    "self-esteem",  # 128 docs, 405 uses
    "one-quarter",  # 127 docs, 412 uses
    "solid-state",  # 127 docs, 233 uses
    "fourth-largest",  # 127 docs, 168 uses
    "long-running",  # 127 docs, 156 uses
    "build-up",  # 127 docs, 144 uses
    "multi-ethnic",  # 126 docs, 153 uses
    "one-party",  # 125 docs, 239 uses
    "non-aligned",  # 124 docs, 198 uses
    "in-depth",  # 124 docs, 131 uses
    "non-muslims",  # 123 docs, 241 uses
    "mcgraw-hill",  # 123 docs, 153 uses
    "first-ever",  # 123 docs, 136 uses
    "water-soluble",  # 122 docs, 169 uses
    "non-western",  # 122 docs, 166 uses
    "south-central",  # 122 docs, 140 uses
    "high-end",  # 120 docs, 153 uses
    "hunter-gatherer",  # 119 docs, 213 uses
    "built-up",  # 119 docs, 171 uses
    "great-grandfather",  # 119 docs, 144 uses
    "half-hour",  # 118 docs, 218 uses
    "high-temperature",  # 118 docs, 191 uses
    "life-threatening",  # 118 docs, 129 uses
    "full-fledged",  # 118 docs, 128 uses
    "first-person",  # 117 docs, 178 uses
    "above-mentioned",  # 117 docs, 165 uses
    "north-central",  # 117 docs, 139 uses
    "anti-war",  # 116 docs, 214 uses
    "cost-effective",  # 116 docs, 133 uses
    "first-hand",  # 116 docs, 127 uses
    "eighteenth-century",  # 115 docs, 142 uses
    "ten-year",  # 115 docs, 132 uses
    "first-order",  # 114 docs, 247 uses
    "socio-political",  # 114 docs, 137 uses
    "one-way",  # 113 docs, 145 uses
    "singer-songwriter",  # 112 docs, 156 uses
    "high-resolution",  # 112 docs, 147 uses
    "horse-drawn",  # 111 docs, 175 uses
    "break-up",  # 111 docs, 140 uses
    "western-style",  # 111 docs, 135 uses
    "three-part",  # 111 docs, 128 uses
    "ever-increasing",  # 111 docs, 118 uses
    "one-to-one",  # 110 docs, 145 uses
    "long-established",  # 110 docs, 121 uses
    "jean-pierre",  # 108 docs, 150 uses
    "state-sponsored",  # 108 docs, 134 uses
    "one-time",  # 108 docs, 122 uses
    "self-proclaimed",  # 108 docs, 118 uses
    "self-confidence",  # 107 docs, 149 uses
    "three-day",  # 107 docs, 120 uses
    "self-evident",  # 106 docs, 179 uses
    "anti-semitism",  # 106 docs, 154 uses
    "one-year",  # 106 docs, 135 uses
    "self-sufficiency",  # 106 docs, 130 uses
    "open-ended",  # 106 docs, 124 uses
    "cross-cultural",  # 105 docs, 144 uses
    "case-by-case",  # 105 docs, 133 uses
    "two-part",  # 105 docs, 120 uses
    "fast-growing",  # 105 docs, 111 uses
    "far-right",  # 104 docs, 160 uses
    "well-to-do",  # 104 docs, 140 uses
    "one-sided",  # 103 docs, 121 uses
    "non-linear",  # 102 docs, 147 uses
    "hand-held",  # 102 docs, 136 uses
    "prize-winning",  # 102 docs, 118 uses
    "one-dimensional",  # 101 docs, 150 uses
    "on-line",  # 101 docs, 118 uses
    "great-grandson",  # 101 docs, 115 uses
    "anti-communists",  # 101 docs, 112 uses
    "well-documented",  # 101 docs, 112 uses
    "meta-analysis",  # 100 docs, 246 uses
    "box-office",  # 100 docs, 212 uses
    "feature-length",  # 100 docs, 142 uses
    "six-year",  # 100 docs, 125 uses
    "well-trained",  # 100 docs, 118 uses
    "high-density",  # 100 docs, 117 uses
    "six-month",  # 100 docs, 108 uses
    "left-handed",  # 99 docs, 189 uses
    "anti-government",  # 99 docs, 123 uses
    "light-years",  # 98 docs, 385 uses
    "hip-hop",  # 98 docs, 324 uses
    "beaux-arts",  # 98 docs, 168 uses
    "ill-fated",  # 98 docs, 110 uses
    "deep-sea",  # 97 docs, 169 uses
    "cross-border",  # 97 docs, 160 uses
    "two-way",  # 97 docs, 146 uses
    "second-hand",  # 97 docs, 135 uses
    "east-west",  # 97 docs, 129 uses
    "well-educated",  # 97 docs, 102 uses
    "half-lives",  # 96 docs, 216 uses
    "low-pressure",  # 96 docs, 169 uses
    "half-sister",  # 96 docs, 137 uses
    "general-purpose",  # 95 docs, 145 uses
    "top-level",  # 95 docs, 108 uses
    "centuries-old",  # 95 docs, 101 uses
    "half-way",  # 94 docs, 184 uses
    "six-day",  # 94 docs, 149 uses
    "high-frequency",  # 94 docs, 138 uses
    "government-owned",  # 94 docs, 121 uses
    "world-class",  # 94 docs, 104 uses
    "jean-fran",  # 93 docs, 131 uses
    "post-colonial",  # 93 docs, 113 uses
    "seven-year",  # 93 docs, 107 uses
    "non-violent",  # 92 docs, 133 uses
    "self-conscious",  # 92 docs, 130 uses
    "world-famous",  # 92 docs, 100 uses
    "subject-matter",  # 91 docs, 262 uses
    "highest-grossing",  # 91 docs, 232 uses
    "spin-off",  # 91 docs, 128 uses
    "high-altitude",  # 91 docs, 119 uses
    "co-authored",  # 91 docs, 118 uses
    "face-to-face",  # 91 docs, 118 uses
    "peer-reviewed",  # 91 docs, 111 uses
    "world-renowned",  # 91 docs, 101 uses
    "pre-colonial",  # 90 docs, 115 uses
    "post-independence",  # 90 docs, 112 uses
    "mid-to-late",  # 90 docs, 100 uses
    "north-south",  # 89 docs, 121 uses
    "by-products",  # 89 docs, 116 uses
    "slow-moving",  # 89 docs, 94 uses
    "half-past",  # 88 docs, 389 uses
    "sea-level",  # 88 docs, 160 uses
    "co-wrote",  # 88 docs, 126 uses
    "high-income",  # 88 docs, 124 uses
    "better-known",  # 88 docs, 91 uses
    "clear-cut",  # 88 docs, 91 uses
    "counter-reformation",  # 87 docs, 181 uses
    "re-entered",  # 87 docs, 156 uses
    "high-performance",  # 87 docs, 117 uses
    "right-handed",  # 86 docs, 180 uses
    "free-standing",  # 86 docs, 130 uses
    "on-site",  # 86 docs, 130 uses
    "co-written",  # 86 docs, 107 uses
    "three-month",  # 86 docs, 93 uses
    "good-natured",  # 85 docs, 307 uses
    "live-action",  # 85 docs, 189 uses
    "self-reliance",  # 85 docs, 109 uses
    "foreign-born",  # 84 docs, 125 uses
    "nation-states",  # 84 docs, 120 uses
    "cross-sectional",  # 84 docs, 118 uses
    "seventeenth-century",  # 84 docs, 99 uses
    "re-opened",  # 84 docs, 98 uses
    "labor-intensive",  # 84 docs, 95 uses
    "cross-country",  # 83 docs, 152 uses
    "self-awareness",  # 83 docs, 124 uses
    "second-class",  # 83 docs, 114 uses
    "record-breaking",  # 83 docs, 103 uses
    "two-volume",  # 83 docs, 91 uses
    "laissez-faire",  # 82 docs, 127 uses
    "in-house",  # 82 docs, 102 uses
    "good-bye",  # 81 docs, 585 uses
    "first-rate",  # 81 docs, 162 uses
    "red-hot",  # 81 docs, 162 uses
    "like-minded",  # 81 docs, 93 uses
    "year-long",  # 81 docs, 85 uses
    "self-portrait",  # 80 docs, 132 uses
    "self-consciousness",  # 80 docs, 130 uses
    "steam-powered",  # 80 docs, 122 uses
    "for-profit",  # 80 docs, 113 uses
    "pre-industrial",  # 80 docs, 98 uses
    "well-suited",  # 80 docs, 85 uses
    "neo-assyrian",  # 79 docs, 253 uses
    "looking-glass",  # 79 docs, 225 uses
    "cross-examination",  # 79 docs, 176 uses
    "non-white",  # 79 docs, 114 uses
    "socio-cultural",  # 79 docs, 104 uses
    "co-produced",  # 79 docs, 102 uses
    "fifth-largest",  # 79 docs, 102 uses
    "run-off",  # 79 docs, 102 uses
    "half-century",  # 79 docs, 87 uses
    "human-made",  # 78 docs, 100 uses
    "first-born",  # 78 docs, 98 uses
    "state-of-the-art",  # 78 docs, 80 uses
    "little-known",  # 78 docs, 78 uses
    "drawing-room",  # 77 docs, 841 uses
    "e-mail",  # 77 docs, 152 uses
    "science-fiction",  # 77 docs, 140 uses
    "three-way",  # 77 docs, 97 uses
    "higher-level",  # 77 docs, 92 uses
    "ground-based",  # 76 docs, 144 uses
    "runner-up",  # 76 docs, 128 uses
    "top-down",  # 76 docs, 114 uses
    "co-workers",  # 76 docs, 94 uses
    "semi-autonomous",  # 76 docs, 93 uses
    "fast-moving",  # 76 docs, 83 uses
    "sought-after",  # 76 docs, 79 uses
    "second-order",  # 75 docs, 143 uses
    "trade-off",  # 75 docs, 91 uses
    "co-author",  # 75 docs, 84 uses
    "life-size",  # 74 docs, 111 uses
    "up-to-date",  # 74 docs, 83 uses
    "non-traditional",  # 74 docs, 82 uses
    "dining-room",  # 73 docs, 474 uses
    "anti-aircraft",  # 73 docs, 197 uses
    "non-violence",  # 73 docs, 139 uses
    "higher-order",  # 73 docs, 122 uses
    "single-celled",  # 73 docs, 104 uses
    "one-day",  # 73 docs, 99 uses
    "all-powerful",  # 73 docs, 97 uses
    "multi-purpose",  # 73 docs, 94 uses
    "low-density",  # 73 docs, 91 uses
    "night-time",  # 73 docs, 88 uses
    "self-imposed",  # 73 docs, 76 uses
    "kai-shek",  # 72 docs, 234 uses
    "third-person",  # 72 docs, 147 uses
    "word-final",  # 72 docs, 133 uses
    "free-living",  # 72 docs, 127 uses
    "re-released",  # 72 docs, 114 uses
    "on-screen",  # 72 docs, 101 uses
    "mid-twentieth",  # 72 docs, 75 uses
    "two-day",  # 72 docs, 75 uses
    "first-degree",  # 71 docs, 160 uses
    "anti-colonial",  # 71 docs, 121 uses
    "able-bodied",  # 71 docs, 98 uses
    "high-school",  # 71 docs, 94 uses
    "co-operative",  # 71 docs, 89 uses
    "reddish-brown",  # 71 docs, 85 uses
    "non-military",  # 71 docs, 82 uses
    "ever-changing",  # 71 docs, 79 uses
    "highest-ranking",  # 71 docs, 74 uses
    "mid-ocean",  # 70 docs, 170 uses
    "editor-in-chief",  # 70 docs, 123 uses
    "u-shaped",  # 70 docs, 102 uses
    "high-pitched",  # 70 docs, 83 uses
    "open-source",  # 69 docs, 176 uses
    "far-off",  # 69 docs, 148 uses
    "ice-free",  # 69 docs, 119 uses
    "re-enter",  # 69 docs, 96 uses
    "deep-water",  # 69 docs, 94 uses
    "white-tailed",  # 69 docs, 91 uses
    "above-ground",  # 69 docs, 90 uses
    "re-establishment",  # 69 docs, 82 uses
    "three-volume",  # 69 docs, 82 uses
    "non-commercial",  # 69 docs, 80 uses
    "co-ordination",  # 69 docs, 79 uses
    "non-toxic",  # 69 docs, 78 uses
    "agreed-upon",  # 69 docs, 76 uses
    "then-current",  # 69 docs, 71 uses
    "good-looking",  # 68 docs, 150 uses
    "federal-court",  # 68 docs, 142 uses
    "co-star",  # 68 docs, 138 uses
    "anti-corruption",  # 68 docs, 111 uses
    "per-capita",  # 68 docs, 86 uses
    "one-man",  # 68 docs, 85 uses
    "all-female",  # 68 docs, 84 uses
    "cold-blooded",  # 68 docs, 84 uses
    "hard-working",  # 68 docs, 79 uses
    "well-received",  # 68 docs, 78 uses
    "all-out",  # 68 docs, 77 uses
    "mid-century",  # 68 docs, 75 uses
    "three-fourths",  # 67 docs, 151 uses
    "land-use",  # 67 docs, 131 uses
    "counter-revolutionary",  # 67 docs, 109 uses
    "full-size",  # 67 docs, 106 uses
    "cut-off",  # 67 docs, 87 uses
    "self-governance",  # 67 docs, 78 uses
    "co-existed",  # 67 docs, 77 uses
    "start-up",  # 67 docs, 77 uses
    "self-identify",  # 67 docs, 76 uses
    "semi-independent",  # 67 docs, 75 uses
    "third-most",  # 67 docs, 75 uses
    "blue-green",  # 66 docs, 96 uses
    "lower-class",  # 66 docs, 84 uses
    "co-operate",  # 66 docs, 82 uses
    "ill-health",  # 66 docs, 74 uses
    "all-encompassing",  # 66 docs, 71 uses
    "london-based",  # 66 docs, 71 uses
    "mid-september",  # 66 docs, 70 uses
    "mid-nineteenth",  # 66 docs, 68 uses
    "mixed-race",  # 65 docs, 108 uses
    "counter-attack",  # 65 docs, 95 uses
    "problem-solving",  # 65 docs, 95 uses
    "low-energy",  # 65 docs, 83 uses
    "self-sustaining",  # 65 docs, 78 uses
    "neo-classical",  # 65 docs, 70 uses
    "lesser-known",  # 65 docs, 68 uses
    "re-emerged",  # 65 docs, 66 uses
    "anti-slavery",  # 64 docs, 186 uses
    "non-negative",  # 64 docs, 125 uses
    "self-sacrifice",  # 64 docs, 102 uses
    "self-respect",  # 64 docs, 100 uses
    "counter-clockwise",  # 64 docs, 96 uses
    "one-act",  # 64 docs, 95 uses
    "co-official",  # 64 docs, 94 uses
    "run-up",  # 64 docs, 86 uses
    "major-general",  # 64 docs, 81 uses
    "longest-lived",  # 64 docs, 78 uses
    "new-found",  # 64 docs, 73 uses
    "government-sponsored",  # 64 docs, 69 uses
    "government-run",  # 64 docs, 68 uses
    "in-between",  # 64 docs, 68 uses
    "month-long",  # 64 docs, 67 uses
    "all-star",  # 63 docs, 202 uses
    "gamma-ray",  # 63 docs, 183 uses
    "evidence-based",  # 63 docs, 128 uses
    "full-grown",  # 63 docs, 126 uses
    "take-off",  # 63 docs, 114 uses
    "jean-luc",  # 63 docs, 103 uses
    "self-identified",  # 63 docs, 75 uses
    "re-establishing",  # 63 docs, 69 uses
    "full-blown",  # 63 docs, 68 uses
    "set-up",  # 63 docs, 68 uses
    "well-studied",  # 63 docs, 67 uses
    "then-president",  # 63 docs, 66 uses
    "cd-rom",  # 62 docs, 112 uses
    "self-rule",  # 62 docs, 109 uses
    "self-help",  # 62 docs, 87 uses
    "re-release",  # 62 docs, 85 uses
    "light-hearted",  # 62 docs, 74 uses
    "non-denominational",  # 62 docs, 74 uses
    "self-taught",  # 62 docs, 71 uses
    "non-stop",  # 62 docs, 70 uses
    "co-starred",  # 61 docs, 118 uses
    "micro-organisms",  # 61 docs, 106 uses
    "inner-city",  # 61 docs, 104 uses
    "egg-laying",  # 61 docs, 97 uses
    "fine-grained",  # 61 docs, 90 uses
    "world-wide",  # 61 docs, 83 uses
    "anti-fascist",  # 61 docs, 81 uses
    "prentice-hall",  # 61 docs, 68 uses
    "number-one",  # 60 docs, 246 uses
    "al-malik",  # 60 docs, 194 uses
    "role-playing",  # 60 docs, 170 uses
    "self-propelled",  # 60 docs, 131 uses
    "cease-fire",  # 60 docs, 107 uses
    "low-frequency",  # 60 docs, 95 uses
    "computer-generated",  # 60 docs, 94 uses
    "light-emitting",  # 60 docs, 94 uses
    "post-secondary",  # 60 docs, 83 uses
    "worn-out",  # 60 docs, 81 uses
    "water-based",  # 60 docs, 79 uses
    "ready-made",  # 60 docs, 76 uses
    "pre-eminence",  # 60 docs, 75 uses
    "colonial-era",  # 60 docs, 71 uses
    "free-market",  # 59 docs, 92 uses
    "hand-to-hand",  # 59 docs, 79 uses
    "west-central",  # 59 docs, 73 uses
    "first-generation",  # 59 docs, 70 uses
    "multi-national",  # 59 docs, 64 uses
    "now-extinct",  # 59 docs, 61 uses
    "third-highest",  # 59 docs, 61 uses
    "week-long",  # 59 docs, 61 uses
    "second-degree",  # 58 docs, 119 uses
    "post-classical",  # 58 docs, 113 uses
)


if __name__ == "__main__":
    raise SystemExit(run_import(WORDS, DIFFICULTY_LEVEL, __doc__ or ""))
