"""Plain-text handling for the WPA American Life Histories PDFs.

The counterpart of :mod:`wordfreq.corpora.scotus_text` for the Library of
Congress life-history manuscripts that ``download_wpalh.py`` caches.  The
tokenizer and capitalization analysis are shared, so a cleaned interview goes
through :func:`wordfreq.corpora.frequency_build.analyze_book` unchanged.

Each PDF is a scanned typescript whose text layer is the Library's own OCR.
Three kinds of non-interview text come with it:

* **Questionnaire pages.**  Many interviews open with the Folklore Project's
  "Form A" (circumstances of interview) and "Form B" (personal history of
  informant), and some with an editor's checking sheet.  They are a list of
  printed prompts -- "Place and date of birth", "Description of informant" --
  that would otherwise repeat in every document.  A page carrying two or more
  of the prompts is dropped whole.
* **Header lines.**  The text pages ("Form C") and the Southern write-ups
  open with field labels, writer and editor credits, project names, page
  numbers and accession stamps.  These are dropped line by line, as is any
  line carrying a form prompt on a page that was otherwise kept.
* **OCR debris.**  Lines that are mostly punctuation and digits.

Words broken across a line end ("re-\\nmember") are rejoined.

Most remaining OCR damage is one-off and the builder's minimum-document
threshold removes it.  The exception is the typewriter's regular letter
confusions -- "tne" for "the", "oould" for "could" -- which recur in hundreds
of interviews.  :func:`build_ocr_corrections` maps those back to the word they
misread, judged against the whole collection's counts and a vocabulary of
words attested elsewhere, and :func:`apply_ocr_corrections` rewrites them and
deletes unknown fragments ("tt", "ie").

Nothing here touches the network or the database.  Reading a PDF needs
``pypdf``, which is deliberately not a project dependency: it is only needed
to (re)extract the text cache, so it is imported on first use.
"""

import re
from collections import Counter
from pathlib import Path
from typing import Collection, Dict, Iterable, List, Mapping, Optional

# --- Questionnaire pages ---------------------------------------------------

# Printed prompts of the Folklore Project forms and the editor's checking
# sheet.  OCR mangles individual prompts often enough ("NAME OF VORKER") that
# a page is judged on how many it carries, not on any one of them.
FORM_PROMPTS = [
    r"forms?\s+to\s+be\s+filled",
    r"circumstances\s+of\s+interv",
    r"date\s+and\s+time\s+of\s+interview",
    r"place\s+of\s+interview",
    r"name\s+and\s+address\s+of\s+(?:informant|person)",
    r"description\s+of\s+(?:room|informant)",
    r"personal\s+history",
    r"place\s+and\s+date\s+of\s+birth",
    r"places\s+lived\s+in",
    r"education,?\s+with\s+dates",
    r"occupations\s+and\s+accomplishments",
    r"special\s+skills\s+and\s+interests",
    r"community\s+and\s+religious",
    r"other\s+points\s+gained",
    r"original\s+mss",
    r"field\s+notes",
    r"sources\s+given",
    r"checker",
    # The Southern states' own header form.
    r"name\s+of\s+person\s+interviewed",
    r"street\s+address",
    r"touch\s+with\s+informant",
]
FORM_PROMPT_RES = [re.compile(prompt, re.IGNORECASE) for prompt in FORM_PROMPTS]
MIN_FORM_PROMPTS = 2

# --- Header lines ------------------------------------------------------------

# Field labels are printed in capitals; matching them case-sensitively keeps
# "Date" or "State" at the start of an ordinary sentence.
FIELD_LABEL_RE = re.compile(r"^\s*(?:STATE|NAME\s+OF\s+\S+|ADDRESS|DATE|SUBJECT)\b")
HEADER_LINE_RE = re.compile(
    r"""^\s*(?:
        FOLK\s*LORE\b.*
      | FOLK\s*STUFF\b.*
      | FORM\s+\S{1,3}\s*$
      | FORM\s+[A-D]\b.*
      | TEXT\s+OF\s+INTERVIEW.*
      | (?:WRITTEN|EDITED|REVISED|TYPED)\s+BY\b.*
      | EDITOR\s*$
      | RESEARCH\s+FIELD\s+WORKER.*
      | .*\bWRITERS'?\s+PROJECT\b.*
      | .*\bW\.?\s?P\.?\s?A\.?\s+AREA\b.*
      | .*\bLIBRARY\s+OF\s+CONGRESS\b.*
      | LIVING\s+LORE\b.*
      | PAGE\s*\d+\s*$
    )""",
    re.IGNORECASE | re.VERBOSE,
)
# A running header: one or two words and a page number ("Noakes Page 2",
# "Pilaw - 2").  Three tokens at most, so a line of dialogue ending in a
# number is not caught.
PAGE_HEADER_RE = re.compile(r"^\s*(?:\S+\s+){0,2}(?:page\s*|[-–]\s*)\d{1,3}\s*$", re.IGNORECASE)
# An accession stamp on its own line: "W15075", "W3612".
STAMP_RE = re.compile(r"^\s*[A-Z]{1,2}\s?\d{3,6}\s*$")
# Below this share of letters among a line's non-space characters, the line
# is OCR debris or a table of figures rather than prose.
MIN_LETTER_SHARE = 0.6
# All-capitals lines with at least this many letters are headings.  "I" and
# "OK" alone on a line are not.
MIN_CAPS_LINE_LETTERS = 4

# A word broken across a line end: "re-\nmember".  Only a lowercase
# continuation is joined, so a dash before a capitalized line is kept apart.
LINE_END_HYPHEN_RE = re.compile(r"([A-Za-z])-[ \t]*\n[ \t]*([a-z])")

# --- Dialect -----------------------------------------------------------------

# Eye-dialect spellings the writers used, chiefly for Southern Black speakers.
# Only spellings that are not also ordinary words or names are listed: "de"
# and "chile" would count Spanish and New Mexico's chile, "den", "ax" and "wit"
# are words, "der" is German, and "'em", "ole" or "nothin'" are how everyone in
# the collection is written as talking.
# Apostrophes are stripped before matching, as the tokenizer does at edges.
DIALECT_MARKERS = frozenset(
    {
        "dat",
        "dat's",
        "dey",
        "dey's",
        "dem",
        "dis",
        "dese",
        "dose",
        "dar",
        "wid",
        "wif",
        "gwine",
        "gwan",
        "chillun",
        "chilluns",
        "lawd",
        "lak",
        "sho",
        "fust",
        "jes",
        "wus",
        "befo",
        "yo",
        "yas",
        "yassum",
        "yessum",
        "nawsuh",
        "yassuh",
        "massa",
        "marster",
        "mistis",
        "sez",
        "iffen",
        "whar",
        "thar",
        "dere",
        "dat'll",
    }
)
_WORD_RE = re.compile(r"[A-Za-z][A-Za-z']*")

# --- OCR misreadings -----------------------------------------------------------

# Letter pairs the Library's OCR confuses in 1930s typescript, both ways:
# "tne" for "the", "oould" for "could", "whioh" for "which", "thnt" for
# "that".  Confusions this regular recur across hundreds of documents, so the
# minimum-document threshold cannot remove them.
_CONFUSION_PAIRS = [
    "co",
    "ce",
    "eo",
    "ea",
    "ao",
    "au",
    "nh",
    "na",
    "nu",
    "nm",
    "nr",
    "hb",
    "lt",
    "li",
    "it",
    "tf",
    "td",
    "io",
    "vw",
]


def _confusion_table(pairs: Iterable[str]) -> Dict[str, str]:
    """Each letter mapped to the letters it is confused with, in both directions."""
    table: Dict[str, str] = {}
    for pair in pairs:
        table[pair[0]] = table.get(pair[0], "") + pair[1]
        table[pair[1]] = table.get(pair[1], "") + pair[0]
    return table


OCR_CONFUSIONS = _confusion_table(_CONFUSION_PAIRS)
# A correction must be this many times more frequent than the misreading...
DEFAULT_MIN_CORRECTION_RATIO = 10
# ... and among this many of the corpus's most frequent words.
DEFAULT_MAX_CORRECTION_TARGET_RANK = 3000
# A word other corpora also have is corrected only if it ranks this many times
# higher here than in any of them...
DEFAULT_KNOWN_OVERREPRESENTATION = 3
# ... and its correction is this many times as frequent.
DEFAULT_KNOWN_MIN_CORRECTION_RATIO = 20
# Known words that pass both tests but, sampled, are as often meant as
# misread: "a buck Indian" beside "getting buck to Fernandina", "Hey, Docia"
# beside "hey were too lazy", and "git" is how people talked.
NEVER_CORRECT = frozenset({"buck", "hey", "git"})
_VOWEL_RE = re.compile(r"[aeiouy]")
_LOWERCASE_LETTERS = "abcdefghijklmnopqrstuvwxyz"
# Whole words only, so "tne" is rewritten but "tnes" inside nothing is not.
_BARE_WORD_RE = re.compile(r"(?<![A-Za-z'])[A-Za-z]+(?:'[A-Za-z]+)*(?![A-Za-z])")


def extract_pages(pdf: Path) -> List[str]:
    """The text layer of every page of one PDF, in order.

    Raises:
        RuntimeError: if ``pypdf`` is not installed.
    """
    try:
        from pypdf import PdfReader  # type: ignore[import-not-found, unused-ignore]
    except ImportError as error:
        raise RuntimeError(
            "Reading the life-history PDFs needs pypdf, which is not a project "
            "dependency: pip install pypdf"
        ) from error
    reader = PdfReader(str(pdf))
    return [page.extract_text() or "" for page in reader.pages]


def count_form_prompts(page: str) -> int:
    """How many distinct questionnaire prompts a page carries."""
    return sum(1 for prompt in FORM_PROMPT_RES if prompt.search(page))


def is_form_page(page: str) -> bool:
    """Whether a page is a questionnaire or checking sheet, not interview text."""
    return count_form_prompts(page) >= MIN_FORM_PROMPTS


def is_header_line(line: str) -> bool:
    """Whether a line is a label, credit, page header, stamp or OCR debris."""
    stripped = line.strip()
    if not stripped:
        return False
    if FIELD_LABEL_RE.match(stripped) or HEADER_LINE_RE.match(stripped):
        return True
    # A form prompt on a page the page-level test kept, because the writer
    # filled the form in on the same sheet as the interview ("3. Name and
    # address of informant Charles Brown, Canyon City").
    if any(prompt.search(stripped) for prompt in FORM_PROMPT_RES):
        return True
    if PAGE_HEADER_RE.match(stripped) or STAMP_RE.match(stripped):
        return True
    visible = [char for char in stripped if not char.isspace()]
    letters = [char for char in visible if char.isalpha()]
    if len(letters) / len(visible) < MIN_LETTER_SHARE:
        return True
    # An all-capitals line is a title or label in these typescripts
    # ("INTERVIEW WITH JOHN LOVETT"), and gives the proper-noun test no
    # capitalization evidence: left in, its names are counted as words.
    return len(letters) >= MIN_CAPS_LINE_LETTERS and all(char.isupper() for char in letters)


def clean_page(page: str) -> str:
    """A text page with its header lines and debris removed."""
    kept = [line.rstrip() for line in page.splitlines() if not is_header_line(line)]
    return "\n".join(kept)


def clean_pages(pages: Iterable[str]) -> str:
    """The interview text of one document: forms dropped, headers stripped.

    Line-end hyphens are rejoined after the pages are put back together, so a
    word broken across a page boundary is mended too.
    """
    body = [clean_page(page) for page in pages if not is_form_page(page)]
    text = "\n".join(page for page in body if page.strip())
    return LINE_END_HYPHEN_RE.sub(r"\1\2", text)


def dialect_share(text: str) -> float:
    """Share of a text's words that are eye-dialect spellings."""
    words = [word.strip("'").lower() for word in _WORD_RE.findall(text)]
    words = [word for word in words if word]
    if not words:
        return 0.0
    counts = Counter(words)
    marked = sum(count for word, count in counts.items() if word in DIALECT_MARKERS)
    return marked / len(words)


def word_counts(texts: Iterable[str]) -> Counter[str]:
    """Lowercase word counts over a set of texts, apostrophes stripped at the edges."""
    counts: Counter[str] = Counter()
    for text in texts:
        for word in _WORD_RE.findall(text):
            stripped = word.strip("'").lower()
            if stripped:
                counts[stripped] += 1
    return counts


def _confusion_variants(word: str) -> Iterable[str]:
    """Every spelling one OCR misreading away from ``word``.

    Either one letter confused with another, or a first letter lost at the
    left margin of the page: "fter", "ounty" and "hose" are "after", "county"
    and "those" with the typebar's first strike too faint to read.
    """
    for index, char in enumerate(word):
        for replacement in OCR_CONFUSIONS.get(char, ""):
            yield word[:index] + replacement + word[index + 1 :]
    for letter in _LOWERCASE_LETTERS:
        yield letter + word


def is_ocr_fragment(word: str, known: Collection[str]) -> bool:
    """An unknown token too short or vowelless to be a word: "tt", "ie", "tht"."""
    if word in known:
        return False
    return len(word) <= 2 or not _VOWEL_RE.search(word)


def build_ocr_corrections(
    counts: Counter[str],
    known: Mapping[str, int],
    *,
    min_ratio: int = DEFAULT_MIN_CORRECTION_RATIO,
    max_target_rank: int = DEFAULT_MAX_CORRECTION_TARGET_RANK,
    known_overrepresentation: int = DEFAULT_KNOWN_OVERREPRESENTATION,
    known_min_ratio: int = DEFAULT_KNOWN_MIN_CORRECTION_RATIO,
) -> Dict[str, str]:
    """Map recurring OCR misreadings to the word they misread.

    An unknown word is corrected when it is one misreading away from a known
    word at least ``min_ratio`` times as frequent in the same corpus: "tne"
    becomes "the", "oould" "could".  Dialect spellings are never corrected
    ("sho" is "sure", not a misread "she").

    A known word -- one some other corpus also has -- is corrected only on
    much stronger evidence, because it may be meant.  It must rank at least
    ``known_overrepresentation`` times higher here than anywhere else, and the
    correction must be ``known_min_ratio`` times as frequent.  That is what
    "ant", "ny" and "ti" look like in this collection: 2,476 "ant"s, sampled,
    are all "and", and "and" is 60 times as common.  A word this corpus is
    genuinely about is over-represented too ("barn", "mule"), but no
    misreading neighbor of it is twenty times as frequent.

    The correction must also be among the corpus's ``max_target_rank`` most
    frequent words.  Misreadings pile up on common words, because that is
    where most of the typed letters are; without the limit a rare word is
    credited with every near miss that happens to sit next to it.

    Args:
        counts: Lowercase word counts over the whole corpus.
        known: Lowercase words attested elsewhere (the other corpora), each
            mapped to its best rank in any of them.
        min_ratio: How much more frequent an unknown word's correction must be.
        max_target_rank: How far down the corpus's own list a correction may
            come from.
        known_overrepresentation: How much higher a known word must rank here
            than elsewhere before it is a candidate at all.
        known_min_ratio: How much more frequent a known word's correction must be.

    Returns:
        Lowercase misreading -> lowercase correction.
    """
    ranked = [word for word, _ in counts.most_common()]
    corpus_rank = {word: rank for rank, word in enumerate(ranked, start=1)}
    targets = set(ranked[:max_target_rank]) & known.keys()
    corrections: Dict[str, str] = {}
    for word, count in counts.items():
        if word in DIALECT_MARKERS or word in NEVER_CORRECT:
            continue
        if word in known:
            if corpus_rank[word] * known_overrepresentation > known[word]:
                continue
            ratio = known_min_ratio
        elif len(word) < 3:
            continue
        else:
            ratio = min_ratio
        best: Optional[str] = None
        best_count = count * ratio - 1
        for variant in _confusion_variants(word):
            if variant in targets and counts[variant] > best_count:
                best, best_count = variant, counts[variant]
        if best is not None:
            corrections[word] = best
    return corrections


def apply_ocr_corrections(text: str, corrections: Dict[str, str], known: Collection[str]) -> str:
    """Rewrite misreadings and delete fragments, keeping an initial capital."""

    def fix(match: "re.Match[str]") -> str:
        word = match.group(0)
        lower = word.lower()
        corrected = corrections.get(lower)
        if corrected is not None:
            return corrected.capitalize() if word[0].isupper() else corrected
        if is_ocr_fragment(lower, known):
            return ""
        return word

    return _BARE_WORD_RE.sub(fix, text)


def slugify_item(shelf_id: str, title: str, max_length: int = 90) -> str:
    """``<shelf id>_<Title>`` key for one interview in the corpus JSON."""
    words = re.findall(r"[A-Za-z0-9]+", title)
    slug = f"{shelf_id}_{'_'.join(words)}" if words else shelf_id
    return slug[:max_length]
