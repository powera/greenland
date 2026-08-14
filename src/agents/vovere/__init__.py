"""Concept agents (the "vovere" family).

This package groups the concept-oriented agents that share the Wikidata seed ->
Vovere body -> concept-creation pipeline:

* :mod:`agents.vovere.vovere` -- ``VovereAgent``, the concept *generator*.
* :mod:`agents.vovere.voverukas` -- the red-link *ranker* (discovers topics).
* :mod:`agents.vovere.voveraite` -- creates concepts from explicit Q-ids.

These modules are command lines: ranking lives in :mod:`concepts.discovery`,
Q-id intake in :mod:`concepts.seed.qids`, and batch submission/completion in
:mod:`concepts.generate.batch`.

``VovereAgent`` and ``html_to_text`` are re-exported here so existing
``from agents.vovere import VovereAgent`` imports keep working after the move
from ``agents/vovere.py`` to this package.
"""

from concepts.generate.entry import VovereAgent, html_to_text

__all__ = ["VovereAgent", "html_to_text"]
