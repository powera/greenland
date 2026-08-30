#!/usr/bin/env python3
"""Move level 18's geography and calendar lemmas down to level 14.

Level 18 held two groups that do not belong together and do not belong at 18:

* 18 ``natural_feature`` nouns (mountain, river, island, volcano) -- ordinary
  landscape vocabulary.
* 19 ``temporal_name`` nouns -- the seven weekdays and twelve months.

Both are early vocabulary.  The weekdays and months in particular are among the
first closed sets a learner meets in any language, and the landforms sit beside
words already at 14: ``N11_020``-``N11_031`` (sky, sun, moon, star, cloud,
rain, snow, wind, storm, fog, ice, temperature) are all level 14 already, so
the split that left mountain and river at 18 was an artifact rather than a
judgement.  Moving these 37 puts the whole natural-world group at one level and
empties 18 for the linguistics terms that replace it.

``forecast`` (``N11_032``) moves with them because it is in the batch, but it
is worth flagging rather than fixing here: it carries the ``natural_feature``
subtype while sitting between the weather nouns, and a forecast is a prediction
about the weather rather than a feature of the landscape.  Changing a subtype
is a different operation from changing a level, with its own GUID consequences,
so this script does not attempt it.

``lithium`` (``N15_003``) is re-leveled here too, in the other direction: it is
the one ``chemical_compound`` lemma still at -1 (unassigned), and it belongs
with the element names at 54.  Its nine siblings in the N15 range are already
leveled sensibly (oxygen 30, hydrogen/nitrogen/chlorine 24, acid/base 19), so
this is the last of that group left unset.

Patches by GUID rather than by lemma text.  A GUID names one sense; a lemma
text can match several ("lead" the metal and "lead" the verb are different
rows), and this must not re-level a homograph it was not aimed at.

Running without ``--execute`` only prints the plan and makes no HTTP requests.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Sequence, Tuple

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api import BarsukasAPIError
from api.constants import BASE_URL
from api.lemmas import get_lemma, patch_lemma_difficulty

# (guid, expected lemma text, target level).  The lemma text is not sent -- it
# is checked against what the server returns, so a GUID that has come to mean
# something else since this script was written stops the run instead of
# silently re-leveling the wrong sense.
MOVES: Sequence[Tuple[str, str, int]] = (
    # Landforms and water: the rest of the N11 natural-world range is at 14.
    ("N11_001", "mountain", 14),
    ("N11_002", "hill", 14),
    ("N11_004", "river", 14),
    ("N11_005", "lake", 14),
    ("N11_006", "ocean", 14),
    ("N11_007", "sea", 14),
    ("N11_008", "beach", 14),
    ("N11_009", "coast", 14),
    ("N11_010", "island", 14),
    ("N11_011", "peninsula", 14),
    ("N11_012", "desert", 14),
    ("N11_014", "canyon", 14),
    ("N11_015", "cliff", 14),
    ("N11_016", "cave", 14),
    ("N11_017", "waterfall", 14),
    ("N11_018", "glacier", 14),
    ("N11_019", "volcano", 14),
    ("N11_032", "forecast", 14),
    # Weekdays.
    ("N32_001", "Monday", 14),
    ("N32_002", "Tuesday", 14),
    ("N32_003", "Wednesday", 14),
    ("N32_004", "Thursday", 14),
    ("N32_005", "Friday", 14),
    ("N32_006", "Saturday", 14),
    ("N32_007", "Sunday", 14),
    # Months.
    ("N32_008", "January", 14),
    ("N32_009", "February", 14),
    ("N32_010", "March", 14),
    ("N32_011", "April", 14),
    ("N32_012", "May", 14),
    ("N32_013", "June", 14),
    ("N32_014", "July", 14),
    ("N32_015", "August", 14),
    ("N32_016", "September", 14),
    ("N32_017", "October", 14),
    ("N32_018", "November", 14),
    ("N32_019", "December", 14),
    # The one chemical_compound lemma still unassigned; joins the elements.
    ("N15_003", "lithium", 54),
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Make the live API calls. Without this flag, only print the plan.",
    )
    return parser.parse_args()


def _print_plan() -> None:
    print(f"Barsukas: {BASE_URL}")
    print(f"Lemmas to re-level: {len(MOVES)}")
    for guid, lemma_text, level in MOVES:
        print(f"  {guid}  {lemma_text:12} -> level {level}")


def _verify(guid: str, expected_text: str) -> str:
    """Confirm ``guid`` still names ``expected_text``; return its current level."""
    response = get_lemma(guid)
    data = response.get("data") if isinstance(response, dict) else None
    if not isinstance(data, dict):
        raise RuntimeError(f"{guid}: lookup returned no data: {response!r}")
    actual_text = data.get("lemma_text")
    if actual_text != expected_text:
        raise RuntimeError(
            f"{guid}: expected {expected_text!r} but the database has {actual_text!r}; "
            "the GUID has been reassigned, so this script is out of date"
        )
    return str(data.get("difficulty_level"))


def _execute() -> None:
    changed = 0
    unchanged = 0
    for guid, lemma_text, level in MOVES:
        current = _verify(guid, lemma_text)
        if current == str(level):
            print(f"  {guid} {lemma_text}: already level {level}, skipping")
            unchanged += 1
            continue
        patch_lemma_difficulty(guid, level)
        print(f"  {guid} {lemma_text}: {current} -> {level}")
        changed += 1
    print(f"Complete: {changed} re-leveled, {unchanged} already correct.")


def main() -> int:
    args = _parse_args()
    _print_plan()
    if not args.execute:
        print("\nNo API calls made. Re-run with --execute only after approval.")
        return 0

    try:
        _execute()
    except (BarsukasAPIError, RuntimeError) as error:
        print(f"Re-level stopped: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
