"""Tests for wikitext-to-prose extraction.

Narrow by design: these cover ``<math>`` stripping, which is what put ``frac``,
``mathbf`` and ``cdot`` into the wiki_math corpus as if they were English.
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
