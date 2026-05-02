"""Basic English tier importer.

Source file shape (data/basic_english/basic_english.json):

    {
      "source": "basic_english",
      "entries": [
        {"word": "a", "disambiguation": "Determiner", "level": "basic"},
        {"word": "account", "level": "basic"},
        {"word": "backbone", "level": "extended"},
        ...
      ]
    }

Two tiers: ``basic`` (Ogden's core 850) and ``extended`` (compound /
international / addendum / endings). The source has no POS information,
so resolution falls back to plain lemma_text matching across all POS.
The ``disambiguation`` field, when present, is passed as ``sense_hint``
and used to narrow homographs the same way YLE's ``sense`` does.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import List

from sqlalchemy.orm import Session

import constants
from storage.models.schema import Lemma
from wordfreq.tiers.base import TierEntry, TierImporter

logger = logging.getLogger(__name__)

SOURCE: str = "basic_english"
DEFAULT_PATH: str = os.path.join(
    constants.PROJECT_ROOT, "data", "basic_english", "basic_english.json"
)


@dataclass
class BasicEnglishImporter:
    """TierImporter for the Basic English wordlist."""

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
            sense = row.get("disambiguation") or None
            entries.append(
                TierEntry(
                    word=word,
                    language_code=self.language_code,
                    pos_hint=None,
                    tier_name=level,
                    sense_hint=sense,
                    themes=(),
                    raw=row,
                )
            )
        return entries

    def resolve(self, session: Session, entry: TierEntry) -> List[int]:
        candidates = session.query(Lemma).filter(Lemma.lemma_text == entry.word).all()
        if not candidates:
            return []
        if entry.sense_hint:
            sense_matches = [c for c in candidates if (c.disambiguation or "") == entry.sense_hint]
            if len(sense_matches) == 1:
                return [sense_matches[0].id]
        return [c.id for c in candidates]
