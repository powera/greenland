"""Tests for Europarl parsing, cleaning, chapter selection and archive layout.

Everything here runs on inline fixtures: no network and no cached release.
The fixture mixes the two attribute styles the release uses (quoted and bare)
and a speech with no recorded language, since both occur in real files.
"""

import io
import tarfile
from pathlib import Path

from wordfreq.corpora.build_europarl import (
    NO_NAME_DETECTION,
    drop_low_ranked_capitalized,
    read_selected_chapters,
)
from wordfreq.corpora.download_europarl import extract_languages, member_target
from wordfreq.corpora.frequency_build import analyze_book
from wordfreq.corpora.europarl_select import (
    ChapterSummary,
    eligible,
    load_selection,
    select_chapters,
    selection_payload,
    write_selection,
)
from wordfreq.corpora.europarl_text import (
    chapter_slug,
    clean_paragraph,
    is_chair,
    is_procedural_title,
    parse_session,
    session_year,
    split_slug,
    strip_vocatives,
)

SESSION = """\
<CHAPTER ID="1">
Resumption of the session
<SPEAKER ID="1" NAME="President">
I declare resumed the session of the European Parliament.
(Applause)
<CHAPTER ID=2>
Fisheries agreement with Morocco
<SPEAKER ID=2 NAME="President">
The next item is the report by Mr Varela.
<SPEAKER ID="3" LANGUAGE="EN" NAME="Evans, Robert J">
Mr President, Commissioner, ladies and gentlemen, the fishermen of my region deserve better.
<P>
The Commission must listen to the Council. (Applause) The coalition agrees.
<SPEAKER ID="4" LANGUAGE="FR" NAME="Martin, David">
(FR) The amendment protects small boats.
<SPEAKER ID="5" NAME="Smith, Jane">
We support the opposition motion.
(The sitting was suspended at 12.10 p.m.)
"""


def _chapters():
    return parse_session(SESSION, "ep-00-01-17")


# --- Parsing -----------------------------------------------------------------


def test_parses_chapters_titles_and_speakers() -> None:
    chapters = _chapters()
    assert [chapter.chapter_id for chapter in chapters] == ["1", "2"]
    assert chapters[1].title == "Fisheries agreement with Morocco"
    speakers = [speech.speaker for speech in chapters[1].speeches]
    assert speakers == ["President", "Evans, Robert J", "Martin, David", "Smith, Jane"]


def test_bare_and_quoted_attributes_and_missing_language() -> None:
    """An untagged speech stays unknown: untagged is not evidence of English."""
    speeches = _chapters()[1].speeches
    assert speeches[1].language == "EN"
    assert speeches[2].language == "FR"
    assert speeches[3].language is None


DAY_FILE = """\
<CHAPTER ID=1>
Resumption of the session
<SPEAKER ID=1 NAME="President.">
I declare resumed the session.
<SPEAKER ID=2 NAME="Andrews (UEN).">
A point about the agenda.
<SPEAKER ID=3 NAME="President.">
The next item is the report (A5-0427/2002) by Giorgio Napolitano, on the role of regions.
<SPEAKER ID=4 NAME="Napolitano (PSE)." LANGUAGE="IT">
The regions deserve a voice.
<SPEAKER ID=5 NAME="President.">
The next item is the vote.
<SPEAKER ID=6 NAME="Evans (PSE).">
I voted in favour.
"""


def test_day_long_chapter_splits_at_agenda_announcements() -> None:
    chapters = parse_session(DAY_FILE, "ep-03-01-13")
    assert [chapter.chapter_id for chapter in chapters] == ["1.0", "1.1", "1.2"]
    assert chapters[0].title == "Resumption of the session"
    assert chapters[1].title.startswith("The next item is the report")
    assert "regions deserve" in chapters[1].text()
    assert chapters[1].slug == "ep-03-01-13_ch1.1"
    assert split_slug(chapters[1].slug) == ("ep-03-01-13", "1.1")
    assert is_procedural_title(chapters[2].title)
    assert not is_procedural_title(chapters[1].title)


def test_per_chapter_files_are_not_split() -> None:
    chapters = parse_session(DAY_FILE, "ep-07-01-15-003")
    assert [chapter.chapter_id for chapter in chapters] == ["1"]


def test_paragraph_tags_split_paragraphs() -> None:
    evans = _chapters()[1].speeches[1]
    assert len(evans.paragraphs) == 2


def test_session_year_and_slug_round_trip() -> None:
    assert session_year("ep-96-04-15") == 1996
    assert session_year("ep-00-01-17") == 2000
    assert session_year("ep-07-01-15-003") == 2007
    assert session_year("notes") is None
    slug = chapter_slug("ep-07-01-15-003", "2")
    assert slug == "ep-07-01-15-003_ch2"
    assert split_slug(slug) == ("ep-07-01-15-003", "2")


# --- Cleaning ----------------------------------------------------------------


def test_chapter_text_drops_chair_stage_directions_and_vocatives() -> None:
    text = _chapters()[1].text()
    assert "next item" not in text  # chair
    assert "Applause" not in text
    assert "sitting was suspended" not in text
    assert "(FR)" not in text
    assert not text.startswith("Mr President")
    assert "Commissioner, ladies" not in text
    assert "the fishermen of my region" in text
    assert "The Commission must listen to the Council." in text  # mid-speech kept


def test_language_filter_keeps_only_recorded_language() -> None:
    text = _chapters()[1].text(languages={"en"})
    assert "fishermen" in text
    assert "amendment" not in text
    assert "opposition" not in text  # no recorded language: dropped by any filter


def test_chair_detection_keeps_president_in_office() -> None:
    assert is_chair("President")
    assert is_chair("The President")
    assert is_chair("Vice-President")
    assert is_chair("President. –")
    assert not is_chair("President-in-Office of the Council")
    assert not is_chair("Evans, Robert J")


def test_vocatives_only_stripped_at_start() -> None:
    assert strip_vocatives("Madam President, I agree.") == "I agree."
    assert strip_vocatives("Mr President-in-Office of the Council, thank you.") == "thank you."
    assert strip_vocatives("I told the President, firmly.") == "I told the President, firmly."


def test_ordinary_parentheses_survive_cleaning() -> None:
    cleaned = clean_paragraph("The directive (as amended) applies.")
    assert cleaned == "The directive (as amended) applies."


def test_number_abbreviation_is_removed_but_the_word_no_is_not() -> None:
    assert "No" not in clean_paragraph("I support Amendment No 10 and Nos 4, 9.")
    assert clean_paragraph("No, we disagree.") == "No, we disagree."


def test_spaced_possessive_is_rejoined() -> None:
    assert clean_paragraph("a minute' s silence") == "a minute's silence"
    assert clean_paragraph("the members' salaries") == "the members' salaries"


def test_procedural_titles() -> None:
    for title in (
        "Resumption of the session",
        "Approval of the Minutes of the previous sitting",
        "Voting time",
        "Explanations of vote",
        "Agenda",
        "Documents received",
    ):
        assert is_procedural_title(title), title
    for title in (
        "Fisheries agreement with Morocco",
        "Question Time (Commission)",
        "Situation in Kosovo",
    ):
        assert not is_procedural_title(title), title


# --- Selection ---------------------------------------------------------------


def _summary(slug: str, year: int, words: int, title: str = "Debate") -> ChapterSummary:
    return ChapterSummary(slug=slug, year=year, title=title, words=words, translated_words=0)


def test_eligible_rejects_short_and_procedural() -> None:
    assert eligible(_summary("a_ch1", 2000, 1000), min_words=800)
    assert not eligible(_summary("a_ch2", 2000, 500), min_words=800)
    assert not eligible(_summary("a_ch3", 2000, 5000, "Voting time"), min_words=800)


def test_selection_is_year_balanced_and_redistributes_thin_years() -> None:
    summaries = [_summary(f"ep-00_ch{i}", 2000, 1000) for i in range(100)]
    summaries += [_summary(f"ep-01_ch{i}", 2001, 1000) for i in range(100)]
    summaries += [_summary("ep-96_ch1", 1996, 1000)]  # a thin year
    selected = select_chapters(summaries, target_words=21000)
    per_year = {
        year: sum(1 for item in selected if item.year == year) for year in (1996, 2000, 2001)
    }
    assert per_year[1996] == 1
    assert per_year[2000] == per_year[2001] == 10


def test_selection_is_deterministic() -> None:
    summaries = [_summary(f"ep-00_ch{i}", 2000, 1000) for i in range(50)]
    first = select_chapters(summaries, target_words=10000)
    second = select_chapters(list(reversed(summaries)), target_words=10000)
    assert [item.slug for item in first] == [item.slug for item in second]


def test_selection_file_round_trip(tmp_path: Path) -> None:
    selected = [_summary("ep-00-01-17_ch2", 2000, 1000, "Fisheries: a debate")]
    payload = selection_payload(selected, target_words=1000, min_words=800)
    path = tmp_path / "chapters.yaml"
    write_selection(payload, path, selected)
    assert load_selection(path) == ["ep-00-01-17_ch2"]


# --- Archive layout and building ---------------------------------------------


def test_member_target_filters_language_and_layout() -> None:
    assert member_target("txt/en/ep-00-01-17.txt", ["en"]) == "txt/en/ep-00-01-17.txt"
    assert member_target("europarl/txt/en/ep-00-01-17.txt", ["en"]) == "txt/en/ep-00-01-17.txt"
    assert member_target("txt/fr/ep-00-01-17.txt", ["en"]) is None
    assert member_target("tools/split-sentences.perl", ["en"]) is None


def test_extract_then_build_from_selection(tmp_path: Path) -> None:
    archive = tmp_path / "europarl.tgz"
    with tarfile.open(archive, "w:gz") as tar:
        for name, body in (("txt/en/ep-00-01-17.txt", SESSION), ("txt/fr/ep-00-01-17.txt", "x")):
            data = body.encode("utf-8")
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))

    cache = tmp_path / "cache"
    written = extract_languages(archive, cache, ["en"])
    assert written == {"en": 1}
    assert not (cache / "txt" / "fr").exists()

    documents = read_selected_chapters(cache, ["ep-00-01-17_ch2", "ep-99-01-01_ch1"], min_words=5)
    assert [slug for slug, _ in documents] == ["ep-00-01-17_ch2"]
    assert "fishermen" in documents[0][1]


def test_low_ranked_capitalized_entries_are_dropped_and_list_refilled() -> None:
    frequencies = {"the": 100, "European": 90, "I": 80, "vote": 70, "Barroso": 60, "quota": 50}
    kept, dropped = drop_low_ranked_capitalized(frequencies, max_rank=2, max_words=4)
    assert kept == {"the": 100, "European": 90, "I": 80, "vote": 70}
    assert dropped == 0
    kept, dropped = drop_low_ranked_capitalized(frequencies, max_rank=4, max_words=5)
    assert list(kept) == ["the", "European", "I", "vote", "quota"]
    assert dropped == 1


def test_name_detection_off_keeps_capitalized_words() -> None:
    text = "We ask the Commission and the Council to act. " * 6
    assert "commission" in analyze_book("plain", text).names
    kept = analyze_book("europarl", text, capitalization_ratio=NO_NAME_DETECTION)
    assert not kept.names
    assert "commission" in kept.content_counts
