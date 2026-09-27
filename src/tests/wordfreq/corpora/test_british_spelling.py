"""Tests for folding British spellings onto American ones.

The rules over-generate on purpose; the reference set is what stops a fold
turning one real word into another ("filled" -> "filed").  Both directions are
asserted: folds that must happen, and near-misses that must not.
"""

from wordfreq.corpora.british_spelling import (
    american_candidates,
    build_spelling_map,
    fold_text,
    vocabulary,
)

KNOWN = {
    "program",
    "programs",
    "labeling",
    "organize",
    "organization",
    "honor",
    "honorable",
    "center",
    "centered",
    "defense",
    "traveled",
    "analyze",
    "fulfill",
    "pediatric",
    # Real words the rules could wrongly produce, or real words themselves.
    "fill",
    "filled",
    "filed",
    "morning",
    "canes",
    "for",
    "promise",
}


def test_regular_folds() -> None:
    words = [
        "programme",
        "programmes",
        "labelling",
        "organise",
        "organisation",
        "honour",
        "honourable",
        "centre",
        "centred",
        "defence",
        "travelled",
        "analyse",
        "paediatric",
    ]
    mapping = build_spelling_map(words, KNOWN)
    assert mapping == {
        "programme": "program",
        "programmes": "programs",
        "labelling": "labeling",
        "organise": "organize",
        "organisation": "organization",
        "honour": "honor",
        "honourable": "honorable",
        "centre": "center",
        "centred": "centered",
        "defence": "defense",
        "travelled": "traveled",
        "analyse": "analyze",
        "paediatric": "pediatric",
    }


def test_irregular_fold() -> None:
    assert build_spelling_map(["fulfil"], KNOWN) == {"fulfil": "fulfill"}


def test_known_word_never_folds_into_another() -> None:
    """ "filled" is a form of fill, so -lled -> -led must not make it "filed"."""
    assert build_spelling_map(["filled", "promise"], KNOWN) == {}


def test_rules_that_would_mangle_ordinary_words() -> None:
    assert "morning" not in american_candidates("mourning")
    assert "canes" not in american_candidates("canoes")
    assert american_candidates("four") == []  # too short for a rule


def test_french_words_do_not_fold_like_centre() -> None:
    """Seen in Europarl: entre -> enter, votre -> voter, lettre -> letter."""
    known = KNOWN | {"enter", "voter", "letter", "outer", "scoring", "prize"}
    words = ["entre", "votre", "lettre", "outre", "scouring", "prise", "kilometre"]
    assert build_spelling_map(words, known | {"kilometer"}) == {"kilometre": "kilometer"}


def test_unknown_target_does_not_fold() -> None:
    assert build_spelling_map(["colour"], KNOWN) == {}


def test_fold_text_keeps_case_and_leaves_other_words() -> None:
    mapping = {"programme": "program", "honour": "honor"}
    text = "The Programme is an HONOUR; the programme's aims."
    assert fold_text(text, mapping) == "The Program is an HONOR; the program's aims."


def test_vocabulary_is_lowercase_words() -> None:
    assert vocabulary(["The Programme, 2006.", "programme"]) == {"the", "programme"}
