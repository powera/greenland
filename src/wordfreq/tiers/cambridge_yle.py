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

Resolution: match each entry to an English Lemma whose ``lemma_text`` equals
the YLE word and whose ``pos_type`` is compatible with the YLE pos shorthand.
If exactly one Lemma matches, attach. If multiple match, mark ambiguous (the
runner queues these for human review).
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
from wordfreq.tiers.base import ResolveResult, TierEntry, TierImporter

logger = logging.getLogger(__name__)

SOURCE: str = "cambridge_yle"
DEFAULT_PATH: str = os.path.join(constants.PROJECT_ROOT, "data", "cambridge", "yle_wordlist.json")

# YLE pos shorthand -> set of acceptable Lemma.pos_type values.
# A YLE entry matches a Lemma if any of the mapped pos_types equals the lemma's pos_type.
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
            for pos in pos_list:
                entries.append(
                    TierEntry(
                        word=word,
                        language_code=self.language_code,
                        pos_hint=pos,
                        tier_name=level,
                        sense_hint=sense,
                        themes=themes,
                        raw=row,
                    )
                )
        return entries

    def resolve(self, session: Session, entry: TierEntry) -> ResolveResult:
        candidates = session.query(Lemma).filter(Lemma.lemma_text == entry.word).all()
        if not candidates:
            return ResolveResult.unmatched(reason="no lemma with matching lemma_text")

        accepted_pos = _accepted_lemma_pos_types(entry.pos_hint)
        if accepted_pos is not None:
            filtered = [c for c in candidates if c.pos_type in accepted_pos]
        else:
            filtered = candidates

        if not filtered:
            return ResolveResult.unmatched(
                reason=f"no lemma with pos_type in {sorted(accepted_pos or set())}"
            )

        # If a sense hint is present and exactly one candidate's disambiguation matches, prefer it.
        if entry.sense_hint:
            sense_matches = [c for c in filtered if (c.disambiguation or "") == entry.sense_hint]
            if len(sense_matches) == 1:
                return ResolveResult.matched(sense_matches[0].id)

        if len(filtered) == 1:
            return ResolveResult.matched(filtered[0].id)
        return ResolveResult.ambiguous(
            (c.id for c in filtered),
            reason=f"{len(filtered)} candidate lemmas for ({entry.word}, pos={entry.pos_hint})",
        )


def _accepted_lemma_pos_types(pos_hint: Optional[str]) -> Optional[set[str]]:
    """Return the set of Lemma.pos_type values that can match this YLE pos shorthand.

    Returns None for unknown shorthand (skip pos filtering and let lemma_text alone decide).
    """
    if pos_hint is None:
        return None
    mapped = YLE_POS_TO_LEMMA_POS.get(pos_hint)
    if mapped is None:
        return None
    return set(mapped)
