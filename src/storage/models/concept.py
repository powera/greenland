"""Concept model: encyclopedia-style entries (e.g. "World War II", "Art Deco").

Concepts are short, web-page-length encyclopedia entries about a topic. They are
deliberately kept OUTSIDE the lemma/GUID/data-release machinery: they are not
lexical items, they are not exported to ``data/release``, and they carry no GUID.
They live in whichever storage backend is configured (Postgres in production,
SQLite locally) via the shared :class:`~storage.models.schema.Base`.

Slug semantics follow the Wikipedia convention: spaces and underscores are
equivalent and capitalization is preserved and significant. The canonical stored
form uses underscores (URL-ready); display converts underscores back to spaces.
Use :func:`normalize_concept_slug` for all lookups/inserts and
:func:`concept_slug_to_title` for display so the two never drift apart.
"""

import datetime
import re
from typing import List, NamedTuple, Optional

from sqlalchemy import (
    TIMESTAMP,
    Boolean,
    Float,
    Integer,
    String,
    Text,
    ForeignKey,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from storage.models.schema import Base

# Maximum number of source references accepted for a concept. The minimum (2) is
# treated as guidance rather than a hard floor so thin entries are not blocked.
MAX_CONCEPT_SOURCES: int = 10

_WHITESPACE_RE = re.compile(r"\s+")


def normalize_concept_slug(text: str) -> str:
    """Return the canonical slug for a concept title or wiki-link target.

    Collapses internal whitespace and replaces spaces with underscores, leaving
    capitalization untouched. ``"Abraham Lincoln"``, ``" Abraham  Lincoln "`` and
    ``"Abraham_Lincoln"`` all normalize to ``"Abraham_Lincoln"``, so the three
    are treated as the same concept.

    Args:
        text: A human-entered title or the inside of a ``[[...]]`` wiki link.

    Returns:
        The canonical, underscore-joined slug (capitalization preserved).
    """
    collapsed = _WHITESPACE_RE.sub(" ", text.strip())
    return collapsed.replace(" ", "_")


# Wiki links inside concept bodies: ``[[Target]]`` or ``[[Target|display text]]``.
# Target is everything up to an optional pipe; display text is optional.
WIKI_LINK_RE = re.compile(r"\[\[([^\]|]+?)(?:\|([^\]]+))?\]\]")


class WikiLink(NamedTuple):
    """A parsed ``[[...]]`` reference found in a concept body.

    Attributes:
        target_slug: The normalized (underscore) slug the link points to.
        display: The text to show for the link (custom piped text, or the
            human-readable title of the target).
        raw: The original substring, including the brackets, for replacement.
    """

    target_slug: str
    display: str
    raw: str


def parse_wiki_links(text: str) -> List[WikiLink]:
    """Extract all ``[[wiki links]]`` from a concept body.

    Supports both ``[[Battle of Gettysburg]]`` and piped
    ``[[U.S. Civil War|the war]]`` syntax. Targets are normalized so they can be
    matched directly against ``Concept.slug``.

    Args:
        text: The concept body (or any text) to scan.

    Returns:
        A list of :class:`WikiLink` in order of appearance.
    """
    links: List[WikiLink] = []
    for match in WIKI_LINK_RE.finditer(text):
        target_raw = match.group(1).strip()
        piped = match.group(2)
        target_slug = normalize_concept_slug(target_raw)
        display = piped.strip() if piped else concept_slug_to_title(target_slug)
        links.append(WikiLink(target_slug=target_slug, display=display, raw=match.group(0)))
    return links


def concept_slug_to_title(slug: str) -> str:
    """Return the human-readable title for a canonical slug.

    Inverse of :func:`normalize_concept_slug` for display purposes: underscores
    become spaces, capitalization preserved.

    Args:
        slug: A canonical (underscore-joined) concept slug.

    Returns:
        The display title with spaces instead of underscores.
    """
    return slug.replace("_", " ")


class Concept(Base):
    """An encyclopedia-style entry about a topic.

    Examples of topics: "World War II", "Albert Einstein", "Art Deco". The
    ``body`` is typically LLM-generated from ``summary`` plus the ``sources`` and
    may contain ``[[Wiki Links]]`` referencing other concepts by slug.
    """

    __tablename__ = "concepts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Canonical underscore-joined slug AND the wiki-link target, e.g.
    # "Abraham_Lincoln". Unique; capitalization is significant. Always assign via
    # normalize_concept_slug() and display via concept_slug_to_title().
    slug: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)

    # Coarse classification (e.g. "event", "person", "art_movement"). Free-form.
    concept_type: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # One-sentence description (English for now). Also steers body generation.
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # The entry itself (English for now): Markdown, may contain [[wiki links]].
    body: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # JSON array of source references used as LLM input + provenance, e.g.
    # [{"url": "...", "title": "...", "note": "..."}]. Up to MAX_CONCEPT_SOURCES.
    sources: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # JSON array of free-form tags (mirrors Lemma.tags).
    tags: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Provenance / review metadata (mirrors conventions on Lemma/GrammarFact).
    source_model: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    added_at: Mapped[datetime.datetime] = mapped_column(TIMESTAMP, server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP, server_default=func.now(), onupdate=func.now()
    )

    @property
    def title(self) -> str:
        """Human-readable display title derived from the slug."""
        return concept_slug_to_title(self.slug)

    def __repr__(self) -> str:
        return f"<Concept(id={self.id}, slug={self.slug!r}, verified={self.verified})>"


class ConceptLemmaLink(Base):
    """A one-to-one pairing between a lemma and the concept that names it.

    Many concepts (e.g. "Frank Lloyd Wright") are *not* lexical items and never
    get a lemma; this table exists only for the overlap where a concept's topic
    is also a dictionary headword (e.g. "Apple", "Banana").

    Storage model (deliberate, see this module's docstring): concepts live
    outside the lemma machinery, and in hosted deployments they live in a
    *separate, read-only* database from lemmas. So this table lives with the
    lemmas (writable in all modes) and does **not** hard-FK the concepts table.
    The durable payload is the concept's Wikidata Q-id (e.g. "Q89" for Apple) --
    that is the only piece of concept data the data/release export needs. The
    ``concept_slug`` is stored for display/round-tripping only.

    The pairing is strict one-to-one: a lemma links to at most one concept and a
    given concept (by Q-id) links to at most one lemma (unique constraints on
    ``lemma_id`` and ``qid``). A lemma represents a single sense ("bank (river)"
    vs "bank (finance)"), so an ambiguous match should be left unlinked rather
    than guessed. Links are curated for now; an auto-match pass may seed
    candidates later, but acceptance stays explicit.
    """

    __tablename__ = "concept_lemma_links"
    __table_args__ = (
        UniqueConstraint("lemma_id", name="uq_concept_lemma_lemma"),
        UniqueConstraint("qid", name="uq_concept_lemma_qid"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lemma_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("lemmas.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Wikidata Q-id of the paired concept (e.g. "Q89"). This is the value emitted
    # into data/release. Stored here rather than joined from the concepts DB so
    # the export works even when concepts live in a separate/read-only backend.
    qid: Mapped[str] = mapped_column(String, nullable=False, index=True)

    # Canonical concept slug for display and round-tripping back to the concept
    # page (concepts.detail). Not a foreign key.
    concept_slug: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # Whether a human has confirmed this pairing (vs. an auto-suggested candidate).
    verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    added_at: Mapped[datetime.datetime] = mapped_column(TIMESTAMP, server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP, server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return (
            f"<ConceptLemmaLink(lemma_id={self.lemma_id}, qid={self.qid!r}, "
            f"verified={self.verified})>"
        )


class ConceptWikidataIndex(Base):
    """Reverse index from Wikidata Q-id to an accepted or rejected concept."""

    __tablename__ = "concept_wikidata_index"

    qid: Mapped[str] = mapped_column(String, primary_key=True)
    concept_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("concepts.id"), nullable=True, index=True
    )
    # Remote Wikipedia article title for this Q-id. Cached when a Q-id is known
    # but no concept exists yet (concept_id NULL), e.g. ranked "wanted" red links
    # resolved by storage.wikidata.resolve_titles_to_qids. Just the title string,
    # not the full Wikidata entity payload.
    title: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    rejected: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    added_at: Mapped[datetime.datetime] = mapped_column(TIMESTAMP, server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP, server_default=func.now(), onupdate=func.now()
    )

    concept: Mapped[Optional[Concept]] = relationship("Concept")

    def __repr__(self) -> str:
        return (
            f"<ConceptWikidataIndex(qid={self.qid!r}, concept_id={self.concept_id!r}, "
            f"rejected={self.rejected})>"
        )
