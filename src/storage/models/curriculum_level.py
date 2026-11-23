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

Names
-----
``name`` is the English title, and is required. Translations live one row per
language in ``curriculum_level_translations``, the same shape as a lemma and
its ``LemmaTranslation`` rows. They are keyed by the learner's *interface*
language, not the language being learnt: a Spanish speaker learning
Lithuanian sees the Spanish title.

JSON columns
------------
``prerequisites``
    Sorted list of level numbers that must be completed first. These are
    *hard*: Trakaido locks the unit until they are done (a client may choose
    to treat them as advice). Only the named band needs these (see the band
    comment in ``constants``): the core is sequential by construction, and the
    named units are reached by prerequisite rather than by number. A
    prerequisite names a level at or above ``constants.MIN_PREREQUISITE_LEVEL``,
    and the graph may not have a cycle. The previous volume of a series is an
    *implied* prerequisite and is not stored here (see below).
``themes``
    Ordered list of use-case slugs from ``LEVEL_THEMES``, most relevant first:
    "is this unit useful for travel / a high-school class / ...". Shipped so
    the client can suggest units without the learner hunting through 100+.
``content_flags``
    Sorted list of slugs from ``CONTENT_FLAGS``, marking units a client may
    want to hide (weapons, drugs and alcohol, sexual, explicit anatomy).
    Recorded and shipped; no client filters on them yet.
``extra``
    Free-form object for anything Trakaido wants that has not earned a column
    yet. Only the keys in ``storage.crud.curriculum_level.CLIENT_EXTRA_KEYS``
    are copied into the manifest entry; the rest (editorial bookkeeping such
    as a CEFR estimate's rationale) stays in the database and the release.

Series
------
``series`` and ``volume`` say that a level is one volume of a topic split over
several levels ("Plants and Growth" is volume 1, "Plants and Growth 2" is
volume 2). This is the only place that grouping is recorded: names are display
text and nothing parses their numbers. The manifest export turns it into a
prerequisite on the previous volume, so a client never offers volume 3 before
volume 2, and ships both fields so a client can show the series as one row.
``quality.curriculum_volumes`` also reads it to find interchangeable volumes
for word placement.
"""

import datetime
import json
from typing import Any, Dict, List, Optional

from sqlalchemy import TIMESTAMP, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from storage.models.schema import Base

# Whole CEFR levels, then the half-steps a level may be pinned to more finely.
# C1/C2 are not split: nothing in the curriculum is written that high, and a
# finer grade there would be false precision.
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

# Use-case hints: which units are worth suggesting to a learner with a given
# goal.  ``school`` means "I'm taking this language in high school" (classroom
# objects, school subjects, typical textbook units), not academic register --
# the topic band covers that.
LEVEL_THEMES: tuple[str, ...] = ("travel", "school", "daily-life", "work", "heritage")

# Content a client may want to filter out.  ``drugs`` includes alcohol.  There
# is deliberately no general ``violence`` flag: martial arts and contact sports
# need no filter, and weapons have their own.
CONTENT_FLAGS: tuple[str, ...] = ("weapons", "drugs", "sexual", "explicit-anatomy")


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

    # English display name.
    name: Mapped[str] = mapped_column(String, nullable=False)

    # One of CEFR_LEVELS, or NULL when not yet estimated.
    cefr: Mapped[Optional[str]] = mapped_column(String, nullable=True, index=True)

    # JSON list of level numbers; NULL means none.
    prerequisites: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Series slug (e.g. "plants-and-growth") and this level's 1-based volume
    # within it; both NULL for a standalone level.
    series: Mapped[Optional[str]] = mapped_column(String, nullable=True, index=True)
    volume: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # JSON list of LEVEL_THEMES slugs, most relevant first; NULL means none.
    themes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # JSON list of CONTENT_FLAGS slugs; NULL means none.
    content_flags: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # JSON object; whitelisted keys are merged into the manifest entry. NULL means none.
    extra: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Editorial notes for people curating the course. Shipped to data/release,
    # never to the client.
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    added_at: Mapped[datetime.datetime] = mapped_column(TIMESTAMP, server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP, server_default=func.now(), onupdate=func.now()
    )

    translations: Mapped[List["CurriculumLevelTranslation"]] = relationship(
        "CurriculumLevelTranslation",
        back_populates="curriculum_level",
        cascade="all, delete-orphan",
        order_by="CurriculumLevelTranslation.language_code",
    )

    def get_prerequisites(self) -> List[int]:
        """The decoded ``prerequisites`` list (empty when none)."""
        decoded: List[int] = _decode_json(self.prerequisites, [])
        return decoded

    def get_themes(self) -> List[str]:
        """The decoded ``themes`` list (empty when none)."""
        decoded: List[str] = _decode_json(self.themes, [])
        return decoded

    def get_content_flags(self) -> List[str]:
        """The decoded ``content_flags`` list (empty when none)."""
        decoded: List[str] = _decode_json(self.content_flags, [])
        return decoded

    def get_extra(self) -> Dict[str, Any]:
        """The decoded ``extra`` object (empty when none)."""
        decoded: Dict[str, Any] = _decode_json(self.extra, {})
        return decoded

    def get_translations(self) -> Dict[str, str]:
        """Language code -> translated name, English excluded."""
        return {row.language_code: row.name for row in self.translations}

    def get_names(self) -> Dict[str, str]:
        """Every name keyed by language code, English first."""
        return {"en": self.name, **self.get_translations()}

    def __repr__(self) -> str:
        return f"<CurriculumLevel {self.level} {self.name!r} cefr={self.cefr}>"


class CurriculumLevelTranslation(Base):
    """One level's name in one interface language other than English."""

    __tablename__ = "curriculum_level_translations"

    level: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("curriculum_levels.level", ondelete="CASCADE"),
        primary_key=True,
    )
    language_code: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)

    added_at: Mapped[datetime.datetime] = mapped_column(TIMESTAMP, server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP, server_default=func.now(), onupdate=func.now()
    )

    curriculum_level: Mapped[CurriculumLevel] = relationship(
        "CurriculumLevel", back_populates="translations"
    )

    def __repr__(self) -> str:
        return f"<CurriculumLevelTranslation {self.level} {self.language_code}={self.name!r}>"
