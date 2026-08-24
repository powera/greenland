"""Plain-text handling for Project Gutenberg books.

Two jobs live here, both purely mechanical (no network, no database):

* :func:`strip_gutenberg_boilerplate` removes the licence header/footer and the
  transcription apparatus, so only the book's own prose is counted.
* :func:`analyze_text` tokenizes what is left and records, per word, how often
  it appears capitalized *away from a sentence boundary*.  That capitalization
  signal is what :mod:`wordfreq.corpora.frequency_build` uses to tell proper
  nouns apart from ordinary vocabulary.
"""

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from typing import Dict, Iterator, List, Optional, Tuple

# --- Header / footer markers -------------------------------------------------

# Modern files: "*** START OF THE PROJECT GUTENBERG EBOOK FRANKENSTEIN ***"
# Older files also use "THIS PROJECT GUTENBERG EBOOK" and omit the spaces.
START_MARKER_RE = re.compile(
    r"^[^\n]*\*\*\*\s*START OF (?:THE|THIS) PROJECT GUTENBERG EBOOK[^\n]*$",
    re.IGNORECASE | re.MULTILINE,
)
END_MARKER_RE = re.compile(
    r"^[^\n]*\*\*\*\s*END OF (?:THE|THIS) PROJECT GUTENBERG EBOOK[^\n]*$",
    re.IGNORECASE | re.MULTILINE,
)

# Pre-2006 files wrap the header in the "small print" licence instead.
SMALL_PRINT_END_RE = re.compile(
    r"^[^\n]*\*END\*\s*THE SMALL PRINT[^\n]*$", re.IGNORECASE | re.MULTILINE
)
# ... and close with a plain sentence rather than a marker line.
PLAIN_END_RE = re.compile(
    r"^[^\n]*End of (?:the )?(?:Project Gutenberg|Project Gutenberg's|The Project Gutenberg)"
    r"[^\n]*$",
    re.IGNORECASE | re.MULTILINE,
)

# "Title: Pride and Prejudice" in the Gutenberg header block.
TITLE_HEADER_RE = re.compile(r"^Title:\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE)

# Transcription apparatus that sits inside the marked-off body.
PRODUCER_PARAGRAPH_RE = re.compile(
    r"^\s*(?:produced by|e-?text (?:prepared|produced) by|transcribed from|"
    r"this e?text was prepared|prepared by|proofreading team|updated editions|"
    r"scanned (?:and proofed )?by)\b",
    re.IGNORECASE,
)
BRACKETED_APPARATUS_RE = re.compile(
    r"\[\s*(?:illustration|transcriber(?:'s|s')?\s+notes?|footnote|note)\b[^\[\]]*\]",
    re.IGNORECASE | re.DOTALL,
)
TRANSCRIBER_NOTE_HEADING_RE = re.compile(r"^\s*transcriber(?:'s|s')?\s+notes?\b", re.IGNORECASE)

# How many leading/trailing paragraphs may be dropped as transcription notes.
MAX_APPARATUS_PARAGRAPHS = 4

# --- Tokenization ------------------------------------------------------------

# A raw token may contain digits; those are dropped afterwards, so that "1st"
# disappears entirely instead of contributing a bogus "st".
RAW_TOKEN_RE = re.compile(r"[A-Za-z0-9]+(?:['’][A-Za-z0-9]+)*")
CONTAINS_DIGIT_RE = re.compile(r"[0-9]")

# Single letters that are real English words; every other one-letter token is
# scanning noise or a list marker.
VALID_SINGLE_LETTERS = frozenset({"a", "i", "o"})

# Characters skipped when looking backwards for a sentence boundary.
_OPENING_PUNCTUATION = "\"'‘’“”([{*_"
_SENTENCE_ENDERS = ".!?"


def _normalize(text: str) -> str:
    """Normalize encoding artifacts that would otherwise split tokens."""
    text = text.replace("﻿", "")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = unicodedata.normalize("NFC", text)
    return text


def extract_title(text: str) -> Optional[str]:
    """Return the ``Title:`` line from a Gutenberg header, if present."""
    match = TITLE_HEADER_RE.search(text[:20000])
    if match is None:
        return None
    return " ".join(match.group(1).split())


def _find_body_bounds(text: str) -> Tuple[int, int]:
    """Return ``(start, end)`` offsets of the book body within a Gutenberg file."""
    start = 0
    start_match = START_MARKER_RE.search(text)
    if start_match is not None:
        start = start_match.end()
    else:
        small_print = SMALL_PRINT_END_RE.search(text)
        if small_print is not None:
            start = small_print.end()

    end = len(text)
    end_match = None
    for end_match in END_MARKER_RE.finditer(text):
        pass
    if end_match is None:
        for end_match in PLAIN_END_RE.finditer(text):
            pass
    if end_match is not None and end_match.start() > start:
        end = end_match.start()

    return start, end


def _strip_apparatus_paragraphs(paragraphs: List[str]) -> List[str]:
    """Drop leading/trailing producer and transcriber-note paragraphs."""
    head = 0
    while head < len(paragraphs) and head < MAX_APPARATUS_PARAGRAPHS:
        paragraph = paragraphs[head]
        if PRODUCER_PARAGRAPH_RE.match(paragraph) or TRANSCRIBER_NOTE_HEADING_RE.match(paragraph):
            head += 1
            continue
        break

    tail = len(paragraphs)
    while tail > head and tail > len(paragraphs) - MAX_APPARATUS_PARAGRAPHS:
        paragraph = paragraphs[tail - 1]
        if PRODUCER_PARAGRAPH_RE.match(paragraph) or TRANSCRIBER_NOTE_HEADING_RE.match(paragraph):
            tail -= 1
            continue
        break

    return paragraphs[head:tail]


def strip_gutenberg_boilerplate(text: str) -> str:
    """Return just the book text from a Project Gutenberg plain-text file.

    Removes the licence header and footer, the "Produced by ..." credits and
    bracketed transcription apparatus (``[Illustration: ...]``,
    ``[Transcriber's Note: ...]``).  A file with no recognizable markers is
    returned normalized but otherwise untouched, so an unexpected layout costs
    accuracy rather than the whole book.

    Args:
        text: Raw contents of a Gutenberg ``.txt`` file.

    Returns:
        The book body, with boilerplate removed.
    """
    text = _normalize(text)
    start, end = _find_body_bounds(text)
    body = text[start:end]
    body = BRACKETED_APPARATUS_RE.sub(" ", body)

    paragraphs = re.split(r"\n\s*\n", body)
    paragraphs = [paragraph.strip() for paragraph in paragraphs]
    paragraphs = [paragraph for paragraph in paragraphs if paragraph]
    paragraphs = _strip_apparatus_paragraphs(paragraphs)

    return "\n\n".join(paragraphs)


def _is_sentence_initial(text: str, index: int) -> bool:
    """Whether the token starting at ``index`` opens a sentence or a line.

    Line starts count as sentence starts: verse, chapter headings and list
    items capitalize their first word for reasons that say nothing about
    whether the word is a proper noun.
    """
    position = index - 1
    while position >= 0:
        char = text[position]
        if char == "\n":
            return True
        if char.isspace() or char in _OPENING_PUNCTUATION:
            position -= 1
            continue
        return char in _SENTENCE_ENDERS
    return True


def iter_tokens(text: str) -> Iterator[Tuple[str, bool, bool]]:
    """Yield ``(lowercase_token, is_capitalized, is_sentence_initial)`` triples.

    Tokens containing digits, and single letters other than ``a``/``i``/``o``,
    are skipped entirely.
    """
    for match in RAW_TOKEN_RE.finditer(text):
        raw = match.group(0)
        if CONTAINS_DIGIT_RE.search(raw):
            continue
        lowered = raw.lower().replace("’", "'")
        if len(lowered) == 1 and lowered not in VALID_SINGLE_LETTERS:
            continue
        if lowered.startswith("'") or lowered.endswith("'"):
            lowered = lowered.strip("'")
            if not lowered:
                continue
        yield lowered, raw[0].isupper(), _is_sentence_initial(text, match.start())


@dataclass
class TextStats:
    """Token counts for one text, with the capitalization evidence per word.

    Attributes:
        token_total: Total number of tokens counted.
        counts: Occurrences of each lowercased word.
        mid_sentence_total: Occurrences away from a sentence/line start.
        mid_sentence_capitalized: Of those, how many were capitalized.
    """

    token_total: int = 0
    counts: Counter[str] = field(default_factory=Counter)
    mid_sentence_total: Counter[str] = field(default_factory=Counter)
    mid_sentence_capitalized: Counter[str] = field(default_factory=Counter)

    def capitalization_ratio(self, word: str) -> Optional[float]:
        """Share of mid-sentence occurrences that were capitalized.

        Returns ``None`` when the word never appears mid-sentence, which is the
        case for verse and headings and means the evidence is unusable.
        """
        total = self.mid_sentence_total[word]
        if total == 0:
            return None
        return self.mid_sentence_capitalized[word] / total


def analyze_text(text: str) -> TextStats:
    """Tokenize ``text`` and collect per-word counts and capitalization stats."""
    stats = TextStats()
    for token, is_capitalized, is_sentence_initial in iter_tokens(text):
        stats.token_total += 1
        stats.counts[token] += 1
        if not is_sentence_initial:
            stats.mid_sentence_total[token] += 1
            if is_capitalized:
                stats.mid_sentence_capitalized[token] += 1
    return stats


def slugify_title(gutenberg_id: int, title: str, max_length: int = 90) -> str:
    """Build the ``<id>_<Title>`` key used in the corpus JSON files.

    Matches the existing corpus files, where each non-alphanumeric character
    becomes a single underscore (``Frankenstein; Or, The Modern Prometheus``
    becomes ``Frankenstein__Or__The_Modern_Prometheus``).
    """
    sanitized = "".join(char if char.isalnum() else "_" for char in title)
    slug = f"{gutenberg_id}_{sanitized}"[:max_length]
    return slug.rstrip("_")


def summarize_stats(stats: TextStats) -> Dict[str, int]:
    """Small dict of headline numbers, for logging and reports."""
    return {
        "tokens": stats.token_total,
        "unique_words": len(stats.counts),
    }
