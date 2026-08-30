#!/usr/bin/env python3
"""Import a curated batch of common unlinked English words through Barsukas.

This script deliberately uses the public ``ROOT/api`` facade.  In particular,
``api.lemmas.add_word`` runs Barsukas' intelligent word workflow: the server's
LLM identifies the senses and supplies their translations, then the server
selects and stores the useful senses.  The script never supplies definitions or
translations itself.

Running without ``--execute`` only prints the plan and makes no HTTP requests.
The live mode first calls the read-only bulk existence endpoint, then imports
each still-unlinked word and moves every newly created sense to level 34.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Sequence

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.wordlist_import_helper import run_import

DIFFICULTY_LEVEL = 34

# Curated in displayed rank order from the first 200 rows of
# /word-tokens/unlinked on 2026-08-28.  This keeps dictionary headwords and
# removes obvious inflections/plurals (done, members, contains), proper-name
# capitalization (North, River, University), foreign-name particles (de), URL
# debris (http, www, https, org, com), and prefix/tokenization fragments
# (non, sub, re).  Invariant or independently lexicalized forms such as
# "series", "further", and "towards" are intentionally retained.
WORDS: Sequence[str] = (
    "within",
    "various",
    "whole",
    "generally",
    "further",
    "modern",
    "include",
    "per",
    "method",
    "individual",
    "particularly",
    "social",
    "region",
    "throughout",
    "production",
    "local",
    "popular",
    "series",
    "gas",
    "original",
    "former",
    "variety",
    "provide",
    "standard",
    "function",
    "commonly",
    "difference",
    "total",
    "analysis",
    "instance",
    "require",
    "available",
    "direct",
    "highly",
    "average",
    "central",
    "sufficient",
    "religious",
    "text",
    "influence",
    "distinct",
    "appearance",
    "product",
    "character",
    "hundred",
    "double",
    "contain",
    "national",
    "claim",
    "basis",
    "prevent",
    "construction",
    "majority",
    "center",
    "independent",
    "activity",
    "web",
    "approach",
    "specific",
    "recent",
    "upper",
    "section",
    "cost",
    "typically",
    "closely",
    "frequently",
    "content",
    "widely",
    "traditional",
    "thousand",
    "research",
    "numerous",
    "portion",
    "scientific",
    "application",
    "origin",
    "unless",
    "expression",
    "ordinary",
    "remove",
    "height",
    "image",
    "economic",
    "primary",
    "additional",
    "issue",
    "hence",
    "element",
    "constant",
    "principle",
    "flow",
    "supply",
    "commercial",
    "mostly",
    "positive",
    "lack",
    "member",
    "culture",
    "pure",
    "community",
    "extent",
    "personal",
    "useful",
    "northern",
    "foreign",
    "role",
    "treatment",
)


if __name__ == "__main__":
    raise SystemExit(run_import(WORDS, DIFFICULTY_LEVEL, __doc__ or ""))
