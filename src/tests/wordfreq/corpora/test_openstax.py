"""Tests for OpenStax text extraction, the pinned book list and the builder's name rule.

Everything here runs on inline CNXML fixtures: no network and no checkout.
The fixtures copy the markup the real books use, including the apparatus the
extractor has to drop.
"""

from collections import Counter
from pathlib import Path

import pytest

from wordfreq.corpora.build_openstax import capitalized_spread, drop_narrow_capitalized
from wordfreq.corpora.download_openstax import collection_path, license_problems
from wordfreq.corpora.frequency_build import BookAnalysis
from wordfreq.corpora.gutenberg_text import TextStats
from wordfreq.corpora.openstax_books import (
    OPENSTAX_CORPORA,
    OpenStaxBook,
    get_books,
    repo_pins,
)
from wordfreq.corpora.openstax_text import (
    chapter_slug,
    module_text,
    parse_collection,
    read_chapters,
    split_chapter_slug,
    strip_caption_credit,
)

COLLECTION = """\
<col:collection xmlns="http://cnx.rice.edu/collxml" xmlns:md="http://cnx.rice.edu/mdml"
    xmlns:col="http://cnx.rice.edu/collxml">
  <metadata>
    <md:title>Test Book</md:title>
    <md:license url="http://creativecommons.org/licenses/by/4.0/">CC BY</md:license>
  </metadata>
  <col:content>
    <col:module document="m00001"/>
    <col:subcollection>
      <md:title>Unit One</md:title>
      <col:content>
        <col:subcollection>
          <md:title>Kinematics</md:title>
          <col:content>
            <col:module document="m00010"/>
            <col:module document="m00011"/>
          </col:content>
        </col:subcollection>
      </col:content>
    </col:subcollection>
    <col:subcollection>
      <md:title>Dynamics</md:title>
      <col:content>
        <col:module document="m00020"/>
      </col:content>
    </col:subcollection>
    <col:module document="m00099"/>
  </col:content>
</col:collection>
"""


def _module(body: str, *, title: str = "A Section", document_class: str = "") -> str:
    class_attr = f' class="{document_class}"' if document_class else ""
    return f"""\
<document xmlns="http://cnx.rice.edu/cnxml" xmlns:m="http://www.w3.org/1998/Math/MathML"{class_attr}>
<title>{title}</title>
<metadata xmlns:md="http://cnx.rice.edu/mdml">
  <md:title>{title}</md:title>
  <md:abstract><para id="a1">By the end of this section, you will be able to:</para></md:abstract>
</metadata>
<content>
{body}
</content>
</document>
"""


# --- Collections -------------------------------------------------------------


def test_chapters_are_subcollections_that_list_modules() -> None:
    """A unit is walked through; modules outside any chapter are not read."""
    chapters = parse_collection(COLLECTION)
    assert [(chapter.number, chapter.title) for chapter in chapters] == [
        (1, "Kinematics"),
        (2, "Dynamics"),
    ]
    assert chapters[0].module_ids == ["m00010", "m00011"]


def test_chapter_slug_round_trip() -> None:
    slug = chapter_slug("us_history", 7)
    assert slug == "us_history/07"
    assert split_chapter_slug(slug) == ("us_history", 7)


# --- Module text -------------------------------------------------------------


def test_keeps_prose_and_the_text_after_a_skipped_element() -> None:
    text = module_text(
        _module(
            '<para id="p1">Velocity is <emphasis effect="italics">speed</emphasis> with a '
            "direction, about <m:math><m:mn>10</m:mn></m:math> meters per second.</para>"
        )
    )
    assert text == "Velocity is speed with a direction, about meters per second."


def test_titles_labels_and_the_abstract_are_dropped() -> None:
    text = module_text(
        _module(
            '<section id="s1"><title>PATRONAGE: THE SPOILS SYSTEM</title>'
            '<para id="p1">Patronage was the heart of each administration.</para></section>',
            title="The Key Political Issues",
        )
    )
    assert text == "Patronage was the heart of each administration."


def test_classed_sections_and_exercises_are_dropped() -> None:
    text = module_text(
        _module(
            '<para id="p1">Kept.</para>'
            '<section class="review-questions" id="s1"><para id="p2">Which of these?</para>'
            "</section>"
            '<section class="summary" id="s2"><para id="p3">Summary text.</para></section>'
            '<section id="s3"><title>Learning Objectives</title>'
            '<para id="p4">By the end of this section you should be able to</para></section>'
            '<exercise id="e1"><problem id="q1"><para id="p5">Solve it.</para></problem>'
            "</exercise>"
        )
    )
    assert text == "Kept."


def test_note_classes_decide_whether_a_feature_is_prose() -> None:
    text = module_text(
        _module(
            '<note class="microbiology clinical-focus" id="n1"><title>Part 1</title>'
            '<para id="p1">A patient arrives with a fever.</para></note>'
            '<note class="history click-and-explore" id="n2">'
            '<para id="p2">Explore the archive online.</para></note>'
            '<para id="p3">Half of Congress are millionaires.<cite target-id="rf-1">'
            '<note class="reference" id="rf-1">Karl Evers-Hillstrom, "Majority," 2020.</note>'
            "</cite></para>"
        )
    )
    assert text == "A patient arrives with a fever.\nHalf of Congress are millionaires."


def test_code_is_dropped_but_its_surrounding_prose_kept() -> None:
    text = module_text(
        _module(
            '<para id="p1">The built-in function <code>ord()</code> converts a character.</para>'
            '<code class="python" display="block"># Import pandas\nimport pandas as pd</code>'
        )
    )
    assert text == "The built-in function converts a character."


def test_link_only_paragraphs_and_navigation_are_dropped() -> None:
    text = module_text(
        _module(
            '<para id="p1"><link url="https://www.youtube.com/embed/x">OpenStax AP Physics '
            "Chapter 4: Newton's Laws Physics Concept Trailer</link></para>"
            '<para id="p2">See <link url="https://example.org">the survey</link> results.</para>'
            '<para id="p3"><emphasis effect="italics">Jump to the <link target-id="x">next</link>'
            " Clinical Focus box.</emphasis></para>"
        )
    )
    assert text == "See the survey results."


def test_empty_cross_reference_parentheses_are_removed() -> None:
    text = module_text(
        _module(
            '<para id="p1">The Wizard of Oz (<link target-id="Figure_1"/>), was published.</para>'
        )
    )
    assert text == "The Wizard of Oz, was published."


@pytest.mark.parametrize(
    "caption, expected",
    [
        (
            "An American kestrel in flight. (credit: Vince Maidens, Wikimedia Commons)",
            "An American kestrel in flight.",
        ),
        (
            'credit: modification of work "Port of Melbourne", by Chris Phutully/Flickr, CC BY 2.0',
            "",
        ),
        (
            "Energy flows through the cell. Credit: Rao, A., Ryan, K. Department of Biology",
            "Energy flows through the cell.",
        ),
        (
            "Two stains. Image credit: Golgi: By MethoxyRoxy, CC BY-SA 2.5, https://commons.wikimedia.org",
            "Two stains.",
        ),
        (
            "(a) Helical (b) polyhedral. (credit a “micrograph”: modification of work by USDA ARS)",
            "(a) Helical (b) polyhedral.",
        ),
        (
            "Food from microbes. (credit bread: modification of work by F. Rodrigo)",
            "Food from microbes.",
        ),
        (
            "Two cells. (attribution: Biology 2e, Rice University, OpenStax, under CC BY 4.0 license)",
            "Two cells.",
        ),
        (
            "Koch is credited with pure culture techniques.",
            "Koch is credited with pure culture techniques.",
        ),
    ],
)
def test_caption_credits(caption: str, expected: str) -> None:
    assert strip_caption_credit(caption).strip() == expected


def test_caption_credit_is_stripped_inside_a_figure() -> None:
    text = module_text(
        _module(
            '<figure id="f1"><media alt="A cartoon."><image src="x.jpg"/></media>'
            "<caption>Jackson riding a pig. (credit: Library of Congress)</caption></figure>"
            '<para id="p1">The spoils system followed.</para>'
        )
    )
    assert text == "Jackson riding a pig.\nThe spoils system followed."


def test_front_matter_and_summary_modules_are_skipped() -> None:
    assert module_text(_module('<para id="p1">Welcome.</para>', document_class="preface")) == ""
    assert module_text(_module('<para id="p1">Recap.</para>', title="Chapter summary")) == ""
    assert module_text(_module('<para id="p1">Opener.</para>', document_class="introduction"))


def test_read_chapters_joins_modules_and_skips_missing_ones(tmp_path: Path) -> None:
    collection = tmp_path / "collections" / "test.collection.xml"
    collection.parent.mkdir()
    collection.write_text(COLLECTION, encoding="utf-8")
    modules = tmp_path / "modules"
    for module_id, sentence in [("m00010", "First part."), ("m00011", "Second part.")]:
        (modules / module_id).mkdir(parents=True)
        (modules / module_id / "index.cnxml").write_text(
            _module(f'<para id="p1">{sentence}</para>'), encoding="utf-8"
        )

    chapters = list(read_chapters(collection, modules, "physics"))

    # m00020, the only module of chapter 2, is not checked out.
    assert chapters == [("physics/01", "First part.\nSecond part.")]


# --- The book list -----------------------------------------------------------


def test_every_book_is_pinned_to_a_full_commit_and_slugs_are_unique() -> None:
    books = get_books("all")
    assert all(len(book.commit) == 40 for book in books)
    slugs = [book.slug for book in books]
    assert len(slugs) == len(set(slugs))
    assert "/" not in "".join(slugs)
    repo_pins(books)  # one commit per repository, across both corpora


def test_two_pins_in_one_repository_are_refused() -> None:
    first = OpenStaxBook("a", "A", "osbooks-x", "a.collection.xml", "1" * 40, "2026-01-01")
    second = OpenStaxBook("b", "B", "osbooks-x", "b.collection.xml", "2" * 40, "2026-01-01")
    with pytest.raises(ValueError):
        repo_pins((first, second))


def test_unknown_corpus_is_refused() -> None:
    assert set(OPENSTAX_CORPORA) == {"openstax_science", "openstax_society", "openstax_business"}
    with pytest.raises(ValueError):
        get_books("openstax_nursing")


def test_license_check_requires_cc_by(tmp_path: Path) -> None:
    by = OpenStaxBook("by", "By", "osbooks-by", "by.collection.xml", "1" * 40, "2026-01-01")
    nc = OpenStaxBook("nc", "Nc", "osbooks-nc", "nc.collection.xml", "2" * 40, "2026-01-01")
    missing = OpenStaxBook("gone", "Gone", "osbooks-gone", "g.collection.xml", "3" * 40, "")
    collection_path(tmp_path, by).parent.mkdir(parents=True)
    collection_path(tmp_path, by).write_text(COLLECTION, encoding="utf-8")
    collection_path(tmp_path, nc).parent.mkdir(parents=True)
    collection_path(tmp_path, nc).write_text(
        COLLECTION.replace("licenses/by/4.0", "licenses/by-nc-sa/4.0"), encoding="utf-8"
    )

    problems = license_problems(tmp_path, (by, nc, missing))

    assert [problem.split(":")[0] for problem in problems] == ["nc", "gone"]


# --- Capitalized entries must spread -----------------------------------------


def _analysis(slug: str, upper: dict[str, int]) -> BookAnalysis:
    return BookAnalysis(slug=slug, stats=TextStats(), upper_counts=Counter(upper))


def test_capitalized_entries_must_spread_across_chapters_and_books() -> None:
    analyses = [
        _analysis("us_history/10", {"lincoln": 30, "conkling": 12}),
        _analysis("us_history/11", {"lincoln": 20}),
        _analysis("us_history/12", {"lincoln": 5}),
        _analysis("american_government/02", {"lincoln": 3}),
        _analysis("us_history/20", {"blaine": 9}),
        _analysis("us_history/21", {"blaine": 4}),
        _analysis("us_history/22", {"blaine": 2}),
        _analysis("us_history/23", {"blaine": 2}),
    ]
    spread = capitalized_spread(analyses)
    assert spread["lincoln"] == (4, 2)
    assert spread["blaine"] == (4, 1)

    frequencies = {"the": 900, "I": 50, "Lincoln": 40, "Blaine": 30, "Conkling": 20, "war": 10}
    kept, dropped = drop_narrow_capitalized(
        frequencies, spread, min_chapters=4, min_books=2, max_words=4
    )

    assert list(kept) == ["the", "I", "Lincoln", "war"]
    assert dropped == ["Blaine", "Conkling"]
