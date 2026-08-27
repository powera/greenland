"""Tests for Supreme Court opinion extraction and citation stripping.

The citation patterns carry most of the risk here: an opinion is about 5%
citation apparatus by word, and the two failure directions are opposite.
Under-stripping leaves reporter abbreviations ("stat", "ibid", "ante") in an
English frequency list; over-stripping eats the prose around them, which is
how an early version of the run rule removed the dates and quantities from
"In 1998, Congress enlarged the duration by 20 years."  Both directions are
asserted below.
"""

from wordfreq.corpora.gutenberg_text import analyze_text, iter_tokens
from wordfreq.corpora.scotus_text import (
    iter_opinions,
    slugify_case,
    strip_attribution,
    strip_citations,
    unbracket_insertions,
)


def _tokens(text: str) -> list:
    return [token for token, _, _ in iter_tokens(text)]


# --- Citations that must be removed -----------------------------------------


def test_strips_full_reporter_citation() -> None:
    stripped = strip_citations("We granted certiorari. 534 U. S. 1112 (2002).")
    assert "534" not in stripped
    assert "1112" not in stripped
    assert "certiorari" in stripped


def test_strips_statute_and_section() -> None:
    stripped = strip_citations("The Act, 17 U. S. C. § 302(a), applies here.")
    assert "302" not in stripped
    assert "§" not in stripped
    assert "applies here" in stripped


def test_strips_state_statute_run_without_naming_the_state() -> None:
    """The run rule is what covers jurisdictions, which are open-ended.

    There is no list of "La." or "Nev." in the module: a run of two or more
    abbreviations is apparatus regardless of which state it names.
    """
    stripped = strip_citations("See La. Rev. Stat. Ann. §§27:301, 27:306 (2000).")
    for fragment in ("La.", "Rev.", "Stat.", "Ann.", "27:301"):
        assert fragment not in stripped


def test_strips_latin_cross_references() -> None:
    stripped = strip_citations("It follows. Id., at 257. See also Ibid. and supra, at 12.")
    tokens = _tokens(stripped)
    for apparatus in ("id", "ibid", "supra", "ante"):
        assert apparatus not in tokens


def test_strips_session_laws_and_public_laws() -> None:
    stripped = strip_citations("Pub. L. 105-298, 112 Stat. 2827, changed the term.")
    assert "stat" not in _tokens(stripped)
    assert "changed the term" in stripped


def test_strips_isolated_abbreviations() -> None:
    """Singletons have no neighbour, so the run rule cannot reach them."""
    stripped = strip_citations("See Widget Co. and Gadget Inc. and Cf. Brown.")
    tokens = _tokens(stripped)
    for abbreviation in ("co", "inc", "cf"):
        assert abbreviation not in tokens


# --- Prose that must survive -------------------------------------------------


def test_keeps_numbers_in_ordinary_prose() -> None:
    """Bare numbers may join an apparatus run but must never anchor one."""
    text = "In 1998, Congress enlarged the duration by 20 years."
    assert strip_citations(text) == text


def test_keeps_prose_containing_a_citation_signal_word() -> None:
    text = "The Court held that Congress may not act, and 12 States agreed."
    assert strip_citations(text) == text


def test_keeps_latin_set_phrases() -> None:
    """ "deus ex machina" is vocabulary; "Ex parte" in a case name is not."""
    assert "deus ex machina" in strip_citations("a deus ex machina to extract")


def test_keeps_case_names() -> None:
    """Party names stay in: the capitalization rule classifies them as names.

    Removing them here would take the surrounding syntax with them, and the
    per-book proper-noun detector already routes them to ``name_frequency``.
    """
    stripped = strip_citations("We said as much in Barnhart v. Peabody Coal Co.")
    assert "Barnhart" in stripped
    assert "Peabody" in stripped


# --- Editorial brackets ------------------------------------------------------


def test_unbrackets_word_internal_insertions() -> None:
    """Brackets are tokenizer boundaries, so "[w]hen" would count as "hen"."""
    assert _tokens(unbracket_insertions("“[w]hen it applies")) == ["when", "it", "applies"]
    assert _tokens(unbracket_insertions("they see[k] relief")) == ["they", "seek", "relief"]
    assert _tokens(unbracket_insertions("restrain[ed] here")) == ["restrained", "here"]


def test_unbrackets_whole_word_substitutions() -> None:
    assert "the Secretary" in unbracket_insertions("[the Secretary’s] duty")


def test_drops_brackets_holding_no_letters() -> None:
    """A spaced ellipsis has no word in it to keep."""
    assert _tokens(unbracket_insertions("the [. . .] statute")) == ["the", "statute"]


# --- Opinion extraction ------------------------------------------------------

CASE = {
    "id": 12345,
    "name_abbreviation": "Smith v. Jones",
    "decision_date": "2003-01-15",
    "casebody": {
        "opinions": [
            {
                "type": "majority",
                "author": "Justice Ginsburg",
                "text": "Justice Ginsburg\ndelivered the opinion of the Court.\n"
                "The statute applies to every operator. See 534 U. S. 1112 (2002).",
            },
            {"type": "dissent", "author": "Justice Stevens,", "text": "I respectfully dissent."},
        ]
    },
}


def test_iter_opinions_yields_each_opinion() -> None:
    opinions = list(iter_opinions(CASE))
    assert [opinion.opinion_type for opinion in opinions] == ["majority", "dissent"]
    assert opinions[0].author == "Justice Ginsburg"


def test_iter_opinions_strips_attribution_and_citations() -> None:
    majority = next(iter_opinions(CASE))
    assert "delivered the opinion" not in majority.text
    assert "1112" not in majority.text
    assert "statute applies to every operator" in majority.text


def test_iter_opinions_filters_by_type_and_length() -> None:
    assert len(list(iter_opinions(CASE, include_types=["majority"]))) == 1
    assert list(iter_opinions(CASE, min_chars=10_000)) == []


def test_iter_opinions_filters_by_year() -> None:
    """Modern volumes carry supplemental decrees in decades-old cases."""
    assert list(iter_opinions(CASE, min_year=2010)) == []
    assert len(list(iter_opinions(CASE, min_year=1997))) == 2


def test_strip_attribution_handles_dissents() -> None:
    assert strip_attribution("Justice Breyer, dissenting. The Court errs.") == "The Court errs."


def test_slugify_case_is_stable_and_filesystem_safe() -> None:
    slug = slugify_case(12345, "Smith v. Jones", "majority", 0)
    assert slug == "12345_Smith_v_Jones_majority"


# --- End to end --------------------------------------------------------------


def test_analyzed_opinion_has_no_citation_residue() -> None:
    """The whole point: apparatus must not reach the frequency counts."""
    majority = next(iter_opinions(CASE))
    counts = analyze_text(majority.text).counts
    for apparatus in ("stat", "id", "ibid", "ante", "supra", "cf"):
        assert counts[apparatus] == 0
    assert counts["statute"] == 1
