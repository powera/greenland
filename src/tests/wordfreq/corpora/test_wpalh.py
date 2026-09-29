"""Tests for the WPA life-histories text cleanup and corpus build helpers.

The PDFs are OCR of 1930s typescript, and each cleanup step has a failure in
both directions: stripping too little puts questionnaire prompts, page headers
or misreadings ("tne") into an English frequency list; stripping too much eats
dialogue.  Both directions are asserted below.
"""

from collections import Counter

from wordfreq.corpora.build_wpalh import remove_pooled_names
from wordfreq.corpora.frequency_build import analyze_book
from wordfreq.corpora.wpalh_text import (
    apply_ocr_corrections,
    build_ocr_corrections,
    clean_pages,
    dialect_share,
    is_form_page,
    is_header_line,
    slugify_item,
)

FORM_A = """Forms to be Filled out for Each Interview
FORM A
Circumstances of Interview
STATE Illinois
NAME OF WORKER Abe Aaron
1. Date and time of interview May 12
2. Place of interview
3. Name and address of informant
"""

# --- Questionnaire pages ---------------------------------------------------------


def test_form_page_is_dropped() -> None:
    assert is_form_page(FORM_A)


def test_form_page_survives_one_mangled_prompt() -> None:
    page = "FORN ,\nNAME OF VORKER X\nPlace and date of birth\nDescription of informant\n"
    assert is_form_page(page)


def test_text_page_with_one_label_is_kept() -> None:
    page = "FORM C\nText of Interview\nNAME OF WORKER Abe Aaron\nWe sold papers on the corner.\n"
    assert not is_form_page(page)


# --- Header lines ----------------------------------------------------------------


def test_header_lines_are_dropped() -> None:
    for line in [
        "STATE New York",
        "NAME OF WORKER Wayne Walden",
        "FOLKLORE",
        "Written By: Mrs. Ina B. Hawkes",
        "Georgia Writers' Project",
        "Noakes Page 2",
        "Pilaw - 2",
        "W15075",
        "!! ,.; -- 12 ::",
        "INTERVIEW WITH JOHN LOVETT",
        "3. Name and address of informant Charles Brown, Canyon City",
        "Name of Person Interviewed Ti, 8, Maur. (white)",
    ]:
        assert is_header_line(line), line


def test_prose_and_dialogue_are_kept() -> None:
    for line in [
        "Gus:- Naw you got me all wrong.",
        "State fairs were the big thing then.",
        "Date palms don't grow up here.",
        "I was 12 years old.",
        "I",
        "OK",
    ]:
        assert not is_header_line(line), line


def test_clean_pages_drops_forms_and_joins_hyphenated_words() -> None:
    text = clean_pages([FORM_A, "STATE Illinois\nDo you re-\nmember the fire?\n"])
    assert "Circumstances" not in text
    assert "STATE" not in text
    assert "remember the fire" in text


def test_clean_pages_keeps_dash_before_capital() -> None:
    text = clean_pages(["He said-\nThen he left."])
    assert "said-" in text


# --- Dialect ---------------------------------------------------------------------


def test_dialect_share_counts_markers() -> None:
    assert dialect_share("dey gwine home to see de chillun") == 3 / 7


def test_dialect_share_ignores_ordinary_colloquial_speech() -> None:
    assert dialect_share("we was goin' to see 'em about the chile peppers") == 0.0


# --- OCR corrections -------------------------------------------------------------

# Each known word mapped to its best rank in the other corpora.
KNOWN = {"the": 1, "and": 2, "she": 30, "could": 60, "those": 150, "ant": 9000, "hose": 5000}


def _counts() -> Counter[str]:
    return Counter(
        {"the": 5000, "could": 400, "those": 300, "and": 3000, "she": 900, "ant": 3}
        | {"tne": 40, "oould": 12, "hose": 20, "ani": 30, "sho": 50, "zzq": 2}
    )


def test_corrects_letter_confusions() -> None:
    corrections = build_ocr_corrections(_counts(), KNOWN)
    assert corrections["tne"] == "the"
    assert corrections["oould"] == "could"


def test_known_word_needs_twenty_to_one_evidence() -> None:
    # "hose" ranks far higher here than elsewhere, but "those" is only 15
    # times as frequent: it may be meant, so it is left alone.
    assert "hose" not in build_ocr_corrections(_counts(), KNOWN)


def test_overrepresented_known_word_is_corrected() -> None:
    # 2,476 "ant"s in the collection, all of them "and" when sampled.
    counts = Counter({"the": 9000, "and": 6000, "ant": 100, "cattle": 300})
    known = {"the": 1, "and": 2, "ant": 9000, "cattle": 2000}
    assert build_ocr_corrections(counts, known)["ant"] == "and"


def test_known_word_ranked_as_elsewhere_is_never_corrected() -> None:
    # "ant" is no commoner here than in the other corpora.
    counts = Counter({"the": 9000, "and": 6000, "ant": 100})
    assert "ant" not in build_ocr_corrections(counts, {"the": 1, "and": 2, "ant": 5})


def test_never_corrects_a_dialect_spelling() -> None:
    assert "sho" not in build_ocr_corrections(_counts(), KNOWN)


def test_correction_target_must_be_frequent() -> None:
    counts = _counts()
    # "ani" is a confusion away from "ant", but "ant" is far down the list.
    assert "ani" not in build_ocr_corrections(counts, KNOWN, max_target_rank=5)


def test_restores_a_first_letter_lost_at_the_margin() -> None:
    counts = Counter({"after": 800, "fter": 30})
    assert build_ocr_corrections(counts, {"after": 70})["fter"] == "after"


def test_apply_keeps_capital_and_deletes_fragments() -> None:
    corrections = {"tne": "the"}
    text = apply_ocr_corrections("Tne dog and tne tt cat", corrections, {"the", "dog", "cat"})
    assert text.split() == ["The", "dog", "and", "the", "cat"]


# --- Names -----------------------------------------------------------------------


def test_pooled_names_catch_informants_named_rarely_per_interview() -> None:
    # Two mid-sentence mentions per interview: too few for analyze_book's
    # per-document test (four), plenty once the four interviews are pooled.
    analyses = [
        analyze_book(
            f"doc{index}",
            "We met with Lovett at the store. Then we talked to Lovett about hay.",
        )
        for index in range(4)
    ]
    assert all("lovett" in analysis.content_counts for analysis in analyses)
    moved = remove_pooled_names(analyses)
    assert moved["lovett"] == 8
    assert all("lovett" not in analysis.content_counts for analysis in analyses)
    assert all(analysis.names["lovett"] == 2 for analysis in analyses)
    assert "store" in analyses[0].content_counts


def test_slugify_item() -> None:
    assert slugify_item("wpalh-07030116", "[Newsboys]") == "wpalh-07030116_Newsboys"
    assert slugify_item("wpalh-1", "") == "wpalh-1"
