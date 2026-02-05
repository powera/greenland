#!/usr/bin/env python3
"""
Gojūon (五十音) ordering tables for Japanese.

Provides all 46 gojūon kana used for dictionary alphabet bars, and
mappings between voiced/semi-voiced kana and their base (unvoiced) kana.
"""

from typing import Dict, List

# All 46 gojūon kana in standard dictionary order.
ROW_INITIALS: List[str] = list(
    "あいうえお"
    "かきくけこ"
    "さしすせそ"
    "たちつてと"
    "なにぬねの"
    "はひふへほ"
    "まみむめも"
    "やゆよ"
    "らりるれろ"
    "わをん"
)

# Each kana maps to itself plus its voiced (dakuten) and semi-voiced
# (handakuten) variants, used for filtering sort_key values.
ROW_MEMBERS: Dict[str, List[str]] = {
    "あ": ["あ"],
    "い": ["い"],
    "う": ["う"],
    "え": ["え"],
    "お": ["お"],
    "か": ["か", "が"],
    "き": ["き", "ぎ"],
    "く": ["く", "ぐ"],
    "け": ["け", "げ"],
    "こ": ["こ", "ご"],
    "さ": ["さ", "ざ"],
    "し": ["し", "じ"],
    "す": ["す", "ず"],
    "せ": ["せ", "ぜ"],
    "そ": ["そ", "ぞ"],
    "た": ["た", "だ"],
    "ち": ["ち", "ぢ"],
    "つ": ["つ", "づ"],
    "て": ["て", "で"],
    "と": ["と", "ど"],
    "な": ["な"],
    "に": ["に"],
    "ぬ": ["ぬ"],
    "ね": ["ね"],
    "の": ["の"],
    "は": ["は", "ば", "ぱ"],
    "ひ": ["ひ", "び", "ぴ"],
    "ふ": ["ふ", "ぶ", "ぷ"],
    "へ": ["へ", "べ", "ぺ"],
    "ほ": ["ほ", "ぼ", "ぽ"],
    "ま": ["ま"],
    "み": ["み"],
    "む": ["む"],
    "め": ["め"],
    "も": ["も"],
    "や": ["や"],
    "ゆ": ["ゆ"],
    "よ": ["よ"],
    "ら": ["ら"],
    "り": ["り"],
    "る": ["る"],
    "れ": ["れ"],
    "ろ": ["ろ"],
    "わ": ["わ"],
    "を": ["を"],
    "ん": ["ん"],
}

# Reverse map: any kana → the row initial it belongs to.
# Unvoiced kana map to themselves if they are a row initial, or to their
# row's initial.  Voiced/semi-voiced map to their unvoiced row initial.
KANA_TO_ROW: Dict[str, str] = {}
for _row, _members in ROW_MEMBERS.items():
    for _ch in _members:
        KANA_TO_ROW[_ch] = _row
