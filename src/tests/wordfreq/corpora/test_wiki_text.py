"""Tests for wikitext-to-prose extraction.

Narrow by design: these cover HTML tag handling, which is what put ``frac``,
``mathbf`` and ``cdot`` (from ``<math>``) and ``sub``, ``sup`` and ``small``
(from the tags of those names) into the wiki corpora as if they were English.
"""

from wordfreq.corpora.wikipedia.wiki_text import wikitext_to_plain_text


def test_math_tags_contribute_no_text() -> None:
    """A formula is LaTeX, not prose, and must not reach the word counts."""
    text = wikitext_to_plain_text(
        r"The area is <math>A = \frac{1}{2} \mathbf{b} \cdot h</math> for a triangle."
    )
    for control_sequence in ("frac", "mathbf", "cdot"):
        assert control_sequence not in text
    # The surrounding prose survives.
    assert "The area is" in text
    assert "for a triangle" in text


def test_math_variants_are_all_stripped() -> None:
    """Attributes, <chem>, and nested braces must not defeat the block."""
    # Each case pairs the wikitext with the words that must survive it, so the
    # assertion is on whole words: "int" as a substring also matches the
    # "integral" that is legitimately part of the prose.
    cases = [
        (r'A <math display="block">\int_0^\infty e^{-x}dx</math> integral.', {"a", "integral"}),
        (r"Nested <math>\sqrt{\frac{a}{b}}</math> braces.", {"nested", "braces"}),
        (r"Water is <chem>H2O</chem> here.", {"water", "is", "here"}),
    ]
    for case, expected in cases:
        text = wikitext_to_plain_text(case)
        assert "<" not in text, f"tag survived in {text!r}"
        words = {word.strip(".,") for word in text.lower().split()}
        assert words == expected, f"{case!r} produced {words}"


def test_prose_without_math_is_untouched() -> None:
    assert "No math here at all." in wikitext_to_plain_text("No math here at all.")


def test_prose_tags_are_dropped_but_their_text_kept() -> None:
    """A tag name is markup, not a word.

    ``<sub>`` and ``<sup>`` reached the text verbatim and were counted as
    English: 3494 and 1980 occurrences in the wiki_math corpus.  ``<small>``
    is worse, because it inflates a word that genuinely exists.
    """
    text = wikitext_to_plain_text(
        "Water is H<sub>2</sub>O, E<sup>2</sup> holds, and a <small>tiny</small> "
        '<span style="color:red">red</span> word.'
    )
    assert "<" not in text
    words = {word.strip(".,") for word in text.lower().split()}
    for tag_name in ("sub", "sup", "small", "span"):
        assert tag_name not in words, f"{tag_name!r} counted as a word in {text!r}"
    # The prose the tags wrapped survives.
    assert {"water", "tiny", "red", "word"} <= words


def test_void_tags_separate_the_words_around_them() -> None:
    """A line break must not glue its neighbours into one token."""
    text = wikitext_to_plain_text("One<br>two<br />three.")
    assert text.split() == ["One", "two", "three."]


def test_opaque_tags_drop_their_body() -> None:
    """A gallery is filenames and a highlight block is source code."""
    cases = [
        "Before <gallery>File:A.jpg|Caption\nFile:B.jpg</gallery> after.",
        'Before <syntaxhighlight lang="python">def small(): pass</syntaxhighlight> after.',
    ]
    for case in cases:
        words = {word.strip(".,") for word in wikitext_to_plain_text(case).lower().split()}
        assert words == {"before", "after"}, f"{case!r} produced {words}"


def test_nowiki_keeps_its_body_as_literal_text() -> None:
    """The point of the tag is that the markup inside it is not markup."""
    text = wikitext_to_plain_text("Text <nowiki>{{foo}} and [[bar]]</nowiki> more.")
    assert "nowiki" not in text
    assert "{{foo}}" in text
    assert "[[bar]]" in text


def test_unrecognized_tags_do_not_reach_the_text() -> None:
    """An unknown tag is still markup; only the prose it wraps is kept."""
    text = wikitext_to_plain_text("A <foobar>weird</foobar> tag.")
    assert "foobar" not in text
    assert "weird" in text


def test_unclosed_opaque_tag_does_not_swallow_the_article() -> None:
    """A missing close must cost one construct, not the whole page."""
    text = wikitext_to_plain_text(
        "Before <gallery>File:A.jpg\n\nA whole paragraph of real prose.\n\nAnother one."
    )
    assert "A whole paragraph of real prose." in text
    assert "Another one." in text


def test_stray_closing_tag_does_not_open_a_new_block() -> None:
    """The close left behind by the "\\n\\n" guard must not reopen the block.

    A taxobox whose ``image`` argument holds an ``<imagemap>`` with a blank
    line in it: the guard force-closes the imagemap at the blank line, so its
    real ``</imagemap>`` arrives with nothing to close.  Matching it on the tag
    name alone would open a second opaque block, which then eats the ``}}`` and
    leaves the template open over the rest of the page -- which is what cost
    "Animal", "Bird" and "Mammal" their entire text.
    """
    text = wikitext_to_plain_text(
        "{{automatic taxobox\n"
        "| image = <imagemap>\n"
        "File:Animal diversity.png |300px\n"
        "\n"
        "rect 0 0 118 86 [[Echinoderm]]\n"
        "</imagemap>\n"
        "}}\n"
        "\n"
        "Animals are multicellular eukaryotic organisms.\n"
    )
    assert "Animals are multicellular eukaryotic organisms." in text
    # The imagemap's own body is apparatus and stays out of the prose.
    assert "Echinoderm" not in text
    assert "300px" not in text
