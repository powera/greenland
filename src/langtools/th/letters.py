"""Thai dictionary letter bar: 44 consonants in canonical alphabet order.

Thai has no case distinction; ``get_letters("th", uppercase=False)`` returns
the same list. Vowels are not given separate buckets — Thai dictionary
ordering keys on the consonant.
"""

from typing import List

LETTERS_UPPER: List[str] = list("กขฃคฅฆงจฉชซฌญฎฏฐฑฒณดตถทธนบปผฝพฟภมยรลวศษสหฬอฮ")
