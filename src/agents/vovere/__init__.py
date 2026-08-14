"""Concept agents (the "vovere" family).

This package groups the concept-oriented agents that share the Wikidata seed ->
Vovere body -> concept-creation pipeline:

* :mod:`agents.vovere.vovere` -- ``VovereAgent``, the concept *generator*.
* :mod:`agents.vovere.voverukas` -- the red-link *ranker* (discovers topics).
* :mod:`agents.vovere.voveraite` -- creates concepts from explicit Q-ids.

``VovereAgent`` and ``html_to_text`` are re-exported here so existing
``from agents.vovere import VovereAgent`` imports keep working after the move
from ``agents/vovere.py`` to this package.
"""

from concepts.generate.entry import VovereAgent, html_to_text

__all__ = ["VovereAgent", "html_to_text"]
