"""Plain-text handling for Supreme Court opinions from the Caselaw Access Project.

The counterpart of :mod:`wordfreq.corpora.gutenberg_text` for CAP's case JSON.
Both jobs here are purely mechanical (no network, no database); the tokenizer
and capitalization analysis are shared, so a stripped opinion goes through
:func:`wordfreq.corpora.gutenberg_text.analyze_text` unchanged.

CAP has already done the structural separation a Gutenberg book needs markers
for.  ``casebody`` carries ``head_matter``, ``parties``, ``attorneys`` and
``judges`` as fields of their own, so the syllabus, the reporter's caption and
the list of counsel never reach the text: taking ``opinions[].text`` is enough,
and there is no equivalent of the licence header to find.

What is left to strip is citation apparatus, which is dense in a way ordinary
prose is not.  It is about 5% of the words in a typical opinion and is almost
entirely numerals, reporter abbreviations and Latin cross-references -- text
that would otherwise contribute ``stat``, ``ante`` and ``ibid`` to an English
frequency list.  The patterns below cover:

* full citations (``534 U. S. 438``, ``171 F. 3d 1052``, ``106 Stat. 3037``)
  and the short forms that follow them (``534 U. S., at 442``);
* statutes and public laws (``26 U. S. C. § 9706(a)``, ``Pub. L. 102-486``);
* section and footnote references (``§ 9701(b)(1)``, ``n. 3``);
* internal cross-references (``Id.``, ``Ibid.``, ``supra``, ``ante, at 12``);
* record citations (``Brief for Petitioners 14``).

**Case names are deliberately left in place.**  ``Barnhart v. Sigmon Coal Co.``
is a proper noun, and the per-book capitalization rule in
:mod:`wordfreq.corpora.frequency_build` already classifies it as one: a party
name appears capitalized away from sentence starts essentially every time, so
it lands in ``name_frequency`` rather than the vocabulary.  Deleting the names
here would instead throw away the surrounding syntax, and stripping ``v.``
alone would leave two bare names running together.
"""

import re
from typing import Any, Dict, Iterator, List, NamedTuple, Optional

# --- Citation apparatus ------------------------------------------------------

# Reporter volumes print "U. S." and "F. 3d" with internal spaces, so a pattern
# written as "U.S.C." matches nothing.  Every abbreviation here allows optional
# space after each period.
_REPORTER = r"(?:U\.\s?S\.|F\.|S\.\s?Ct\.|L\.\s?Ed\.|F\.\s?Supp\.)"

CITATION_RE = re.compile(
    r"""
      # Statutes: "26 U. S. C. § 9706(a)", with or without the section.
      \d+\s+U\.\s?S\.\s?C\.(?:\s?App\.)?(?:\s?§+\s?[\d\w().,\s-]*?(?=[,;.]?\s))?
      # Full reporter citations: "534 U. S. 438", "171 F. 3d 1052".
    | \d+\s+"""
    + _REPORTER
    + r"""\s?(?:[23]d\s)?\s*\d+
      # Short forms that follow one: "534 U. S., at 442", "id., at 9".
    | \d+\s+"""
    + _REPORTER
    + r"""\s?,?\s*(?:at\s+[\d\s,-]+)?
      # Session laws: "106 Stat. 3037", "Pub. L. 102-486".
    | \d+\s+Stat\.\s+[\d,-]+
    | Pub\.\s?L\.\s?(?:No\.\s?)?[\d-]+
      # Bare section and footnote references.
    | §+\s?[\d\w()-]+
    | \bn\.\s?\d+
      # Latin cross-references, with an optional pinpoint.  These are printed
      # both capitalized and not, and "ibid" appears with and without its
      # period, so the whole group is matched case-insensitively.
    | (?i:\b(?:id|ibid)\b\.?,?(?:\s+at\s+[\d\s,-]+)?)
    | (?i:\b(?:ante|post|supra|infra)\b,?(?:\s+at\s+[\d\s,-]+)?)
      # Edition and supplement cites: "(1976 ed., Supp. V)", "(4th ed. 2000)".
    | \b\d*(?:st|nd|rd|th)?\s?ed\.(?:,?\s?Supp\.\s?[IVX\d]+)?
    | \bSupp\.\s?[IVX\d]+
      # Record citations.
    | \bBrief\s+for\s+[A-Za-z .]+?\s+\d+
      # A run of two or more apparatus elements -- abbreviations, numbers and
      # section signs in sequence.  This is what catches state statute cites
      # ("La. Rev. Stat. Ann. §§27:301", "Nev. Rev. Stat. § 41.036") without
      # naming the states: there are 539 distinct abbreviation-shaped tokens
      # in a 20-case sample and a list of them would never be complete, but
      # apparatus is structurally a *run* while prose is not.  The leading
      # (?<![A-Za-z]) stops the pattern matching the tail of a real word.
      # An apparatus run must be *anchored* by an abbreviation or a section
      # sign; bare numbers only join a run, never start one.  Otherwise
      # ordinary prose loses its dates and quantities ("In 1998, Congress
      # enlarged the duration by 20 years").
    | (?:(?<![A-Za-z])[A-Z][A-Za-z&]{0,4}\.|§+)
      (?:\s*(?:(?<![A-Za-z])[A-Z][A-Za-z&]{0,4}\.|\d[\d,\-–:]*|§+|\bat\b))*
      # Isolated abbreviations, which by definition have no neighbouring
      # element for the run rule to catch.  These are the frequent, closed set
      # -- signals, reporters, corporate suffixes and the Latin cross-refs --
      # not the open-ended list of jurisdictions.
    | \b(?:Cf|cf|Id|id|Ibid|ibid|Inc|Co|Corp|Assn|Bd|Univ|Dept|Dist|Cty|Div|Jr|Sr)\.
    | \b(?:App|Pet|Cert|cert|Tr|Arg|Cong|Sess|Rec|Exh|Regs?|Rev|Stat|Supp|Ann|Const|Art|Tit|Proc|Comm|Cas|Rep|Rcd|Wall|How)\.
    | \b(?:pp?|ch|cl|al|seq|etc|ed|Ed|JJ|Nos?|So|pt|added)\.
    | \b(?:Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sept?|Oct|Nov|Dec)\.
      # "e. g.," and "i. e.," -- printed with a space in this reporter.
    | \b[ei]\.\s?[ge]\.,?
    | \bet\s+(?:al|seq)\.
    | \bhttps?://\S+|\bwww\.\S+
    | \bApp\.\s+(?:to\s+Pet\.\s+for\s+Cert\.\s+)?\d*[a-z]?
      # Constitutional cites and trailing years.
    | \bArt\.\s?[IVX]+(?:,\s?§+\s?\d+)?(?:,\s?cl\.\s?\d+)?
    | \bAmdt\.\s?\d+
    | \(\d{4}\)
    """,
    re.VERBOSE,
)

# --- Editorial insertions ----------------------------------------------------

# Quotations are altered in brackets to fit the sentence quoting them:
# "[w]hen" lowercases an opening capital, "see[k]" adjusts a verb, and
# "[the Secretary's]" replaces a pronoun with its referent.  The brackets are
# an editorial convention, not part of the word, and the tokenizer treats them
# as boundaries -- so "[w]hen" counts as "hen", "see[k]" as "see" and
# "assum[e]" as "assum".  Removing the brackets and keeping the letters is the
# only reading that yields the word the Justice actually wrote.
_BRACKET_INSERTION_RE = re.compile(r"\[([^\[\]]{1,60}?)\]")


def unbracket_insertions(text: str) -> str:
    """Drop editorial brackets from quotations, keeping the text inside.

    ``"[w]hen"`` becomes ``"when"`` and ``"see[k]"`` becomes ``"seek"``.  A
    bracket holding no letters (an ellipsis or a stray mark) is dropped whole,
    since there is no word in it to keep.
    """

    def keep(match: "re.Match[str]") -> str:
        inner = match.group(1)
        return inner if any(ch.isalpha() for ch in inner) else ""

    return _BRACKET_INSERTION_RE.sub(keep, text)


# Left behind once the citations go: ", ,", " ;" and runs of stray commas.
_ORPHAN_PUNCT_RE = re.compile(r"\s+([,;.])")
_REPEAT_PUNCT_RE = re.compile(r"([,;])(\s*[,;])+")
_WHITESPACE_RE = re.compile(r"[ \t]+")


def strip_citations(text: str) -> str:
    """Remove citation apparatus from an opinion, leaving its prose.

    Args:
        text: One opinion's text, as CAP stores it.

    Returns:
        The text with citations removed and the punctuation they stranded
        tidied up.  Sentence structure is otherwise untouched.
    """
    stripped = CITATION_RE.sub(" ", text)
    stripped = _REPEAT_PUNCT_RE.sub(r"\1", stripped)
    stripped = _ORPHAN_PUNCT_RE.sub(r"\1", stripped)
    stripped = _WHITESPACE_RE.sub(" ", stripped)
    return "\n".join(line.strip() for line in stripped.splitlines())


# --- Opinion extraction ------------------------------------------------------

# "Justice Ginsburg\ndelivered the opinion of the Court." opens most opinions;
# the attribution is metadata rather than prose and repeats across every case.
_ATTRIBUTION_RE = re.compile(
    r"\A\s*(?:Mr\.\s+)?(?:Chief\s+)?Justice\s+[A-Z][A-Za-z]+\s*,?\s*"
    r"(?:with\s+whom[^.]*?,?\s*)?"
    r"(?:delivered\s+the\s+opinion[^.]*\.|"
    r"(?:concurring|dissenting)[^.]*\.|"
    r"(?:concurs?|dissents?)[^.]*\.)",
    re.IGNORECASE,
)


def strip_attribution(text: str) -> str:
    """Drop the "Justice X delivered the opinion of the Court." opener."""
    return _ATTRIBUTION_RE.sub("", text, count=1).lstrip()


class Opinion(NamedTuple):
    """One opinion within a case.

    Attributes:
        case_id: CAP's numeric case id.
        slug: Key used for this opinion in the corpus JSON.
        opinion_type: ``majority``, ``dissent``, ``concurrence``, ...
        author: Authoring justice as CAP records them ("" when absent).
        text: The opinion's prose, citations and attribution removed.
    """

    case_id: int
    slug: str
    opinion_type: str
    author: str
    text: str


def slugify_case(
    case_id: int, name: str, opinion_type: str, index: int, max_length: int = 90
) -> str:
    """Key for one opinion in the corpus JSON (``<id>_<Name>_<type>``)."""
    cleaned = re.sub(r"[^\w\s-]", "", name).strip()
    cleaned = re.sub(r"[\s-]+", "_", cleaned)
    room = max_length - len(str(case_id)) - len(opinion_type) - 3
    if room > 0:
        cleaned = cleaned[:room]
    return f"{case_id}_{cleaned}_{opinion_type}{index if index else ''}"


def iter_opinions(
    case: Dict[str, Any],
    *,
    include_types: Optional[List[str]] = None,
    min_chars: int = 0,
    min_year: Optional[int] = None,
) -> Iterator[Opinion]:
    """Yield the opinions of one CAP case, stripped and ready to analyze.

    Args:
        case: A parsed CAP case JSON document.
        include_types: Opinion types to keep (``None`` keeps every type).
        min_chars: Skip opinions shorter than this after stripping.  Volume 537
            holds 5541 cases of which only 6 exceed 50k characters; the rest
            are orders and denials of certiorari, which are near-pure
            boilerplate and carry almost no running prose.
        min_year: Skip cases decided before this year.  A modern volume can
            carry a supplemental decree in a decades-old original-jurisdiction
            case -- *Nebraska v. Wyoming* (1945) and *Arizona v. California*
            (1963) both appear in volumes of the 2000s -- and that prose is
            not of the period the corpus is meant to measure.

    Yields:
        One :class:`Opinion` per opinion that passes the filters.
    """
    if min_year is not None:
        decided = str(case.get("decision_date") or "")[:4]
        if not decided.isdigit() or int(decided) < min_year:
            return

    case_id = int(case.get("id", 0))
    name = str(case.get("name_abbreviation") or case.get("name") or "")
    casebody = case.get("casebody") or {}
    opinions = casebody.get("opinions") or []

    for index, raw in enumerate(opinions):
        opinion_type = str(raw.get("type") or "unknown")
        if include_types is not None and opinion_type not in include_types:
            continue
        text = strip_citations(unbracket_insertions(strip_attribution(str(raw.get("text") or ""))))
        if len(text) < min_chars:
            continue
        author = str(raw.get("author") or "").rstrip(",")
        yield Opinion(
            case_id=case_id,
            slug=slugify_case(case_id, name, opinion_type, index),
            opinion_type=opinion_type,
            author=author,
            text=text,
        )
