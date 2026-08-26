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
from typing import Dict, Iterable, Iterator, List, Optional, Tuple

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

# Apostrophe variants, all folded to ASCII "'" before tokenizing.  Books are
# individually consistent but differ from each other, so without this the same
# contraction is two different words across the corpus: a book typeset with
# U+2019 contributes to "don’t" and one with ASCII to "don't", and --min-books
# can then drop both for appearing in too few books.  U+02BC is a modifier
# letter rather than punctuation, so it would split "donʼt" into "don" + "t".
APOSTROPHE_VARIANTS = "’‘ʼ՚′´‛"
_APOSTROPHE_RE = re.compile(f"[{APOSTROPHE_VARIANTS}]")

# Dash variants that separate words: em, en, horizontal bar, figure dash, minus,
# and the "--" that older files use for an em dash.  A plain hyphen is NOT here:
# it joins a genuine compound ("well-known"), which the token regex then splits
# into its parts, and that is the existing behaviour.
DASH_VARIANTS = "—–―‒−"
_DASH_RE = re.compile(f"[{DASH_VARIANTS}]|--+")

# A raw token may contain digits; those are dropped afterwards, so that "1st"
# disappears entirely instead of contributing a bogus "st".
RAW_TOKEN_RE = re.compile(r"[A-Za-z0-9]+(?:'[A-Za-z0-9]+)*")
CONTAINS_DIGIT_RE = re.compile(r"[0-9]")

# Single letters that are real English words; every other one-letter token is
# scanning noise or a list marker.
VALID_SINGLE_LETTERS = frozenset({"a", "i", "o"})

# Characters skipped when looking backwards for a sentence boundary.
_OPENING_PUNCTUATION = "\"'‘’“”([{*_"
_SENTENCE_ENDERS = ".!?"


def _normalize(text: str) -> str:
    """Normalize encoding artifacts that would otherwise split or double tokens."""
    text = text.replace("﻿", "")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = unicodedata.normalize("NFC", text)
    # Fold typographic apostrophes so a contraction is one word corpus-wide.
    text = _APOSTROPHE_RE.sub("'", text)
    # Dashes separate words rather than joining them: "cat—the" is two words,
    # and an unspaced em dash is the ordinary 19th-century typesetting.  The
    # token regex already stops at them, but a dash flanked by letters must not
    # be mistaken for a hyphenated compound, so make the break explicit.
    text = _DASH_RE.sub(" ", text)
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


def build_phrase_index(phrases: Iterable[str]) -> Dict[str, int]:
    """Index multi-word phrases by their first word, for :func:`iter_tokens`.

    Returns ``{lowercased phrase: word count}`` for every phrase of two or more
    words. Single words are dropped: they need no joining, and keeping them
    would make the lookup claim matches it does not perform.
    """
    index: Dict[str, int] = {}
    for phrase in phrases:
        parts = phrase.lower().split()
        if len(parts) < 2:
            continue
        index[" ".join(parts)] = len(parts)
    return index


def iter_tokens(
    text: str,
    phrases: Optional[Dict[str, int]] = None,
) -> Iterator[Tuple[str, bool, bool]]:
    """Yield ``(lowercase_token, is_capitalized, is_sentence_initial)`` triples.

    Tokens containing digits, and single letters other than ``a``/``i``/``o``,
    are skipped entirely.

    The text is normalized first, so apostrophe and dash variants are folded
    whether or not the caller came through
    :func:`strip_gutenberg_boilerplate`.

    When ``phrases`` is given (from :func:`build_phrase_index`), a run of words
    matching a known phrase is emitted as **one** token: "ice cream" counts as
    itself rather than as "ice" plus "cream", and "New York" is one name rather
    than two words that are separately common. The longest match at a position
    wins, and the words it consumes are not emitted again -- a phrase's count
    is therefore taken out of its parts' counts, which is the point: "ice
    cream" should not also inflate "cream".

    A phrase's capitalization and sentence position are those of its first
    word, so "New York" mid-sentence reads as capitalized evidence for the
    whole phrase, exactly as a single-word name would.
    """
    text = _normalize(text)

    # Materialize the token stream first: a phrase match needs to look ahead,
    # which a bare finditer loop cannot do.
    collected: List[Tuple[str, bool, bool]] = []
    for match in RAW_TOKEN_RE.finditer(text):
        raw = match.group(0)
        if CONTAINS_DIGIT_RE.search(raw):
            continue
        lowered = raw.lower()
        if len(lowered) == 1 and lowered not in VALID_SINGLE_LETTERS:
            continue
        if lowered.startswith("'") or lowered.endswith("'"):
            lowered = lowered.strip("'")
            if not lowered:
                continue
        collected.append((lowered, raw[0].isupper(), _is_sentence_initial(text, match.start())))

    if not phrases:
        yield from collected
        return

    longest = max(phrases.values())
    position = 0
    total = len(collected)
    while position < total:
        matched_length = 0
        # Prefer the longest phrase starting here, so "New York" wins over a
        # hypothetical "New" and a longer name wins over a shorter prefix.
        for length in range(min(longest, total - position), 1, -1):
            candidate = " ".join(
                collected[index][0] for index in range(position, position + length)
            )
            if phrases.get(candidate) == length:
                matched_length = length
                break

        if matched_length:
            joined = " ".join(
                collected[index][0] for index in range(position, position + matched_length)
            )
            _, is_capitalized, is_sentence_initial = collected[position]
            yield joined, is_capitalized, is_sentence_initial
            position += matched_length
            continue

        yield collected[position]
        position += 1


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


def analyze_text(text: str, phrases: Optional[Dict[str, int]] = None) -> TextStats:
    """Tokenize ``text`` and collect per-word counts and capitalization stats.

    ``phrases`` (from :func:`build_phrase_index`) makes known multi-word forms
    count as single tokens; see :func:`iter_tokens`.
    """
    stats = TextStats()
    for token, is_capitalized, is_sentence_initial in iter_tokens(text, phrases):
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
