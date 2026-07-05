"""Story-library agents (the "ožys" family).

Ožys ("billy goat" in Lithuanian -- a nod to The Three Billy Goats Gruff, the
story that motivated the text-works library) generates the texts of *authored*
works: retellings of traditional stories and original constructed
conversations. It never touches canonical-type works (poems, songs, ...),
whose texts are transcribed, not generated.
"""

from agents.ozys.ozys import OzysAgent

__all__ = ["OzysAgent"]
