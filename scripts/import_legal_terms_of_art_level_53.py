#!/usr/bin/env python3
"""Import the legal terms of art -- the multi-word phrases of the law.

Levels 42 and 50 took single words from the legal_scotus corpus, by Zipf skew
and by corpus exclusivity respectively.  Both miss the vocabulary that carries
the most legal meaning per token, because a frequency list over whitespace
tokens cannot see it: "ex post facto" is three ordinary words, "voir dire" is
two words that are not English at all, and "res ipsa loquitur" is Latin whose
parts mean nothing to a reader who does not already know the doctrine.  This
list is assembled from the standard terminology rather than mined from a corpus.

Most entries are Latin or Law French; the rest are English phrases fixed enough
that their meaning is not the sum of their parts ("fruit of the poisonous tree",
"void for vagueness").

These are wanted primarily for **tokenizing**: the point is that the database
knows "habeas corpus" is one lexical unit rather than two words, so a sentence
containing it segments correctly.  Translation is secondary and may not be
possible for every entry -- many legal systems have no equivalent doctrine, and
several of these terms are borrowed untranslated into other languages exactly as
they are into English.  An entry the server records as a lexical gap is a
correct outcome here, not a failure of the import.

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

DIFFICULTY_LEVEL = 53

# Standard legal terminology, not a corpus extract.  Checked against
# ``words_exist`` and against the word lists of levels 34-52, which is what
# removed the bare forms already claimed there ("certiorari", "indictment" and
# "tolling" belong to level 50, so they appear here only inside a longer phrase
# such as "equitable tolling").  "information" and "standing" are omitted
# entirely: both are already in the database in their ordinary senses, and the
# legal sense of each is a disambiguation of that lemma rather than a new one.
#
# Trimmed of terms that are either dictionary curiosities rather than working
# vocabulary ("profit a prendre", "autrefois acquit") or transparent enough that
# a tokenizer gains nothing from holding them together ("burden of proof").
WORDS: Sequence[str] = (
    "ex post facto",
    "habeas corpus",
    "amicus curiae",
    "per curiam",
    "stare decisis",
    "res judicata",
    "prima facie",
    "de facto",
    "de jure",
    "de novo",
    "in re",
    "ex parte",
    "mens rea",
    "actus reus",
    "nolo contendere",
    "in forma pauperis",
    "pro se",
    "pro bono",
    "pro hac vice",
    "in camera",
    "in limine",
    "inter alia",
    "sui generis",
    "ultra vires",
    "obiter dictum",
    "ratio decidendi",
    "nunc pro tunc",
    "ab initio",
    "bona fide",
    "caveat emptor",
    "quid pro quo",
    "res ipsa loquitur",
    "respondeat superior",
    "quantum meruit",
    "malum in se",
    "malum prohibitum",
    "corpus delicti",
    "nolle prosequi",
    "in personam",
    "in rem",
    "forum non conveniens",
    "lis pendens",
    "per stirpes",
    "per capita",
    "ad litem",
    "guardian ad litem",
    "subpoena duces tecum",
    "voir dire",
    "mandamus",
    "quo warranto",
    "laches",
    "estoppel",
    "tort",
    "escheat",
    "servitude",
    "easement",
    "covenant",
    "intestate",
    "testator",
    "executor",
    "remainderman",
    "arraignment",
    "subpoena",
    "mootness",
    "ripeness",
    "promissory estoppel",
    "collateral estoppel",
    "unjust enrichment",
    "fee simple",
    "life estate",
    "tenancy in common",
    "joint tenancy",
    "adverse possession",
    "eminent domain",
    "double jeopardy",
    "due process",
    "equal protection",
    "strict scrutiny",
    "substantive due process",
    "void for vagueness",
    "fruit of the poisonous tree",
    "exclusionary rule",
    "probable cause",
    "reasonable suspicion",
    "beyond a reasonable doubt",
    "preponderance of the evidence",
    "clear and convincing evidence",
    "prima facie case",
    "summary judgment",
    "directed verdict",
    "judgment notwithstanding the verdict",
    "class action",
    "political question",
    "sovereign immunity",
    "qualified immunity",
    "felony murder",
    "plea bargain",
    "statute of limitations",
    "equitable tolling",
)


if __name__ == "__main__":
    raise SystemExit(run_import(WORDS, DIFFICULTY_LEVEL, __doc__ or ""))
