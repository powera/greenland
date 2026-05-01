"""Protocol and dataclasses for tier importers.

Each tier source supplies a class implementing ``TierImporter``: it knows how
to read its source file and turn raw rows into ``TierEntry`` objects, and how
to resolve each entry to a Lemma in the database (or report ambiguity).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable, List, Optional, Protocol

from sqlalchemy.orm import Session


@dataclass(frozen=True)
class TierEntry:
    """One row from a tier source, language-and-source agnostic.

    ``language_code`` is per-entry to leave room for sources that mix languages,
    though current sources (YLE, CEFR for English) are single-language.
    """

    word: str
    language_code: str
    pos_hint: Optional[str]  # e.g., "n", "v", "adj" — source-specific shorthand
    tier_name: str  # must match a TierDefinition.tier_name for the source
    sense_hint: Optional[str] = None  # disambiguation string from the source, if any
    themes: tuple[str, ...] = field(default_factory=tuple)
    raw: Optional[dict] = None  # original row for debugging / pending-review payload


class ResolveStatus(str, Enum):
    MATCHED = "matched"
    AMBIGUOUS = "ambiguous"
    UNMATCHED = "unmatched"


@dataclass(frozen=True)
class ResolveResult:
    """Outcome of resolving a TierEntry to one or more candidate Lemma ids."""

    status: ResolveStatus
    lemma_ids: tuple[int, ...] = ()  # populated for MATCHED (len 1) and AMBIGUOUS (len>1)
    reason: Optional[str] = None  # human-readable explanation for the status

    @classmethod
    def matched(cls, lemma_id: int) -> "ResolveResult":
        return cls(status=ResolveStatus.MATCHED, lemma_ids=(lemma_id,))

    @classmethod
    def ambiguous(cls, lemma_ids: Iterable[int], reason: Optional[str] = None) -> "ResolveResult":
        return cls(status=ResolveStatus.AMBIGUOUS, lemma_ids=tuple(lemma_ids), reason=reason)

    @classmethod
    def unmatched(cls, reason: Optional[str] = None) -> "ResolveResult":
        return cls(status=ResolveStatus.UNMATCHED, reason=reason)


class TierImporter(Protocol):
    """Source-specific tier loader. Add one per data source.

    Concrete importers should also expose module-level constants ``SOURCE``
    (the tier source key, e.g. ``"cambridge_yle"``) and any source-specific
    file path defaults.
    """

    source: str

    def load_entries(self) -> List[TierEntry]:
        """Read the source file and return one TierEntry per row."""
        ...

    def resolve(self, session: Session, entry: TierEntry) -> ResolveResult:
        """Resolve a single TierEntry to a Lemma id (or ambiguity / miss)."""
        ...
