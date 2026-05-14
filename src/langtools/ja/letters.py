"""Japanese dictionary letter bar: gojūon (五十音) row initials.

Re-exports ``ROW_INITIALS`` from ``gojuon`` so dispatcher callers can reach
the canonical 10-row initial set via ``get_letters("ja")``.
"""

from typing import List

from langtools.ja.gojuon import ROW_INITIALS

LETTERS_UPPER: List[str] = list(ROW_INITIALS)
