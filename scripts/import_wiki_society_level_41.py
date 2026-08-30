#!/usr/bin/env python3
"""Import the society vocabulary that leans toward the wiki_society corpus.

Sourced from /word-tokens/corpus-skew?corpus=wiki_society -- the words whose Zipf
here is furthest above their Zipf in the other corpora, which is what surfaces
society, philosophy and religion -- law, politics, economics, language, ethics and belief rather than the function words a raw frequency list would return.

Level 41 places this with the other corpus-skew batches (35-41, one per
Wikipedia corpus except wiki_math): specialised vocabulary a learner meets well
after the core.  These lists are disjoint; see the note on the word list below.

The language and linguistics terms this list originally carried moved to
import_linguistics_basic_level_18.py and import_linguistics_advanced_level_55.py.
The corpus put them here because encyclopedic prose about language sits inside
the Level 4 Society list, which is a fact about the corpus rather than about
the words: "noun" and "vowel" are the app's own metalanguage and belong early,
and "phoneme" and "orthography" belong with the rest of the technical tail.

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

DIFFICULTY_LEVEL = 41

# The top 200 rows of /word-tokens/corpus-skew?corpus=wiki_society on 2026-08-29,
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
# import_unlinked_level_34.py are removed here for the same reason.
WORDS: Sequence[str] = (
    "curriculum",
    "ethics",
    "cognitive",
    "theology",
    "university",
    "ethical",
    "deity",
    "adherents",
    "tradition",
    "texts",
    "legal",
    "ritual",
    "communion",
    "skepticism",
    "psychology",
    "suffrage",
    "verbal",
    "comparative",
    "academic",
    "peoples",
    "argued",
    "bullying",
    "psychological",
    "myth",
    "rights",
    "slang",
    "worship",
    "liberal",
    "goods",
    "divine",
    "philosophical",
    "organize",
    "reality",
    "democratic",
    "masculine",
    "subordinate",
    "theft",
    "philosopher",
    "ideology",
    "policy",
    "currency",
    "relics",
    "terrorism",
    "forensic",
    "doctrine",
    "insight",
    "posited",
    "spiritual",
    "moral",
    "goddess",
    "management",
    "inclusive",
    "based",
    "personality",
    "cultural",
    "mental",
    "managing",
    "prevalence",
    "peer",
    "supernatural",
    "conservative",
    "argue",
    "contrasted",
    "divinity",
    "official",
    "associated",
    "security",
    "concept",
    "welfare",
    "undergraduate",
    "status",
    "creation",
    "mythology",
    "fasting",
    "ethnicity",
    "stimulus",
)


if __name__ == "__main__":
    raise SystemExit(run_import(WORDS, DIFFICULTY_LEVEL, __doc__ or ""))
