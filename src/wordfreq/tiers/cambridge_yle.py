"""Cambridge Young Learners English (YLE) tier importer.

Source file shape (data/cambridge/yle_wordlist.json):

    {
      "source": "...",
      "entries": [
        {"word": "animal", "pos": ["n"], "level": "starters",
         "variants": {"UK": null, "US": null}, "sense": null,
         "themes": ["Animals"]},
        ...
      ]
    }

Per-entry behavior:
- Words containing ``/`` are split into multiple TierEntry rows (e.g.
  ``Ann/Anna`` -> ``Ann``, ``Anna``), each carrying the same metadata.
- A row with multiple POS values produces one TierEntry per POS.
- Resolution returns every Lemma whose ``lemma_text`` matches and whose
  ``pos_type`` is compatible with the YLE pos shorthand. The runner attaches
  a tier annotation and a LemmaTier row to each candidate (handles homographs
  like ``fish`` (animal) and ``fish`` (meat) without human disambiguation).
- A ``sense`` hint, when present and matching exactly one Lemma's
  ``disambiguation``, narrows the candidate set to that one Lemma.
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

SOURCE: str = "cambridge_yle"
DEFAULT_PATH: str = os.path.join(constants.PROJECT_ROOT, "data", "cambridge", "yle_wordlist.json")

# YLE pos shorthand -> set of acceptable Lemma.pos_type values.
YLE_POS_TO_LEMMA_POS: dict[str, tuple[str, ...]] = {
    "n": ("noun",),
    "v": ("verb",),
    "adj": ("adjective",),
    "adv": ("adverb",),
    "prep": ("preposition",),
    "pron": ("pronoun",),
    "conj": ("conjunction",),
    "det": ("determiner", "article"),
    "int": ("interjection",),
    "excl": ("interjection",),
    "poss": ("determiner", "pronoun"),
    "title": ("noun",),
    "dis": ("determiner", "pronoun"),
}


@dataclass
class CambridgeYleImporter:
    """TierImporter for Cambridge YLE wordlists."""

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
            pos_list = row.get("pos") or [None]
            themes = tuple(row.get("themes") or ())
            sense = row.get("sense")
            for surface in _split_surface_forms(word):
                for pos in pos_list:
                    entries.append(
                        TierEntry(
                            word=surface,
                            language_code=self.language_code,
                            pos_hint=pos,
                            tier_name=level,
                            sense_hint=sense,
                            themes=themes,
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
        if not filtered:
            return []

        if entry.sense_hint:
            sense_matches = [c for c in filtered if (c.disambiguation or "") == entry.sense_hint]
            if len(sense_matches) == 1:
                return [sense_matches[0].id]
        return [c.id for c in filtered]


def _split_surface_forms(word: str) -> List[str]:
    """Split YLE-style slash-separated surface forms (e.g. ``Ann/Anna``).

    Strips whitespace around each part. Returns ``[word]`` if no slash present.
    Empty parts are dropped.
    """
    if "/" not in word:
        return [word]
    parts = [p.strip() for p in word.split("/")]
    return [p for p in parts if p]


def _accepted_lemma_pos_types(pos_hint: Optional[str]) -> Optional[set[str]]:
    """Return the set of Lemma.pos_type values that match this YLE pos shorthand.

    Returns None for unknown shorthand (skip pos filtering and let lemma_text alone decide).
    """
    if pos_hint is None:
        return None
    mapped = YLE_POS_TO_LEMMA_POS.get(pos_hint)
    if mapped is None:
        return None
    return set(mapped)
