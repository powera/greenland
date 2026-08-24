#!/usr/bin/python3

"""The emoji list being walked, and what each glyph is matched against.

Populating emoji is driven from the *emoji* side rather than the lemma side:
because an emoji belongs to at most one lemma (see :mod:`words.emoji`), walking
the catalog once decides every glyph exactly once and terminates. Walking the
~50k lemmas instead would ask "does this word have an emoji?" almost always to
answer "no".

Each glyph has three possible outcomes, all of them progress:

``assigned``
    A lemma in the database depicts it. The glyph is attached to that lemma.
``no_match``
    Nothing depicts it, or only by a stretch. The glyph is dismissed and never
    shown again.
``missing_lemma``
    There is one clear concept for the glyph but the database has no lemma for
    it -- the ninja emoji, the pile-of-poo emoji. This stages a
    :class:`~storage.models.imports.PendingImport` so the ordinary approval
    path can create the word, and records the glyph so it can be attached once
    the lemma exists.

The catalog itself is a generated snapshot of the pictographic Unicode blocks
(``data/emoji_catalog.json``); regenerate it with
``PYTHONPATH=src python -m words.emoji_catalog --rebuild``.
"""

from __future__ import annotations

import json
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

CATALOG_PATH = Path(__file__).parent / "data" / "emoji_catalog.json"

# Pictographic blocks worth reviewing. Flags and regional indicators are left
# out on purpose: they denote places, which are names rather than lemmas.
CATALOG_RANGES: Sequence[Tuple[int, int, str]] = (
    (0x1F300, 0x1F5FF, "symbols_pictographs"),
    (0x1F600, 0x1F64F, "emoticons"),
    (0x1F680, 0x1F6FF, "transport_map"),
    (0x1F900, 0x1F9FF, "supplemental"),
    (0x1FA70, 0x1FAFF, "extended_a"),
    (0x2600, 0x26FF, "misc_symbols"),
    (0x2700, 0x27BF, "dingbats"),
)

# Unicode-name fragments marking a glyph as structural UI rather than a
# depictable concept. Arrows and keycaps are shapes, not things.
SKIP_NAME_FRAGMENTS: Sequence[str] = (
    "REGIONAL INDICATOR",
    "VARIATION SELECTOR",
    "TAG ",
    "ZERO WIDTH",
    "ARROW",
    "KEYCAP",
    "SELECTOR",
    "MODIFIER FITZPATRICK",
)


@dataclass(frozen=True)
class CatalogEntry:
    """One emoji awaiting (or having received) a decision."""

    value: str
    codepoint: str
    name: str
    block: str

    @property
    def search_terms(self) -> List[str]:
        """Lemma-text candidates derived from the Unicode name.

        ``"DOG FACE"`` yields ``["dog face", "dog"]`` -- the full name first,
        then the name with trailing qualifiers (FACE, SIGN, SYMBOL) stripped,
        which is usually the actual word. Used to seed the candidate search;
        the reviewer can always search for something else.
        """
        lowered = self.name.lower()
        terms = [lowered]
        for qualifier in (" face", " sign", " symbol", " button", " selector"):
            if lowered.endswith(qualifier):
                trimmed = lowered[: -len(qualifier)].strip()
                if trimmed and trimmed not in terms:
                    terms.append(trimmed)
        return terms


def build_catalog_entries() -> List[CatalogEntry]:
    """Derive the catalog from the running Python's Unicode tables.

    Used to regenerate the snapshot; reading the snapshot is what callers do,
    so that the review order does not shift under a Python upgrade.
    """
    entries: List[CatalogEntry] = []
    for low, high, block in CATALOG_RANGES:
        for codepoint in range(low, high + 1):
            character = chr(codepoint)
            try:
                name = unicodedata.name(character)
            except ValueError:
                continue
            if any(fragment in name for fragment in SKIP_NAME_FRAGMENTS):
                continue
            entries.append(
                CatalogEntry(
                    value=character,
                    codepoint=f"U+{codepoint:04X}",
                    name=name,
                    block=block,
                )
            )
    return entries


@lru_cache(maxsize=1)
def load_catalog() -> Tuple[CatalogEntry, ...]:
    """The catalog snapshot, in review order (cached)."""
    with CATALOG_PATH.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    return tuple(CatalogEntry(**entry) for entry in payload["entries"])


def catalog_by_value() -> Dict[str, CatalogEntry]:
    """The catalog indexed by glyph."""
    return {entry.value: entry for entry in load_catalog()}


def write_catalog(entries: Iterable[CatalogEntry], path: Path = CATALOG_PATH) -> int:
    """Write a catalog snapshot to disk. Returns the number of entries."""
    listed = list(entries)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(
            {"entries": [entry.__dict__ for entry in listed]},
            handle,
            ensure_ascii=False,
            indent=1,
        )
        handle.write("\n")
    return len(listed)


def main() -> None:
    """CLI: regenerate the catalog snapshot."""
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Regenerate data/emoji_catalog.json from Unicode tables.",
    )
    args = parser.parse_args()

    if args.rebuild:
        count = write_catalog(build_catalog_entries())
        print(f"Wrote {count} entries to {CATALOG_PATH}")
    else:
        print(f"{len(load_catalog())} entries in {CATALOG_PATH}")


if __name__ == "__main__":
    main()
