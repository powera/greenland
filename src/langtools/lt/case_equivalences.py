"""Lithuanian case name aliases for grammatical form normalization.

Loaded dynamically by langtools.form_equivalences; intentionally has no imports
so it can be read without executing langtools/lt/__init__.py.
"""

# Maps alternative/alias case names to the canonical names used in this system.
# The Lithuanian locative (vietininkas) is the same case that cross-linguistic
# typology — and LLMs familiar with Finnish/Estonian/Hungarian — call "inessive".
CASE_ALIASES = {"inessive": "locative"}
