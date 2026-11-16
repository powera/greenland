"""Plain-text handling for Open American National Corpus primary texts.

The counterpart of :mod:`wordfreq.corpora.scotus_text` for the OANC
documents that ``download_oanc.py`` caches as ``<cache>/<subcorpus>/**/*.txt``.
The tokenizer and capitalization analysis are shared, so a cleaned document
goes through :func:`wordfreq.corpora.frequency_build.analyze_book` unchanged.

The written subcorpora are already clean prose: the GrAF primary text carries
no markup, the annotations being standoff files the downloader skips.  Two
things are still done here:

* **The headline is dropped.**  A Slate article opens with its title on the
  first line ("Slobodan But Surely?", "Talking Points for the Times!"), set in
  title case.  Capitalized ordinary words there would count as evidence that
  the words are names.
* **Hard-wrapped lines are rejoined.**  Paragraphs are wrapped at about 80
  columns and separated by blank or indented lines; joining each paragraph
  onto one line keeps a capitalized word that happens to start a line ("and
  Los\\nAngeles") from reading as sentence-initial.

Nothing here touches the network or the database.
"""

import re
from pathlib import Path
from typing import Iterator, NamedTuple

# A paragraph break: a blank line, or a line break followed by indentation.
PARAGRAPH_BREAK_RE = re.compile(r"\n\s*\n|\n(?=[ \t])")
WHITESPACE_RE = re.compile(r"\s+")


class OancDocument(NamedTuple):
    """One cleaned OANC document."""

    slug: str
    text: str


def clean_document(raw: str, *, drop_headline: bool = True) -> str:
    """Strip the headline and rejoin wrapped lines into paragraphs.

    Args:
        raw: The primary text as stored in the archive.
        drop_headline: Remove the first non-empty line.

    Returns:
        The document as paragraphs separated by blank lines.
    """
    text = raw.replace("\r\n", "\n").replace("\r", "\n").strip()
    if drop_headline:
        _, _, text = text.partition("\n")
    paragraphs = [WHITESPACE_RE.sub(" ", block).strip() for block in PARAGRAPH_BREAK_RE.split(text)]
    return "\n\n".join(paragraph for paragraph in paragraphs if paragraph)


def iter_documents(
    subcorpus_dir: Path, *, min_chars: int = 0, drop_headline: bool = True
) -> Iterator[OancDocument]:
    """Yield every cleaned document under ``subcorpus_dir``, in path order.

    The slug is the path below the subcorpus directory without its suffix
    (``6/Article247_720``), which is unique within a subcorpus.

    Args:
        subcorpus_dir: ``<cache>/<subcorpus>`` as written by ``download_oanc``.
        min_chars: Skip documents shorter than this once cleaned.
        drop_headline: Remove each document's first line.
    """
    for path in sorted(subcorpus_dir.rglob("*.txt")):
        if path.name.startswith("._"):
            continue
        text = clean_document(
            path.read_text(encoding="utf-8", errors="replace"), drop_headline=drop_headline
        )
        if len(text) < min_chars:
            continue
        yield OancDocument(
            slug=path.relative_to(subcorpus_dir).with_suffix("").as_posix(), text=text
        )
