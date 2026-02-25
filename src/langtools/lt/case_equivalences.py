"""Equivalences between Lithuanian case names and alternative linguistic terminology.

Lithuanian has 7 traditional cases (nominative, genitive, dative, accusative,
instrumental, locative, vocative).  In cross-linguistic typology some of these
are referred to by different names:

- The **locative** (vietininkas) expresses location ("in/at something") and is
  functionally equivalent to what many typologists call the *inessive* case
  (as found in Finnish, Estonian, and Hungarian).  An LLM familiar with those
  languages may label this form as "inessive" rather than "locative".
"""

from typing import Dict

# Maps alternative/alias case names to the canonical names used in this system.
LT_CASE_ALIASES: Dict[str, str] = {
    "inessive": "locative",  # Lithuanian locative = cross-linguistic inessive
}
