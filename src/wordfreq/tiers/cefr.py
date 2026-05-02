"""CEFR tier importer.

Source file shape (data/cefr/cefr_wordlist.json):

    {
      "source": "cefr",
      "entries": [
        {"word": "abandon", "pos": "verb", "level": "B1"},
        {"word": "a", "pos": "determiner", "level": "A1"},
        ...
      ]
    }

Each entry maps to one TierEntry. POS strings come from the upstream
Open Language Profiles CSVs and are full words (``noun``, ``verb``,
``adjective``, ...) — they map directly to ``Lemma.pos_type``, with a
small mapping for verb-family aliases (``be-verb``, ``modal auxiliary``,
etc.) that the database stores as plain ``verb``.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import List, Optional

from sqlalchemy.orm import Session

import constants
from storage.models.schema import Lemma
from wordfreq.tiers.base import TierEntry, TierImporter

logger = logging.getLogger(__name__)

SOURCE: str = "cefr"
DEFAULT_PATH: str = os.path.join(constants.PROJECT_ROOT, "data", "cefr", "cefr_wordlist.json")

# CEFR POS string -> set of acceptable Lemma.pos_type values.
# All verb-family auxiliaries fold into "verb"; "vern" is an upstream typo
# for "verb"; "infinitive-to" carries no useful POS signal so we drop the
# filter for it (lemma_text alone decides).
CEFR_POS_TO_LEMMA_POS: dict[str, tuple[str, ...]] = {
    "noun": ("noun",),
    "verb": ("verb",),
    "vern": ("verb",),
    "be-verb": ("verb",),
    "do-verb": ("verb",),
    "have-verb": ("verb",),
    "modal auxiliary": ("verb",),
    "adjective": ("adjective",),
    "adverb": ("adverb",),
    "preposition": ("preposition",),
    "pronoun": ("pronoun",),
    "conjunction": ("conjunction",),
    "determiner": ("determiner", "article"),
    "interjection": ("interjection",),
    "number": ("numeral",),
}


@dataclass
class CefrImporter:
    """TierImporter for the merged CEFR-J + Octanove wordlist."""

    file_path: str = DEFAULT_PATH
    language_code: str = "en"
    source: str = SOURCE

    def load_entries(self) -> List[TierEntry]:
        with open(self.file_path, "r", encoding="utf-8") as fh:
            payload = json.load(fh)
        entries: List[TierEntry] = []
        for row in payload.get("entries", []):
            word = row.get("word")
            level = row.get("level")
            if not word or not level:
                continue
            pos_hint = row.get("pos") or None
            entries.append(
                TierEntry(
                    word=word,
                    language_code=self.language_code,
                    pos_hint=pos_hint,
                    tier_name=level,
                    sense_hint=None,
                    themes=(),
                    raw=row,
                )
            )
        return entries

    def resolve(self, session: Session, entry: TierEntry) -> List[int]:
        candidates = session.query(Lemma).filter(Lemma.lemma_text == entry.word).all()
        if not candidates:
            return []
        accepted_pos = _accepted_lemma_pos_types(entry.pos_hint)
        if accepted_pos is not None:
            filtered = [c for c in candidates if c.pos_type in accepted_pos]
        else:
            filtered = candidates
        return [c.id for c in filtered]


def _accepted_lemma_pos_types(pos_hint: Optional[str]) -> Optional[set[str]]:
    """Return acceptable Lemma.pos_type values for a CEFR POS string.

    Returns None when the CEFR POS carries no useful filter signal
    (unknown value or ``infinitive-to``); callers then skip POS filtering.
    """
    if pos_hint is None:
        return None
    mapped = CEFR_POS_TO_LEMMA_POS.get(pos_hint)
    if mapped is None:
        return None
    return set(mapped)
