"""HTTP facade for audio endpoints.

Lemma audio availability is currently a sub-resource of ``/api/v1/lemma/<guid>``
in the Barsukas API, so this module re-exports :func:`api.lemmas.get_audio`
and exists as the natural home for future standalone audio endpoints.

Mirrors ``src/barsukas/routes/api.py``. Any change to a route signature or
response shape there must be reflected here in the same commit.
"""

from __future__ import annotations

from api.lemmas import get_audio

__all__ = ["get_audio"]
