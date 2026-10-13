"""Tests for the LLM level-outlier scan: prompt building and answer matching."""

from typing import Any, Dict, List, Optional

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from reports.curriculum_bands import UNRANKED_SENTINEL
from storage.models.curriculum_level import CurriculumLevel
from storage.models.schema import Base, Lemma
from wordfreq.data.cohorts import US_STATES
from quality.level_outliers import (
    OUTLIER_JSON_SCHEMA,
    build_context,
    build_prompt,
    describe_word,
    levels_in_band,
    neighbour_levels,
    parse_outliers,
    scan_level,
)


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def _lemma(
    session: Session,
    text: str,
    level: int,
    definition: str = "",
    rank: Optional[int] = 3000,
    disambiguation: Optional[str] = None,
) -> Lemma:
    lemma = Lemma(
        lemma_text=text,
        definition_text=definition or f"a {text}",
        pos_type="noun",
        pos_subtype="sport_equipment",
        difficulty_level=level,
        guid=f"N_{text}_{session.query(Lemma).count()}",
        frequency_rank=rank,
        disambiguation=disambiguation,
    )
    session.add(lemma)
    session.flush()
    return lemma


def _sports_level(session: Session) -> List[Lemma]:
    session.add(CurriculumLevel(level=210, name="Sports Equipment", cefr="A2"))
    return [
        _lemma(session, "ball", 210, rank=900),
        _lemma(session, "bat", 210, "a flying mammal", rank=4000, disambiguation="animal"),
        _lemma(session, "bat", 210, "a club for hitting a ball", rank=4001),
        _lemma(session, "sphygmomanometer", 210, rank=None),
    ]


def test_word_line_carries_pos_sense_definition_and_rank() -> None:
    session = _session()
    words = _sports_level(session)
    assert (
        describe_word(2, words[1])
        == "2. bat (noun/sport_equipment) [animal]: a flying mammal | rank 4000"
    )
    assert describe_word(4, words[3]).endswith("| rank unranked")
    words[0].frequency_rank = UNRANKED_SENTINEL
    assert describe_word(1, words[0]).endswith("| rank unranked")


def test_prompt_numbers_every_word_and_fills_placeholders() -> None:
    session = _session()
    words = _sports_level(session)
    prompt = build_prompt(210, "Sports Equipment", "A2", words)
    assert "Title: Sports Equipment" in prompt
    assert "Band: named" in prompt
    assert "4. sphygmomanometer" in prompt
    assert "{{" not in prompt and "{{" not in build_context()


def test_untitled_level_says_so() -> None:
    assert "Title: (no title yet)" in build_prompt(1150, None, None, [])


def test_parse_matches_by_number_and_keeps_two_senses_apart() -> None:
    session = _session()
    words = _sports_level(session)
    scan = parse_outliers(
        {
            "outliers": [
                {
                    "number": 2,
                    "word": "bat",
                    "issue": "wrong_sense",
                    "severity": "clear",
                    "reasoning": "the animal sense",
                    "suggestion": "drop this sense",
                }
            ]
        },
        210,
        "Sports Equipment",
        words,
    )
    assert scan.problems == ()
    assert [outlier.lemma_id for outlier in scan.outliers] == [words[1].id]
    assert scan.outliers[0].issue == "wrong_sense"


def test_parse_falls_back_to_a_unique_spelling_and_drops_ambiguous_ones() -> None:
    session = _session()
    words = _sports_level(session)
    scan = parse_outliers(
        {
            "outliers": [
                # Wrong number, but only one word is spelled this way.
                {"number": 1, "word": "sphygmomanometer", "issue": "obscure", "severity": "clear"},
                # Two words are spelled "bat": no way to tell which was meant.
                {"number": 9, "word": "bat", "issue": "off_topic", "severity": "clear"},
                # A repeat of the first flag.
                {"number": 4, "word": "sphygmomanometer", "issue": "obscure", "severity": "clear"},
            ]
        },
        210,
        "Sports Equipment",
        words,
    )
    assert [outlier.word for outlier in scan.outliers] == ["sphygmomanometer"]
    assert len(scan.problems) == 1 and "'bat'" in scan.problems[0]


def test_parse_reads_unknown_issue_and_severity_conservatively() -> None:
    session = _session()
    words = _sports_level(session)
    scan = parse_outliers(
        {"outliers": [{"number": 1, "word": "ball", "issue": "weird", "severity": "very"}]},
        210,
        "Sports Equipment",
        words,
    )
    assert scan.outliers[0].issue == "other"
    assert scan.outliers[0].severity == "borderline"
    assert len(scan.problems) == 2


class _FakeResponse:
    def __init__(self, data: Dict[str, Any]) -> None:
        self.structured_data = data


class _FakeClient:
    def __init__(self, data: Dict[str, Any]) -> None:
        self.data = data
        self.calls: List[Dict[str, Any]] = []

    def generate_chat(self, **kwargs: Any) -> _FakeResponse:
        self.calls.append(kwargs)
        return _FakeResponse(self.data)


def test_scan_sends_the_level_and_returns_matched_flags() -> None:
    session = _session()
    words = _sports_level(session)
    session.commit()
    client = _FakeClient(
        {
            "outliers": [
                {
                    "number": 4,
                    "word": "sphygmomanometer",
                    "issue": "off_topic",
                    "severity": "clear",
                    "reasoning": "medical equipment",
                    "suggestion": "",
                }
            ]
        }
    )
    scan = scan_level(session, 210, client)  # type: ignore[arg-type]

    assert scan.title == "Sports Equipment" and scan.word_count == 4
    assert [outlier.guid for outlier in scan.outliers] == [words[3].guid]
    call = client.calls[0]
    assert call["json_schema"] is OUTLIER_JSON_SCHEMA
    assert "1. ball" in call["prompt"]


def test_scan_of_an_empty_level_makes_no_call() -> None:
    session = _session()
    client = _FakeClient({"outliers": []})
    scan = scan_level(session, 999, client)  # type: ignore[arg-type]
    assert scan.word_count == 0 and client.calls == []


def test_levels_in_band() -> None:
    session = _session()
    for level, name in (
        (8, "Basics"),
        (15, "Local Countries"),
        (21, "Days and Months"),
        (150, "Thinking"),
        (1070, "Law"),
    ):
        session.add(CurriculumLevel(level=level, name=name))
    session.add(CurriculumLevel(level=US_STATES.level, name="US States"))
    session.commit()
    assert levels_in_band(session, "named") == [150]
    # Skipped: 15 is override-only, 21 the days-and-months fixed set.
    assert levels_in_band(session, "core") == [8]


def test_core_neighbours_skip_empty_and_override_only_levels() -> None:
    session = _session()
    for level, name in ((13, "Feelings"), (14, "Descriptions"), (16, "People"), (18, "Family")):
        session.add(CurriculumLevel(level=level, name=name))
    _lemma(session, "joy", 13)
    _lemma(session, "big", 14)
    _lemma(session, "aunt", 18)
    # 15 is override-only and 17 is empty, so 16's neighbours are 14 and 18.
    _lemma(session, "uncle", 16)
    session.commit()

    neighbours = neighbour_levels(session, 16)

    assert [neighbour.level for neighbour in neighbours] == [14, 18]
    prompt = build_prompt(16, "People", "A2", [], neighbours)
    assert "Level 14 - Descriptions: big" in prompt
    assert "{{" not in prompt


def test_named_levels_have_no_neighbours() -> None:
    session = _session()
    _sports_level(session)
    _lemma(session, "goal", 211)
    session.commit()

    assert neighbour_levels(session, 210) == []
    assert "For reference only" not in build_prompt(210, "Sports Equipment", "A2", [])
