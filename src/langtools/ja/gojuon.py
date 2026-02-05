#!/usr/bin/env python3
"""
Gojūon (五十音) ordering tables for Japanese.

Provides the 10 row-initial kana used for dictionary alphabet bars, and
mappings between voiced/semi-voiced kana and their base (unvoiced) row.
"""

from typing import Dict, List

# The 10 gojūon row initials, in standard dictionary order.
ROW_INITIALS: List[str] = list("あかさたなはまやらわ")

# Each row initial maps to the full set of kana that belong to that row,
# including voiced (dakuten) and semi-voiced (handakuten) variants.
ROW_MEMBERS: Dict[str, List[str]] = {
    "あ": list("あいうえお"),
    "か": list("かきくけこがぎぐげご"),
    "さ": list("さしすせそざじずぜぞ"),
    "た": list("たちつてとだぢづでど"),
    "な": list("なにぬねの"),
    "は": list("はひふへほばびぶべぼぱぴぷぺぽ"),
    "ま": list("まみむめも"),
    "や": list("やゆよ"),
    "ら": list("らりるれろ"),
    "わ": list("わをん"),
}

# Reverse map: any kana → the row initial it belongs to.
# Unvoiced kana map to themselves if they are a row initial, or to their
# row's initial.  Voiced/semi-voiced map to their unvoiced row initial.
KANA_TO_ROW: Dict[str, str] = {}
for _row, _members in ROW_MEMBERS.items():
    for _ch in _members:
        KANA_TO_ROW[_ch] = _row
