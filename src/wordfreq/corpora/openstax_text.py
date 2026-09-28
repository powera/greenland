"""Reduce an OpenStax book's CNXML source to running prose, chapter by chapter.

A book is a *collection* file (the table of contents: chapters as
``subcollection`` elements, each listing its section *modules*) plus one
``modules/<id>/index.cnxml`` per module.  The unit of analysis is the chapter:
its modules' prose joined into one document.  Chapters are what a proper noun
has to spread across -- a figure the book covers in one chapter is that
chapter's subject, not the corpus's vocabulary -- and a chapter (5-15k words)
is long enough for its rates to mean something.

What is kept is what a reader reads as the book's text: paragraphs, lists,
quotations, figure captions, and the feature boxes (case studies, careers,
primary-source extracts).  What is dropped is everything the book says in
another register or says twice:

* Assessment: ``exercise`` wherever it appears, and every classed
  ``section``.  Body sections carry no class; the classed ones are without
  exception review questions, summaries, key terms, key equations, learning
  objectives, reference lists and further reading (``summary``,
  ``review-questions``, ``critical-thinking``, ``references`` ... -- 50-odd
  classes across the catalogue).  Dropping by the presence of a class, rather
  than listing them, is what keeps a book's own house names out.
* Notes whose class says they are not prose (``DROP_NOTE_CLASSES``): citation
  footnotes, "link to learning" and other pointers to websites and videos,
  teacher-edition notes, and embedded quizzes.
* Structure and non-text: titles and labels (headings would put
  "INTRODUCTION" in every chapter), glossaries, tables, equations, MathML,
  media, and code -- which is how the computing books keep their prose without
  their listings.
* Whole modules: front and back matter (a ``preface`` or ``appendix``
  document, or any module outside a chapter), and per-chapter summary modules
  (``SKIPPED_MODULE_TITLES``).

Nothing here touches the network or the database.
"""

import logging
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator, List, Optional, Tuple

logger = logging.getLogger(__name__)

CNXML_NS = "http://cnx.rice.edu/cnxml"
COLLXML_NS = "http://cnx.rice.edu/collxml"
MDML_NS = "http://cnx.rice.edu/mdml"
MATHML_NS = "http://www.w3.org/1998/Math/MathML"

# Elements whose whole subtree is dropped.  Their tail text -- the prose after
# the element, inside its parent -- is kept.
SKIPPED_ELEMENTS = frozenset(
    {
        "metadata",
        "title",
        "label",
        "glossary",
        "exercise",
        "table",
        "media",
        "equation",
        "code",
        "preformat",
        "footnote",
    }
)

# Elements that start a new line of text.  The tokenizer treats a line start as
# a sentence start, which carries no capitalization evidence; a list item or a
# caption usually opens with a capital whether or not it is a sentence.
BLOCK_ELEMENTS = frozenset(
    {
        "para",
        "item",
        "list",
        "caption",
        "quote",
        "figure",
        "note",
        "section",
        "content",
        "definition",
        "div",
        "document",
    }
)

# A note is dropped when any of its class tokens is one of these.  The rest --
# "clinical-focus", "career", "own-words", "dig-deeper" and the other feature
# boxes -- are ordinary prose.
DROP_NOTE_CLASSES = frozenset(
    {
        # Citations, inside <cite>: author names, titles and URLs.
        "reference",
        # Pointers to websites, videos and simulations.
        "link-to-learning",
        "click-and-explore",
        "linkup",
        "interactive",
        "interactive-long",
        "media-video",
        "media-podcast",
        "guided-slides",
        "download-file",
        # Embedded questions and worked quizzes.
        "check-your-understanding",
        "learning-questions",
        "practice-program",
        "visual-connection",
        "ost-assessed-feature",
        "ost-assignable",
        "ost-get-exercise",
        "workout",
        "chapter-objectives",
        # ... and the business books' names for the same things.
        "concept-check",
        "are-you-ready",
        "work-it-out",
        "think-through",
        "concepts-practice",
        "excel-spreadsheet",
        # The teacher's edition and AP course apparatus.
        "os-teacher",
        "ost-reading-discard",
        "ost-misconception",
        "ost-background-info",
        "ost-tips-teaching",
        "ost-teacher-demonstration",
        "ap-science-practices",
        "ost-sciprac-scithink",
        "ost-sciprac-activity",
        "ost-sciprac-lab",
    }
)

# Document classes of front and back matter.
SKIPPED_DOCUMENT_CLASSES = frozenset({"preface", "appendix"})

# Module titles, lowercased, of per-chapter apparatus published as modules of
# their own rather than as classed sections.
SKIPPED_MODULE_TITLES = frozenset({"chapter summary", "glossary", "key terms"})

# Titles, lowercased, of unclassed sections that are apparatus all the same.
# The Python book marks its learning objectives only by title.
SKIPPED_SECTION_TITLES = frozenset({"learning objectives"})

# A caption's image credit, which always runs to the caption's end: "(credit:
# Vince Maidens, Wikimedia Commons)", "(credit a: modification of work by
# ...)", "Credit: Rao, A., Ryan, K. ...", "Image credit: Golgi: By MethoxyRoxy,
# CC BY-SA 2.5, https://...".  Left in, "Flickr", "Wikimedia" and "Commons"
# rank as corpus vocabulary, and the photographers' names spread across
# chapters the way no other name does.
#
# The credit marker may carry a short label naming the photo it covers:
# "credit a:", "credit a, b:", "credit bread:", "credit a “micrograph”:", or
# "credit (b)" with no colon at all.  OpenStax's own figures say "(attribution:
# Biology 2e, Rice University, OpenStax, under CC BY 4.0 license)" instead,
# which left "Rice", "Openstax", "Cc" and "Nc" in the list.
_CAPTION_CREDIT = re.compile(
    r"\(?\b(?:(?:image\s+|photo\s+)?credits?|attributions?)\b(?:\s*\([a-z]\)|[^:()\n]{0,40}:).*",
    re.IGNORECASE | re.DOTALL,
)

# Microbiology's links between its feature boxes: "Jump to the next Clinical
# Focus box. Go back to the previous Clinical Focus box."
_NAVIGATION_LINE = re.compile(r"^(?:Jump to|Go back to) the (?:next|previous)\b.*$", re.MULTILINE)

# What an empty cross-reference leaves behind: "The Wizard of Oz (), was ...".
_EMPTY_PARENTHESES = re.compile(r"\s*\(\s*\)")

_WHITESPACE = re.compile(r"[ \t\r\f\v]+")
_BLANK_LINES = re.compile(r"\s*\n\s*")


@dataclass
class Chapter:
    """One chapter of one book.

    Attributes:
        number: 1-based position among the book's chapters.
        title: The chapter title from the collection file.
        module_ids: The chapter's modules, in book order.
    """

    number: int
    title: str
    module_ids: List[str] = field(default_factory=list)


def local_name(tag: str) -> str:
    """An element's tag without its namespace."""
    return tag.rsplit("}", 1)[-1]


def _namespace(tag: str) -> str:
    return tag[1:].split("}", 1)[0] if tag.startswith("{") else ""


def class_tokens(element: ET.Element) -> frozenset[str]:
    """The whitespace-separated tokens of an element's ``class`` attribute."""
    return frozenset(element.get("class", "").split())


def _title_of(element: ET.Element) -> str:
    """The lowercased text of an element's own ``title`` child."""
    title = element.find(f"{{{CNXML_NS}}}title")
    if title is None:
        return ""
    return normalize("".join(title.itertext())).lower()


def _is_punctuation(text: Optional[str]) -> bool:
    return not any(character.isalnum() for character in text or "")


def is_link_only(element: ET.Element) -> bool:
    """Whether a paragraph is nothing but links.

    That is how the physics books embed a video ("OpenStax AP Physics Chapter
    4: Newton's Laws Physics Concept Trailer") and how Microbiology links its
    feature boxes together ("Jump to the next Clinical Focus box.") -- titles
    and navigation, not sentences.  A link inside running prose is kept, since
    its text is part of the sentence.
    """
    children = list(element)
    if not children or not _is_punctuation(element.text):
        return False
    return all(
        local_name(child.tag) == "link" and _is_punctuation(child.tail) for child in children
    )


def is_skipped(element: ET.Element) -> bool:
    """Whether an element's whole subtree is left out of the prose."""
    if _namespace(element.tag) == MATHML_NS:
        return True
    name = local_name(element.tag)
    if name in SKIPPED_ELEMENTS:
        return True
    if name == "section":
        return bool(element.get("class", "").strip()) or (
            _title_of(element) in SKIPPED_SECTION_TITLES
        )
    if name == "note":
        return bool(class_tokens(element) & DROP_NOTE_CLASSES)
    if name == "para":
        return is_link_only(element)
    return False


def _collect(element: ET.Element, pieces: List[str]) -> None:
    """Append the kept text of ``element`` (not its tail) to ``pieces``."""
    name = local_name(element.tag)
    block = name in BLOCK_ELEMENTS
    if block:
        pieces.append("\n")
    if name == "newline":
        pieces.append(" ")
    inner: List[str] = []
    if element.text:
        inner.append(element.text)
    for child in element:
        if not is_skipped(child):
            _collect(child, inner)
        if child.tail:
            inner.append(child.tail)
    if name == "caption":
        pieces.append(strip_caption_credit("".join(inner)))
    else:
        pieces.extend(inner)
    if block:
        pieces.append("\n")


def normalize(text: str) -> str:
    """Collapse runs of spaces, and of line breaks, to one of each."""
    text = _WHITESPACE.sub(" ", text)
    return _BLANK_LINES.sub("\n", text).strip()


def strip_caption_credit(caption: str) -> str:
    """A caption's text without its trailing image credit."""
    return _CAPTION_CREDIT.sub("", caption)


def element_text(element: ET.Element) -> str:
    """The prose of one element, one block per line."""
    pieces: List[str] = []
    if not is_skipped(element):
        _collect(element, pieces)
    text = normalize("".join(pieces))
    return normalize(_EMPTY_PARENTHESES.sub("", _NAVIGATION_LINE.sub("", text)))


def is_skipped_module(root: ET.Element) -> bool:
    """Whether a whole module is front matter, back matter or apparatus."""
    if class_tokens(root) & SKIPPED_DOCUMENT_CLASSES:
        return True
    return _title_of(root) in SKIPPED_MODULE_TITLES


def module_text(source: str) -> str:
    """The prose of one module's CNXML, or ``""`` if the module is skipped."""
    root = ET.fromstring(source)
    if is_skipped_module(root):
        return ""
    content = root.find(f"{{{CNXML_NS}}}content")
    if content is None:
        return ""
    return element_text(content)


def parse_collection(source: str) -> List[Chapter]:
    """The chapters of a collection file, in book order.

    A chapter is a ``subcollection`` that lists modules directly.  Units -- a
    subcollection of subcollections -- are walked through, not counted.
    Modules outside any subcollection are the preface and appendices, and are
    not part of any chapter.
    """
    root = ET.fromstring(source)
    chapters: List[Chapter] = []
    # iter() is document order, so a unit comes before the chapters inside it.
    for subcollection in root.iter(f"{{{COLLXML_NS}}}subcollection"):
        content = subcollection.find(f"{{{COLLXML_NS}}}content")
        if content is None:
            continue
        modules = [
            module.get("document", "")
            for module in content.findall(f"{{{COLLXML_NS}}}module")
            if module.get("document")
        ]
        if not modules:
            continue
        title_element = subcollection.find(f"{{{MDML_NS}}}title")
        title = "" if title_element is None else normalize("".join(title_element.itertext()))
        chapters.append(Chapter(number=len(chapters) + 1, title=title, module_ids=modules))
    return chapters


def chapter_slug(book_slug: str, number: int) -> str:
    """``<book>/<NN>``: the key a chapter is reported under."""
    return f"{book_slug}/{number:02d}"


def split_chapter_slug(slug: str) -> Tuple[str, int]:
    """Inverse of :func:`chapter_slug`."""
    book, _, number = slug.rpartition("/")
    return book, int(number)


def read_chapters(
    collection_file: Path, modules_dir: Path, book_slug: str
) -> Iterator[Tuple[str, str]]:
    """``(slug, text)`` for each chapter of one checked-out book.

    A module missing from the checkout is logged and skipped rather than
    failing the book.  Chapters with no text left are not yielded.
    """
    chapters = parse_collection(collection_file.read_text(encoding="utf-8"))
    for chapter in chapters:
        parts: List[str] = []
        for module_id in chapter.module_ids:
            path = modules_dir / module_id / "index.cnxml"
            if not path.exists():
                logger.warning("%s: module %s not checked out", book_slug, module_id)
                continue
            text = module_text(path.read_text(encoding="utf-8"))
            if text:
                parts.append(text)
        if parts:
            yield chapter_slug(book_slug, chapter.number), "\n".join(parts)
