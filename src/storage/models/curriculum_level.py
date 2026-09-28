"""Curriculum level metadata: one row per level number that has a name.

``Lemma.difficulty_level`` says which level a word belongs to; this table says
what a level *is* -- the title a learner sees, roughly where it sits on the
CEFR scale, and which levels have to be finished before it opens. The wireword
manifest ships these rows under ``config.levels`` so Trakaido can show
"Food & Cooking II" instead of "Level 120".

Keyed on the level number itself rather than a surrogate id: a level *is* its
number everywhere else in the schema (lemmas, overrides, sentence rollups), and
a row here only means anything while lemmas carry that number. Levels with no
row simply ship unnamed; a row is not needed for a level to exist.

The table is shared across target languages, as the level numbers are. Per
language variation (country units) lives in the difficulty overrides, which
move *words* between levels; a level's name does not change with the language
being learnt.

JSON columns
------------
``names``
    UI language code -> display name, e.g. ``{"en": "First Words",
    "es": "Primeras palabras"}``. Keyed by the learner's *interface* language,
    not the language being learnt. ``en`` is required, as the name Barsukas and
    the logs use.
``prerequisites``
    Sorted list of level numbers that must be completed first. Only the named
    band needs these (see the band comment in ``constants``): the core is
    sequential by construction, and the named units are reached by
    prerequisite rather than by number.
``extra``
    Free-form object for anything Trakaido wants that has not earned a column
    yet (an icon, a colour, a short description). Its keys are merged into the
    manifest entry, so they may not shadow the columns above.

Validation lives in :mod:`storage.crud.curriculum_level`; the model only
stores and decodes.
"""

import datetime
import json
from typing import Any, Dict, List, Optional

from sqlalchemy import TIMESTAMP, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from storage.models.schema import Base

# Whole CEFR levels, then the half-steps a level may be pinned to more finely.
# C1/C2 are not split: nothing in the curriculum is written that high, and a
# finer grade there would be false precision.
CEFR_MAJOR_LEVELS: tuple[str, ...] = ("A1", "A2", "B1", "B2", "C1", "C2")
CEFR_LEVELS: tuple[str, ...] = (
    "A1",
    "A1.1",
    "A1.2",
    "A2",
    "A2.1",
    "A2.2",
    "B1",
    "B1.1",
    "B1.2",
    "B2",
    "B2.1",
    "B2.2",
    "C1",
    "C2",
)


def _decode_json(raw: Optional[str], default: Any) -> Any:
    """Decode a JSON text column, treating NULL or blank as ``default``."""
    if not raw:
        return default
    return json.loads(raw)


class CurriculumLevel(Base):
    """Display and sequencing metadata for one curriculum level number."""

    __tablename__ = "curriculum_levels"

    # The level number, as used by Lemma.difficulty_level. Not autoincrement:
    # the number is the identity.
    level: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)

    # JSON object: UI language code -> display name. "en" is always present.
    names: Mapped[str] = mapped_column(Text, nullable=False)

    # One of CEFR_LEVELS, or NULL when not yet estimated.
    cefr: Mapped[Optional[str]] = mapped_column(String, nullable=True, index=True)

    # JSON list of level numbers; NULL means none.
    prerequisites: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # JSON object merged into the manifest entry; NULL means none.
    extra: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Editorial notes for people curating the course. Shipped to data/release,
    # never to the client.
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    added_at: Mapped[datetime.datetime] = mapped_column(TIMESTAMP, server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP, server_default=func.now(), onupdate=func.now()
    )

    def get_names(self) -> Dict[str, str]:
        """The decoded ``names`` object."""
        decoded: Dict[str, str] = _decode_json(self.names, {})
        return decoded

    def get_prerequisites(self) -> List[int]:
        """The decoded ``prerequisites`` list (empty when none)."""
        decoded: List[int] = _decode_json(self.prerequisites, [])
        return decoded

    def get_extra(self) -> Dict[str, Any]:
        """The decoded ``extra`` object (empty when none)."""
        decoded: Dict[str, Any] = _decode_json(self.extra, {})
        return decoded

    @property
    def display_name(self) -> str:
        """The English name, which every row carries."""
        return self.get_names().get("en", f"Level {self.level}")

    def __repr__(self) -> str:
        return f"<CurriculumLevel {self.level} {self.display_name!r} cefr={self.cefr}>"
