#!/usr/bin/env python3
"""Import the geography catalog: every country, its people and its languages.

Assembled rather than mined, like the chemical elements: a frequency list
finds the countries a corpus mentions, and what makes the set worth having is
that it is closed.  The list itself lives in
src/words/difficulty/geography_catalog.py, which is also what makes levels
231-233 and 1031-1033 fixed sets -- a word joins them by being listed there,
never by level placement -- and what the per-language country promotion
(src/scripts/apply_country_overrides.py) reads.  This script only adds what the
catalog lists:

* 232/233 -- the people, origin adjectives and languages of the 231 countries.
  The countries themselves are all stored already, so 231 is not listed.
* 1031 -- every other UN member and observer state, Kosovo, and a few
  territories learned as places of their own (Puerto Rico, Greenland).
* 1032 -- their people and origin adjectives, and the ethnic groups that are
  not nationalities (Kurd, Basque, Yoruba).
* 1033 -- the remaining major languages, including the varieties of Chinese
  and Arabic; the general "Chinese" and "Arabic" stay at 233.

Everything goes through ``api.lemmas.add_sense`` with the subtype fixed: "Greek"
is three lemmas -- the person, the adjective and the language -- and both other
add paths stop at a headword that already exists.  Each list's label and tags
keep its senses apart, so a re-run is free for everything a previous run added
or matched.  Senses already stored without a label (the older nationality
nouns) cost one matching call the first time.

Nothing is moved: ``relevel_existing`` would also mark the sense rare.  The
three senses still at 1031 from before the split (Mongolian, Igbo, Assamese)
move by migrations/20261017_split_extended_geography_levels.py, which also
names the levels.  Run that first.

Running without ``--execute`` only prints the plan and makes no HTTP requests.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
for path in (ROOT, ROOT / "src"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from scripts.wordlists.wordlist_import_helper import SenseEntry, SenseList, run_sense_import
from words.difficulty.geography_catalog import GEOGRAPHY_SENSES, GeographySense

THEME_TAG = "geography"

# subtype -> (field as the prompt names it, label, subtype tag).  The labels
# are the ones the catalog's first import stored, so those senses match free.
_LIST_KINDS: dict[str, tuple[str, str, str]] = {
    "region": ("countries and territories", "country", "geography_country"),
    "nationality": ("nationalities and peoples", "nationality", "geography_nationality"),
    "origin": ("national and ethnic origin", "origin", "geography_origin"),
    "language_name": ("languages of the world", "language", "geography_language"),
}

# (level, subtype), in run order: the main tier first.
_LIST_ORDER: tuple[tuple[int, str], ...] = (
    (232, "nationality"),
    (232, "origin"),
    (233, "language_name"),
    (1031, "region"),
    (1032, "nationality"),
    (1032, "origin"),
    (1033, "language_name"),
)


def _entry(sense: GeographySense) -> SenseEntry:
    if sense.pos_subtype == "region":
        # A country name is its own label unless another place shares it.
        if sense.disambiguation is None:
            return SenseEntry(sense.lemma_text, sense.definition, unique=True)
        return SenseEntry(sense.lemma_text, sense.definition, sense.disambiguation)
    return SenseEntry(sense.lemma_text, sense.definition)


def build_sense_lists() -> list[SenseList]:
    """One list per level and subtype, in :data:`_LIST_ORDER`."""
    sense_lists: list[SenseList] = []
    for level, subtype in _LIST_ORDER:
        domain, label, subtype_tag = _LIST_KINDS[subtype]
        entries = tuple(
            _entry(sense)
            for sense in GEOGRAPHY_SENSES
            if sense.base_level == level and sense.pos_subtype == subtype
        )
        sense_lists.append(
            SenseList(
                level=level,
                domain=domain,
                label=label,
                tags=(THEME_TAG, subtype_tag),
                entries=entries,
                pos_subtype=subtype,
            )
        )
    return sense_lists


if __name__ == "__main__":
    raise SystemExit(run_sense_import(build_sense_lists(), __doc__ or ""))
