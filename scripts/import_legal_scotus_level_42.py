#!/usr/bin/env python3
"""Import the legal vocabulary that leans toward the legal_scotus corpus.

Sourced from /word-tokens/corpus-skew?corpus=legal_scotus -- the words whose Zipf
here is furthest above their Zipf in the other corpora, which is what surfaces
the vocabulary of courts and statutes -- procedure, evidence, remedies, rights and
regulation rather than the function words a raw frequency list would return.

Level 42 continues the corpus-skew batches (35-41 are one per Wikipedia corpus
except wiki_math) with the one non-Wikipedia corpus whose vocabulary is a
coherent domain rather than a period style: specialised vocabulary a learner
meets well after the core.  These lists are disjoint; see the note on the word
list below.

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

DIFFICULTY_LEVEL = 42

# The top 400 rows of /word-tokens/corpus-skew?corpus=legal_scotus on 2026-08-29,
# reduced to what words_exist does not already account for, then curated:
# capitalized tokens are dropped (Court, State, Justice -- the skew score cannot
# separate the institution from the common noun), along with possessives and the
# inflected forms whose headword is already in the list ("appeals" beside
# "appeal", "concluded" and "concluding" beside "conclude"), and the words whose
# skew is a matter of judicial *style* rather than legal meaning -- "our",
# "moreover", "accordingly", "ordinarily", "substantially".
#
# A word that scores in more than one corpus is assigned to whichever corpus it
# leans toward hardest, so these lists are disjoint and a word cannot be
# imported twice at two different levels.  Words already claimed by
# import_unlinked_level_34.py and by the 35-41 batches are removed here for the
# same reason.
WORDS: Sequence[str] = (
    "discretion",
    "statute",
    "provision",
    "jury",
    "petition",
    "presumption",
    "deference",
    "reasonable",
    "complaint",
    "employer",
    "verdict",
    "trial",
    "federal",
    "judgment",
    "agency",
    "statutory",
    "plea",
    "comply",
    "impose",
    "scrutiny",
    "defendant",
    "fee",
    "criminal",
    "counsel",
    "eligible",
    "attorney",
    "unreasonable",
    "offense",
    "warrant",
    "remedy",
    "disclosure",
    "affirmative",
    "alien",
    "penalty",
    "conclude",
    "compensation",
    "compel",
    "constitutional",
    "testimony",
    "dismiss",
    "legitimate",
    "alleged",
    "determination",
    "expenditure",
    "appeal",
    "reliance",
    "relief",
    "requirement",
    "conviction",
    "prohibition",
    "violation",
    "jurisdiction",
    "accommodation",
    "denial",
    "prosecutor",
    "injunction",
    "paragraph",
    "prosecution",
    "inadequate",
    "invalid",
    "regulation",
    "interpretation",
    "sanction",
    "imprisonment",
    "privilege",
    "proceeding",
    "suppression",
    "plaintiff",
    "judicial",
    "liability",
    "confinement",
    "burden",
    "writ",
    "obligation",
    "amendment",
    "unfair",
    "deprive",
    "discrimination",
    "instruction",
    "employment",
    "enforcement",
    "enacted",
    "scheme",
    "citizen",
    "justify",
    "exhaustion",
    "entitled",
    "grievance",
    "adequate",
    "failure",
    "defense",
    "unlawful",
    "ballot",
    "assertion",
    "commerce",
    "plausible",
    "breach",
    "indication",
    "disregard",
    "license",
    "lease",
    "contract",
    "regulatory",
    "patent",
    "employee",
    "justification",
    "peremptory",
    "prejudice",
    "assert",
    "abuse",
    "intrusion",
    "sovereign",
    "preliminary",
    "liable",
    "contention",
    "proposition",
    "dispute",
    "lawful",
    "admission",
    "removal",
    "enforce",
    "privacy",
    "applicable",
    "arrest",
    "ordinance",
    "termination",
    "refusal",
    "protection",
    "reasoning",
    "legislative",
    "suppress",
    "recommendation",
    "officer",
    "pleading",
    "precedent",
    "guilty",
    "discharge",
    "consent",
)


if __name__ == "__main__":
    raise SystemExit(run_import(WORDS, DIFFICULTY_LEVEL, __doc__ or ""))
