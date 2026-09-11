#!/usr/bin/env python3
"""Import the history vocabulary that leans toward the wiki_history corpus.

Sourced from /word-tokens/corpus-skew?corpus=wiki_history -- the words whose Zipf
here is furthest above their Zipf in the other corpora, which is what surfaces
the connective prose of historical narrative -- reigns, campaigns, successions and revolts rather than the function words a raw frequency list would return.

The first 40 ranked words form the history sample at general-curriculum level
69. The remaining, sharper domain vocabulary is stored at topic level 104.

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

from scripts.wordlist_import_helper import run_domain_import

DIFFICULTY_LEVEL = 69
TOPIC_DIFFICULTY_LEVEL = 104

# The top 200 rows of /word-tokens/corpus-skew?corpus=wiki_history on 2026-08-29,
# reduced to what words_exist does not already account for, then curated:
# capitalized tokens are dropped (proper-noun residue the skew score cannot
# separate -- River, Empire, Shakespeare), along with possessives and
# participles whose headword is already in the list.  Plurals are dropped
# whenever the singular is an attested word at all, not merely when the
# singular also appears in this list -- the earlier, narrower rule left ~120
# plurals behind.  A few -s words that are their own lemma are kept (blues,
# goods, ethics, memoirs, archives, arts, texts, rights, peoples, relics), tokenization and markup
# fragments (sup, fa, et, al, de, non), and URL debris still in the database
# from the pre-fix corpus load (com, web).
#
# A word that scores in more than one corpus is assigned to whichever corpus it
# leans toward hardest, so these lists are disjoint and a word cannot be
# imported twice at two different levels.  Words already claimed by
# import_unlinked_level_65.py are removed here for the same reason.
WORDS: Sequence[str] = (
    "career",
    "invaded",
    "film",
    "alliance",
    "reign",
    "ally",
    "emperor",
    "lifelong",
    "rebellion",
    "defeat",
    "captured",
    "decisive",
    "commander",
    "tribute",
    "nobility",
    "throne",
    "campaign",
    "tour",
    "clan",
    "eventual",
    "victory",
    "attacked",
    "imprisoned",
    "leader",
    "revolt",
    "born",
    "heir",
    "leadership",
    "descent",
    "title",
    "conquered",
    "ruled",
    "weakened",
    "siege",
    "resigned",
    "royal",
    "defended",
    "nomination",
    "eventually",
    "conquest",
    "appointed",
    "successor",
    "allegiance",
    "expedition",
    "reform",
    "refused",
    "ruler",
    "succeeded",
    "opposition",
    "executed",
    "invasion",
    "claimed",
    "kingdom",
    "senior",
    "imperial",
    "legacy",
    "exile",
    "aristocracy",
    "shortly",
    "supported",
    "forced",
    "honored",
    "crowned",
    "assistant",
    "included",
    "conference",
    "graduated",
    "lifetime",
    "spent",
    "surrender",
    "session",
    "loyalty",
    "ambitious",
    "rival",
    "reputation",
)

GENERAL_WORDS: Sequence[str] = (
    "invaded",
    "alliance",
    "reign",
    "ally",
    "emperor",
    "rebellion",
    "defeat",
    "captured",
    "decisive",
    "commander",
    "tribute",
    "nobility",
    "throne",
    "campaign",
    "clan",
    "victory",
    "attacked",
    "imprisoned",
    "leader",
    "revolt",
    "heir",
    "leadership",
    "descent",
    "conquered",
    "ruled",
    "siege",
    "royal",
    "defended",
    "conquest",
    "appointed",
    "successor",
    "expedition",
    "reform",
    "ruler",
    "invasion",
    "kingdom",
    "imperial",
    "legacy",
    "exile",
    "surrender",
)


if __name__ == "__main__":
    raise SystemExit(
        run_domain_import(
            WORDS,
            GENERAL_WORDS,
            DIFFICULTY_LEVEL,
            TOPIC_DIFFICULTY_LEVEL,
            __doc__ or "",
        )
    )
