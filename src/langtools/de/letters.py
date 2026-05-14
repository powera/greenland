"""German alphabet: standard A–Z plus the umlauts Ä Ö Ü.

ß is not included as a separate letter bucket here (it sorts as ``ss``
under standard German collation) — words beginning with ß are essentially
nonexistent.
"""

from typing import List

LETTERS_UPPER: List[str] = list("ABCDEFGHIJKLMNOPQRSTUVWXYZ") + ["Ä", "Ö", "Ü"]
