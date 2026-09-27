"""Plain-text handling for European Parliament debates from the Europarl corpus.

The counterpart of :mod:`wordfreq.corpora.scotus_text` for the Europarl source
release.  Everything here is mechanical (no network, no database).

A session file is plain text with line-level markup::

    <CHAPTER ID="1">
    Resumption of the session
    <SPEAKER ID="1" NAME="President">
    I declare resumed the session of the European Parliament ...
    <P>
    ...
    <SPEAKER ID="2" LANGUAGE="EN" NAME="Evans, Robert J">
    Mr President, I welcome ...

Attribute values are quoted in some years and bare in others.  ``LANGUAGE`` is
the language the speaker actually spoke, and in the English files it marks a
speech translated into English.  It cannot identify the speeches given in
English: an untagged speech may be one, or may simply be untagged -- 91% of
2007's speeches carry no tag, and 2005's empty tags sit on Spanish members.
A native-English filter would need a second language's files, where the
English originals are the tagged ones.

Structure changed twice over the release: 1996-2001 files hold one sitting day
with a ``CHAPTER`` per agenda item; 2002 to mid-2006 files hold a day in a
single ``CHAPTER``, split here at the chair's announcements (see
:func:`split_agenda_items`); later files hold one agenda item each.

The unit of analysis is the **chapter**: one agenda item, several speakers
debating one subject, typically a few thousand words.  It plays the part a
SCOTUS opinion plays there -- long enough to count, short enough that the
per-document mean stops one marathon debate deciding a word's rank.

What is removed before counting:

* the chair's speeches (``NAME="President"``), which are procedure -- "The
  debate is closed", "The vote will take place tomorrow at 12 noon" -- and
  would repeat across every chapter;
* stage directions, whole-line (``(The sitting was closed at 11.50 a.m.)``)
  and inline (``(Applause)``);
* the ``(FR)`` marker later sessions put before an interpreted speech;
* the vocatives a speech opens with (``Mr President, Commissioner, ladies and
  gentlemen,``), which are a form of address rather than the speech's content.

Procedural chapters (minutes, agenda, voting time, ...) are recognized by title
so the selector can skip them; see :func:`is_procedural_title`.
"""

import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Collection, Dict, Iterator, List, Optional, Tuple

# --- Markup ------------------------------------------------------------------

_TAG_RE = re.compile(r"^\s*<\s*(CHAPTER|SPEAKER|P)\b([^>]*)>\s*$", re.IGNORECASE)
_ATTR_RE = re.compile(r'(\w+)\s*=\s*(?:"([^"]*)"|\'([^\']*)\'|([^\s>]+))')

# "ep-00-01-17" or, from 2007 on, "ep-07-01-15-003" (one file per chapter).
_SESSION_RE = re.compile(r"^ep-(\d{2})-(\d{2})-(\d{2})(?:-\d+)?$")


def parse_attributes(raw: str) -> Dict[str, str]:
    """Parse ``ID="1" NAME="Evans, Robert J"`` into an upper-cased-key dict."""
    attributes: Dict[str, str] = {}
    for match in _ATTR_RE.finditer(raw):
        value = next((group for group in match.groups()[1:] if group is not None), "")
        attributes[match.group(1).upper()] = value.strip()
    return attributes


def session_year(session: str) -> Optional[int]:
    """Calendar year of a session file stem, e.g. ``ep-00-01-17`` -> 2000.

    Europarl starts in 1996, so a two-digit year of 96-99 is the 1990s.
    """
    match = _SESSION_RE.match(session)
    if not match:
        return None
    short = int(match.group(1))
    return 1900 + short if short >= 90 else 2000 + short


# --- Cleaning ----------------------------------------------------------------

# A line that is nothing but a parenthetical: "(Applause)", "(The sitting was
# suspended at 12.10 p.m.)", "(Parliament approved the Minutes)".
_STAGE_LINE_RE = re.compile(r"^\s*\([^()]*\)\s*\.?\s*$")

# Reactions interjected into running text.  A closed list, because other
# parentheses in a speech are ordinary prose ("the directive (as amended)").
_INLINE_STAGE_RE = re.compile(
    r"\(\s*(?:applause|laughter|interruption|interjection|mixed reactions|protests?|"
    r"heckling|loud applause|sustained applause|cries? of|murmurs?|uproar|"
    r"the president cut off|the speaker)[^()]*\)",
    re.IGNORECASE,
)

# "(FR) Mr President, ..." -- the source language of an interpreted speech.
_LANGUAGE_MARKER_RE = re.compile(r"^\s*\([A-Z]{2}\)\s*")

# One vocative a speech may open with, consumed repeatedly so "Mr President,
# Commissioner, ladies and gentlemen," goes as a whole.
_VOCATIVE_RE = re.compile(
    r"""^\s*(?:and\s+)?(?:
        (?:Mr|Mrs|Madam|Ms)\.?\s+
          (?:President|Vice-President|Commissioner|Chairman|Rapporteur|Minister)
          (?:-in-Office)?(?:\s+of\s+the\s+(?:Council|Commission))?
      | (?:the\s+)?President(?:-in-Office)?(?:\s+of\s+the\s+(?:Council|Commission))?
      | Commissioners?
      | [Ll]adies\s+and\s+gentlemen
      | (?:[Hh]onourable\s+)?(?:Members|[Cc]olleagues|[Ff]riends)
    )\s*[,.!:;]\s*""",
    re.VERBOSE,
)

# "President", "President." and, in 2004-2006, "President. –".
_CHAIR_NAME_RE = re.compile(r"^\s*(?:the\s+)?(?:vice[-\s]?)?president[\s.:–—-]*$", re.IGNORECASE)

_WHITESPACE_RE = re.compile(r"[ \t]+")

# Files before about 2001 print a possessive with a stray space ("a minute' s
# silence"), which would tokenize as "minute" plus a bare "s".
_SPACED_POSSESSIVE_RE = re.compile(r"(\w)' s\b")

# "Amendment No 10", "Regulation (EC) No 1234/2006", "Amendments Nos 4, 9 and
# 15": the abbreviation for "number", which would otherwise count as the word
# "no".  Only before a numeral, so "No, we disagree" is untouched.
_NUMBER_ABBREVIATION_RE = re.compile(r"\bNos?\.?(?=\s*\d)")


def is_chair(name: str) -> bool:
    """True when a speaker name is the sitting's chair rather than a person.

    Only the bare title counts: "President-in-Office of the Council" is a
    government minister speaking on substance and is kept.
    """
    return bool(_CHAIR_NAME_RE.match(name))


def strip_vocatives(text: str) -> str:
    """Remove the forms of address a speech opens with."""
    previous = None
    while previous != text:
        previous = text
        text = _VOCATIVE_RE.sub("", text, count=1)
    return text


def clean_paragraph(text: str) -> str:
    """Strip stage directions and language markers from one paragraph."""
    if _STAGE_LINE_RE.match(text):
        return ""
    text = _LANGUAGE_MARKER_RE.sub("", text)
    text = _INLINE_STAGE_RE.sub(" ", text)
    text = _SPACED_POSSESSIVE_RE.sub(r"\1's", text)
    text = _NUMBER_ABBREVIATION_RE.sub(" ", text)
    return _WHITESPACE_RE.sub(" ", text).strip()


# --- Structure ---------------------------------------------------------------


@dataclass(frozen=True)
class Speech:
    """One speaker's contribution to a chapter.

    Attributes:
        speaker: The ``NAME`` attribute ("" when absent).
        language: The ``LANGUAGE`` attribute, upper-cased, or ``None`` when the
            file does not record which language was spoken.
        paragraphs: The speech's paragraphs, uncleaned.
    """

    speaker: str
    language: Optional[str]
    paragraphs: Tuple[str, ...]

    @property
    def is_chair(self) -> bool:
        return is_chair(self.speaker)

    def text(self) -> str:
        """The speech as running prose, stage directions and vocatives removed."""
        cleaned = [clean_paragraph(paragraph) for paragraph in self.paragraphs]
        kept = [paragraph for paragraph in cleaned if paragraph]
        if kept:
            kept[0] = strip_vocatives(kept[0])
        return "\n".join(paragraph for paragraph in kept if paragraph)


@dataclass(frozen=True)
class Chapter:
    """One agenda item of one sitting.

    Attributes:
        session: The session file stem, e.g. ``ep-00-01-17``.
        chapter_id: The ``CHAPTER`` tag's ``ID``.
        title: The agenda item's title (the text before its first speaker).
        speeches: Every speech in the chapter, the chair's included.
    """

    session: str
    chapter_id: str
    title: str
    speeches: Tuple[Speech, ...]

    @property
    def slug(self) -> str:
        """Key for this chapter in the selection list and the corpus JSON."""
        return chapter_slug(self.session, self.chapter_id)

    @property
    def year(self) -> Optional[int]:
        return session_year(self.session)

    def text(
        self,
        *,
        languages: Optional[Collection[str]] = None,
        include_chair: bool = False,
    ) -> str:
        """The chapter's debate as running prose.

        Args:
            languages: Keep only speeches recorded as spoken in one of these
                (upper-case codes, e.g. ``{"EN"}``).  A speech with no recorded
                language is dropped by any filter.  ``None`` keeps every speech.
            include_chair: Keep the chair's procedural speeches.
        """
        wanted = {code.upper() for code in languages} if languages is not None else None
        parts: List[str] = []
        for speech in self.speeches:
            if speech.is_chair and not include_chair:
                continue
            if wanted is not None and speech.language not in wanted:
                continue
            body = speech.text()
            if body:
                parts.append(body)
        return "\n\n".join(parts)


def chapter_slug(session: str, chapter_id: str) -> str:
    """``ep-00-01-17`` + ``3`` -> ``ep-00-01-17_ch3``."""
    return f"{session}_ch{chapter_id}"


def split_slug(slug: str) -> Tuple[str, str]:
    """Inverse of :func:`chapter_slug`: ``(session, chapter_id)``."""
    session, _, chapter_id = slug.rpartition("_ch")
    if not session:
        raise ValueError(f"not a chapter slug: {slug!r}")
    return session, chapter_id


def parse_session(text: str, session: str) -> List[Chapter]:
    """Split one session file into its chapters.

    Text before the first ``CHAPTER`` tag is ignored.  A ``SPEAKER`` with no
    ``CHAPTER`` above it is kept under a synthetic chapter ``0`` rather than
    dropped, so a malformed file loses its title but not its debate.
    """
    chapters: List[Chapter] = []
    chapter_id: Optional[str] = None
    title_lines: List[str] = []
    speeches: List[Speech] = []
    speaker: Optional[Tuple[str, Optional[str]]] = None
    paragraphs: List[str] = []
    paragraph: List[str] = []

    def close_paragraph() -> None:
        if paragraph:
            paragraphs.append(" ".join(paragraph))
            paragraph.clear()

    def close_speech() -> None:
        nonlocal speaker
        close_paragraph()
        if speaker is not None and paragraphs:
            speeches.append(Speech(speaker[0], speaker[1], tuple(paragraphs)))
        paragraphs.clear()
        speaker = None

    def close_chapter() -> None:
        close_speech()
        if chapter_id is not None and speeches:
            chapters.append(Chapter(session, chapter_id, " ".join(title_lines), tuple(speeches)))
        title_lines.clear()
        speeches.clear()

    for line in text.splitlines():
        tag = _TAG_RE.match(line)
        if tag:
            kind = tag.group(1).upper()
            attributes = parse_attributes(tag.group(2))
            if kind == "CHAPTER":
                close_chapter()
                chapter_id = attributes.get("ID", str(len(chapters) + 1))
            elif kind == "SPEAKER":
                close_speech()
                if chapter_id is None:
                    chapter_id = "0"
                language = attributes.get("LANGUAGE") or None
                speaker = (attributes.get("NAME", ""), language.upper() if language else None)
            else:
                close_paragraph()
            continue

        stripped = line.strip()
        if not stripped or chapter_id is None:
            continue
        if speaker is None:
            title_lines.append(stripped)
        elif _STAGE_LINE_RE.match(stripped):
            # Judged here, as a line: joined into the paragraph above it, a
            # whole-line direction would no longer be recognizable as one.
            close_paragraph()
        else:
            paragraph.append(stripped)

    close_chapter()
    if len(chapters) == 1 and _DAY_FILE_RE.match(session):
        chapters = split_agenda_items(chapters[0])
    return chapters


# A whole sitting day in one file, as opposed to the one-file-per-chapter
# layout ("ep-07-01-15-003") used from mid-2006.
_DAY_FILE_RE = re.compile(r"^ep-\d{2}-\d{2}-\d{2}$")

# How the chair opens an agenda item: "The next item is the report (A5-0427/
# 2002) by Giorgio Napolitano, ..." or "We now come to the one-minute speeches".
_AGENDA_TRANSITION_RE = re.compile(
    r"^\s*(?:the\s+next\s+items?\s+(?:is|are|on\s+the\s+agenda)|we\s+(?:now\s+)?(?:come|turn|move)\s+to)\b",
    re.IGNORECASE,
)

# Enough of an announcement to recognize the item without the committee list.
_TRANSITION_TITLE_CHARS = 200


def split_agenda_items(chapter: Chapter) -> List[Chapter]:
    """Split a day-long chapter at the chair's agenda announcements.

    From 2002 to mid-2006 a session file has one ``CHAPTER`` for the whole
    day: tens of thousands of words, every agenda item in one document.  The
    chair announces each item in a regular form (``_AGENDA_TRANSITION_RE``),
    and each announcement starts a new segment titled with it, so the
    procedural title filter still applies ("The next item is the vote.").

    The segment before the first announcement keeps the chapter's own title.
    Segment ids are ``<chapter id>.<n>``, so slugs stay unique.
    """
    segments: List[Chapter] = []
    title = chapter.title
    current: List[Speech] = []

    def close(next_title: str) -> None:
        nonlocal title
        if current:
            segment_id = f"{chapter.chapter_id}.{len(segments)}"
            segments.append(
                replace(chapter, chapter_id=segment_id, title=title, speeches=tuple(current))
            )
            current.clear()
        title = next_title

    for speech in chapter.speeches:
        first = speech.paragraphs[0] if speech.paragraphs else ""
        if speech.is_chair and _AGENDA_TRANSITION_RE.match(first):
            close(first[:_TRANSITION_TITLE_CHARS])
        current.append(speech)
    close("")
    return segments if len(segments) > 1 else [chapter]


# --- Procedural chapters -----------------------------------------------------

# Agenda items that are the machinery of a sitting rather than a debate.  Matched
# against the start of the title, case-insensitively.  Question Time is *not*
# here: it is members questioning the Commission on substance.  Explanations of
# vote are: a thousand near-identical "I voted in favour of this report
# because..." paragraphs would put "voted" and "report" at the top of the list.
_PROCEDURAL_TITLE_RE = re.compile(
    r"""^\s*(?:
        # A chair's announcement, the title of a split day-long chapter (see
        # split_agenda_items), naming procedure rather than a debate.
        (?:the\s+next\s+items?\s+(?:is|are)|we\s+(?:now\s+)?(?:come|turn|move)\s+to)\s+
          (?:the\s+)?(?:votes?\b|voting|explanations?\s+of\s+votes?|agenda|order\s+of\s+business
            |approval\s+of|minutes|membership|composition|verification|documents)
      | resumption\s+of\s+(?:the\s+)?session
      | adjournment\s+of\s+(?:the\s+)?session
      | (?:opening|closure|closing|suspension)\s+of\s+(?:the\s+)?(?:sitting|session)
      | approval\s+of\s+(?:the\s+)?minutes
      | minutes\s+of\s+the\s+previous\s+sitting
      | (?:order\s+of\s+business|agenda)
      | (?:voting\s+time|votes?\b)
      | (?:written\s+)?explanations?\s+of\s+votes?
      | corrections?\s+to\s+votes?
      | corrigend
      | documents?\s+received
      | texts?\s+of\s+(?:treaties|agreements)\s+forwarded
      | membership\s+of\s+(?:parliament|committees|delegations)
      | composition\s+of\s+(?:parliament|committees|political\s+groups)
      | verification\s+of\s+credentials
      | (?:communication|announcement|statement)s?\s+by\s+the\s+president
      | welcome
      | petitions
      | transfers?\s+of\s+appropriations
      | written\s+declarations?
      | decisions?\s+concerning\s+certain\s+documents
      | action\s+taken\s+on\s+parliament'?s?\s+(?:positions|resolutions)
      | time\s+limits?
      | calendar\s+of\s+part-sessions
      | (?:tabling|submission)\s+of\s+motions
      | requests?\s+for\s+(?:urgent|early)\s+(?:procedure|vote)
      | (?:oral\s+questions|written\s+declarations)\s+\(submission\)
      | signature\s+of\s+acts
      | council\s+common\s+positions
      | forwarding\s+of\s+texts
      | points?\s+of\s+order
    )""",
    re.IGNORECASE | re.VERBOSE,
)


def is_procedural_title(title: str) -> bool:
    """True when a chapter title names sitting procedure rather than a debate."""
    return bool(_PROCEDURAL_TITLE_RE.match(title))


# --- Files -------------------------------------------------------------------


def language_dir(cache_dir: Path, language: str = "en") -> Path:
    """Directory holding one language's session files in the cache."""
    return cache_dir / "txt" / language


def session_path(cache_dir: Path, session: str, language: str = "en") -> Path:
    return language_dir(cache_dir, language) / f"{session}.txt"


def iter_session_files(cache_dir: Path, language: str = "en") -> Iterator[Tuple[str, Path]]:
    """Every cached session file for one language, as ``(session, path)``."""
    for path in sorted(language_dir(cache_dir, language).glob("ep-*.txt")):
        yield path.stem, path


def read_session(path: Path) -> List[Chapter]:
    """Parse one cached session file."""
    return parse_session(path.read_text(encoding="utf-8", errors="replace"), path.stem)
