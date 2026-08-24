"""Emoji model: one row per glyph, carrying its review decision.

The review that populates emoji is driven from the *emoji* side, not the lemma
side, and this table is what makes that possible. Every glyph worth
considering gets a row, and each row records the decision made about it:

``undecided``
    Not yet reviewed. The starting state for every seeded glyph.
``assigned``
    ``lemma_id`` is set: this glyph depicts that lemma's concept.
``no_match``
    Reviewed and dismissed -- nothing in the vocabulary depicts it, or only by
    a stretch. Distinct from ``undecided`` so a dismissed glyph is never shown
    again, which is what lets the walk terminate.
``missing_lemma``
    There is one clear concept for the glyph but no lemma for it yet (the ninja
    emoji, the pile-of-poo emoji). ``pending_import_id`` points at the staged
    term; once that is approved the glyph can be attached to the new lemma.

Why a table rather than a column on ``Lemma``
---------------------------------------------
Three things a column cannot do:

1. **Uniqueness is enforced, not scanned for.** An emoji belongs to at most one
   lemma, and ``lemma_id`` is not unique here only because many rows share
   NULL -- the *glyph* is the primary identity, so one glyph physically cannot
   name two lemmas.
2. **Negative decisions have a home.** "This glyph matches nothing" is a fact
   worth storing; on a lemma column there is nowhere to put it.
3. **Glyphs with no lemma are representable.** ``missing_lemma`` rows have no
   lemma to hang off of at all.

``Lemma.emoji`` remains as a derived JSON mirror of the assigned rows, because
that is what the release round trip (``storage.release.lemma``) reads and
writes. This table is the source of truth; the mirror is refreshed from it by
``words.emoji.refresh_lemma_mirror``. Order within the mirror carries primacy
-- the first entry is the primary glyph -- so no rank column is stored here.

Who made a decision and when is recorded in the operation log, as everywhere
else in this schema, rather than duplicated onto these rows.
"""

import datetime
from typing import Optional

from sqlalchemy import (
    TIMESTAMP,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from storage.models.schema import Base

# Not yet reviewed.
EMOJI_STATUS_UNDECIDED: str = "undecided"
# Attached to a lemma (lemma_id is set).
EMOJI_STATUS_ASSIGNED: str = "assigned"
# Reviewed; nothing in the vocabulary depicts it.
EMOJI_STATUS_NO_MATCH: str = "no_match"
# One clear concept, but no lemma for it yet (pending_import_id is set).
EMOJI_STATUS_MISSING_LEMMA: str = "missing_lemma"

EMOJI_STATUSES: frozenset[str] = frozenset(
    {
        EMOJI_STATUS_UNDECIDED,
        EMOJI_STATUS_ASSIGNED,
        EMOJI_STATUS_NO_MATCH,
        EMOJI_STATUS_MISSING_LEMMA,
    }
)


class Emoji(Base):
    """One reviewable emoji glyph and the decision made about it."""

    __tablename__ = "emoji"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # The glyph itself, and the identity of the row. Unique because an emoji
    # can name at most one lemma; the constraint is what enforces that rule.
    value: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)

    # Unicode identity, seeded from the Unicode tables. codepoint is the
    # "U+1F415" form; it is NULL for multi-codepoint sequences (ZWJ sequences,
    # flags), which have no single codepoint.
    unicode_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    codepoint: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    block: Mapped[Optional[str]] = mapped_column(String, nullable=True, index=True)

    # What the glyph actually depicts, when the Unicode name does not say it
    # usefully ("SPARKLES", "PILE OF POO"). Free text, written during review.
    gloss: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # One of EMOJI_STATUSES. Seeded rows start "undecided".
    status: Mapped[str] = mapped_column(
        String,
        nullable=False,
        index=True,
        default=EMOJI_STATUS_UNDECIDED,
        server_default=EMOJI_STATUS_UNDECIDED,
    )

    # Set only when status == "assigned". Deliberately NOT unique: a lemma may
    # hold several glyphs ("dog" gets the dog and dog-face emoji), and the
    # one-lemma-per-emoji rule is carried by value's uniqueness instead.
    lemma_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("lemmas.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Set only when status == "missing_lemma": the term staged for creation.
    pending_import_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("pending_imports.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Why a glyph was dismissed, or any other note left by the reviewer.
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    added_at: Mapped[datetime.datetime] = mapped_column(TIMESTAMP, server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP, server_default=func.now(), onupdate=func.now()
    )

    lemma = relationship("Lemma", backref="emoji_assignments")

    def __repr__(self) -> str:
        return f"<Emoji {self.value!r} status={self.status} lemma_id={self.lemma_id}>"
