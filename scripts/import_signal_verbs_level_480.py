#!/usr/bin/env python3
"""Import signal verbs: the verbs used to introduce and characterize a quote.

The list is 111 signal verbs in their English base forms.  The script keeps the
73 that the dictionary did not account for on 2026-09-24.  Coverage used
the same form-aware check as the add endpoint: lemmas, disambiguated lemmas,
English derivative forms, alternate spellings, and exclusions all count.

Level 480 is the next open general-vocabulary slot after the existing 320-470
import sequence.  It is intentionally a holding level for the complete gap;
individual high-value verbs can be promoted after review without delaying the
rest of the list.

This script deliberately uses the public ``ROOT/api`` facade.  In particular,
``api.lemmas.add_word`` runs Barsukas' intelligent word workflow: the server's
LLM identifies all useful senses and supplies their translations, then the
server selects and stores the surviving lemmas.  The script does not restrict
the result to verb senses merely because these are listed as signal verbs.

The shared importer repeats the existence check and also skips words already
awaiting review in the pending-import queue.  That makes this snapshot safe to
run after other wordlists have added or queued overlapping words.

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

DIFFICULTY_LEVEL = 480

# Signal verbs excluded from the import because the dictionary's form-aware
# coverage check already accounts for them.  They stay here so the full list
# remains complete and auditable.
ALREADY_PRESENT_WORDS: Sequence[str] = (
    "add",
    "announce",
    "answer",
    "argue",
    "ask",
    "assert",
    "believe",
    "charge",
    "compare",
    "consider",
    "continue",
    "deny",
    "describe",
    "develop",
    "discuss",
    "dispute",
    "feel",
    "guide",
    "list",
    "mention",
    "note",
    "notice",
    "observe",
    "offer",
    "persist",
    "reason",
    "reply",
    "see",
    "share",
    "show",
    "stress",
    "suggest",
    "support",
    "tell",
    "test",
    "view",
    "want",
    "warn",
)

WORDS: Sequence[str] = (
    "acknowledge",
    "advise",
    "analyze",
    "assume",
    "categorize",
    "caution",
    "challenge",
    "claim",
    "clarify",
    "comment",
    "concede",
    "conclude",
    "condemn",
    "confirm",
    "confront",
    "contend",
    "contradict",
    "convince",
    "criticize",
    "declare",
    "defend",
    "define",
    "defy",
    "demand",
    "demonstrate",
    "determine",
    "disagree",
    "emphasize",
    "evaluate",
    "exaggerate",
    "express",
    "grant",
    "highlight",
    "hint",
    "identify",
    "illuminate",
    "illustrate",
    "imply",
    "indicate",
    "infer",
    "inquire",
    "insinuate",
    "insist",
    "interpret",
    "maintain",
    "object",
    "oppose",
    "outline",
    "perceive",
    "persuade",
    "portray",
    "praise",
    "proclaim",
    "propose",
    "protect",
    "prove",
    "recommend",
    "regard",
    "reject",
    "relate",
    "remark",
    "remind",
    "resolve",
    "respond",
    "restate",
    "retort",
    "reveal",
    "specify",
    "summarize",
    "synthesize",
    "uncover",
    "urge",
    "verify",
)


if __name__ == "__main__":
    raise SystemExit(run_import(WORDS, DIFFICULTY_LEVEL, __doc__ or ""))
