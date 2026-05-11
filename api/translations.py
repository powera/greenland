"""HTTP facade for translation endpoints.

Translations are currently a lemma sub-resource in the Barsukas API, so this
module re-exports :func:`api.lemmas.get_translations` and exists as the
natural home for future standalone translation endpoints.

Mirrors ``src/barsukas/routes/api/v1.py``. Any change to a route signature or
response shape there must be reflected here in the same commit.
"""

from __future__ import annotations

from api.lemmas import get_translations

__all__ = ["get_translations"]
