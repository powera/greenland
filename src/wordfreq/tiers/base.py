"""Protocol and dataclasses for tier importers.

Each tier source supplies a class implementing ``TierImporter``: it knows how
to read its source file and turn raw rows into ``TierEntry`` objects, and how
to resolve each entry to candidate Lemmas in the database.

The runner attaches every resolved candidate (zero, one, or many). The
annotation row is always written, regardless of how many lemmas matched, so
the annotation table itself acts as the registry of "words this source asserts
exist at this tier" — including those without any matching lemma yet.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Protocol

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
    raw: Optional[dict] = None  # original row for debugging


class TierImporter(Protocol):
    """Source-specific tier loader. Add one per data source.

    Concrete importers should also expose module-level constant ``SOURCE``
    (the tier source key, e.g. ``"cambridge_yle"``).
    """

    source: str

    def load_entries(self) -> List[TierEntry]:
        """Read the source file and return one TierEntry per row.

        Importers may emit multiple TierEntry objects per source row (e.g. YLE
        ``Ann/Anna`` becomes one entry per slash-separated surface form, and a
        row with multiple POS tags becomes one entry per POS).
        """
        ...

    def resolve(self, session: Session, entry: TierEntry) -> List[int]:
        """Return candidate Lemma ids for this entry. Empty list = no match."""
        ...
