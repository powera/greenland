"""Tests for the LLM subtype review: prompts, answer matching, the TSV, and apply."""

import csv
import io
from typing import Any, Dict, List, Optional

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from quality.subtype_review import (
    TSV_COLUMNS,
    apply_rows,
    build_json_schema,
    build_prompt,
    describe_word,
    flag_row,
    lemmas_in_subtype,
    parse_flags,
    read_apply_rows,
    review_subtype,
    subtypes_to_review,
)
from storage.models.guid_prefixes import SUBTYPE_GUID_PREFIXES
from storage.models.guid_tombstone import GuidTombstone
from storage.models.schema import Base, Lemma


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def _lemma(
    session: Session,
    text: str,
    level: Optional[int],
    definition: str = "",
    subtype: str = "time_period",
    disambiguation: Optional[str] = None,
) -> Lemma:
    prefix = SUBTYPE_GUID_PREFIXES["noun"][subtype]
    lemma = Lemma(
        lemma_text=text,
        definition_text=definition or f"a {text}",
        pos_type="noun",
        pos_subtype=subtype,
        difficulty_level=level,
        guid=f"{prefix}_{session.query(Lemma).count() + 1:03d}",
        disambiguation=disambiguation,
    )
    session.add(lemma)
    session.flush()
    return lemma


def _time_words(session: Session) -> List[Lemma]:
    return [
        _lemma(session, "year", 3),
        _lemma(session, "death", 12, "the end of life"),
        _lemma(session, "spring", 8, "the season after winter", disambiguation="season"),
    ]


def _flag(number: int, word: str, verdict: str = "move", **extra: Any) -> Dict[str, Any]:
    item: Dict[str, Any] = {
        "number": number,
        "word": word,
        "verdict": verdict,
        "suggested_subtype": "process_event" if verdict == "move" else "",
        "severity": "clear",
        "reasoning": "not a span of time",
        "suggestion": "",
    }
    item.update(extra)
    return item


def test_word_line_carries_sense_definition_and_level() -> None:
    session = _session()
    words = _time_words(session)
    assert describe_word(3, words[2]) == "3. spring [season]: the season after winter | level 8"
    words[0].difficulty_level = None
    assert describe_word(1, words[0]).endswith("| level none")


def test_prompt_lists_every_subtype_and_numbers_the_senses() -> None:
    session = _session()
    prompt = build_prompt("noun", "time_period", _time_words(session))
    assert 'Review the noun subtype "time_period"' in prompt
    assert "- process_event:" in prompt and "- other:" in prompt
    assert "2. death: the end of life | level 12" in prompt
    assert "{{" not in prompt


def test_schema_offers_live_subtypes_under_their_prompt_names() -> None:
    choices = build_json_schema("noun")["properties"]["flags"]["items"]["properties"][
        "suggested_subtype"
    ]["enum"]
    assert "other" in choices and "noun_other" not in choices
    assert "personal_name" not in choices  # retired
    assert "" in choices


def test_parse_keeps_a_move_and_pre_fills_apply() -> None:
    session = _session()
    words = _time_words(session)
    scan = parse_flags({"flags": [_flag(2, "death")]}, "noun", "time_period", words)

    assert scan.problems == ()
    (flag,) = scan.flags
    assert (flag.lemma_id, flag.suggested_subtype, flag.level) == (words[1].id, "process_event", 12)
    assert flag.default_apply
    assert flag_row(flag)["apply"] == "yes"


def test_parse_leaves_catch_all_borderline_and_flag_only_rows_unticked() -> None:
    session = _session()
    words = _time_words(session)
    payload = {
        "flags": [
            _flag(1, "year", suggested_subtype="other"),
            _flag(2, "death", severity="borderline"),
            _flag(3, "spring", verdict="wrong_sense", suggestion="definition is a coil"),
        ]
    }
    scan = parse_flags(payload, "noun", "time_period", words)

    assert [flag.suggested_subtype for flag in scan.flags] == ["noun_other", "process_event", ""]
    assert [flag.default_apply for flag in scan.flags] == [False, False, False]


def test_parse_drops_bad_answers_and_reports_them() -> None:
    session = _session()
    words = _time_words(session)
    payload = {
        "flags": [
            _flag(1, "year", suggested_subtype="time_period"),  # its own subtype
            _flag(2, "death", suggested_subtype="not_a_subtype"),
            _flag(3, "spring", verdict="rename"),
            _flag(9, "decade"),
        ]
    }
    scan = parse_flags(payload, "noun", "time_period", words)

    assert [(flag.word, flag.suggested_subtype) for flag in scan.flags] == [
        ("year", ""),
        ("death", ""),
    ]
    assert not any(flag.default_apply for flag in scan.flags)
    assert len(scan.problems) == 4


def test_level_bounds_drop_unleveled_and_excluded_senses() -> None:
    session = _session()
    _time_words(session)
    _lemma(session, "eon", None)
    _lemma(session, "fortnight", -1)
    _lemma(session, "millennium", 1100)

    assert [lemma.lemma_text for lemma in lemmas_in_subtype(session, "noun", "time_period")] == [
        "year",
        "spring",
        "death",
        "millennium",
        "eon",
    ]
    bounded = lemmas_in_subtype(session, "noun", "time_period", max_level=30)
    assert [lemma.lemma_text for lemma in bounded] == ["year", "spring", "death"]


def test_subtypes_to_review_skips_the_catch_all_unless_asked() -> None:
    nouns = subtypes_to_review(["noun"], [], include_catch_all=False)
    assert ("noun", "time_period") in nouns and ("noun", "noun_other") not in nouns
    assert ("noun", "personal_name") in nouns  # retired, but senses may still sit there
    assert ("noun", "noun_other") in subtypes_to_review(["noun"], [], include_catch_all=True)
    assert subtypes_to_review(["noun"], ["noun_other"], False) == [("noun", "noun_other")]
    with pytest.raises(ValueError):
        subtypes_to_review(["verb"], ["time_period"], False)


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


def test_review_splits_a_large_subtype_into_chunks() -> None:
    session = _session()
    _time_words(session)
    client = _FakeClient({"flags": []})
    scan = review_subtype(session, "noun", "time_period", client, chunk_size=2)  # type: ignore[arg-type]

    assert scan.word_count == 3 and len(client.calls) == 2
    assert "(part 1 of 2)" in client.calls[0]["prompt"]


def test_review_of_an_empty_subtype_makes_no_call() -> None:
    client = _FakeClient({"flags": []})
    scan = review_subtype(_session(), "noun", "time_period", client)  # type: ignore[arg-type]
    assert scan.word_count == 0 and client.calls == []


def _reviewed_tsv(session: Session, payload: Dict[str, Any]) -> io.StringIO:
    words = lemmas_in_subtype(session, "noun", "time_period")
    scan = parse_flags(payload, "noun", "time_period", words)
    handle = io.StringIO()
    handle.write("\t".join(TSV_COLUMNS) + "\n")
    for flag in scan.flags:
        handle.write("\t".join(flag_row(flag)[column] for column in TSV_COLUMNS) + "\n")
    handle.seek(0)
    return handle


def test_apply_moves_ticked_rows_and_tombstones_the_old_guid() -> None:
    session = _session()
    words = _time_words(session)
    session.commit()
    old_guid = words[1].guid
    tsv = _reviewed_tsv(
        session,
        {"flags": [_flag(3, "death"), _flag(2, "spring", suggested_subtype="other")]},
    )
    rows = read_apply_rows(tsv)
    assert [row["word"] for row in rows] == ["death"]  # the catch-all move is unticked

    result = apply_rows(session, rows)

    assert result.skipped == ()
    (move,) = result.applied
    session.refresh(words[1])
    assert words[1].pos_subtype == "process_event"
    assert words[1].guid == move.new_guid != old_guid
    assert (words[1].guid or "").startswith(SUBTYPE_GUID_PREFIXES["noun"]["process_event"])
    tombstone = session.query(GuidTombstone).filter_by(guid=old_guid).one()
    assert tombstone.replacement_guid == words[1].guid


def test_apply_skips_rows_the_database_has_moved_past() -> None:
    session = _session()
    words = _time_words(session)
    session.commit()
    tsv = _reviewed_tsv(
        session,
        {"flags": [_flag(3, "death"), _flag(1, "year"), _flag(2, "spring", verdict="wrong_pos")]},
    )
    rows = list(csv.DictReader(tsv, delimiter="\t"))
    for row in rows:
        row["apply"] = "yes"  # including the wrong_pos row, which cannot apply
    rows.append({**rows[0]})  # the same lemma twice
    words[0].pos_subtype = "animal"  # "year" was refiled by hand after the review
    session.commit()

    result = apply_rows(session, rows)

    assert [move.word for move in result.applied] == ["death"]
    assert len(result.skipped) == 3
    session.refresh(words[0])
    assert words[0].pos_subtype == "animal"


def test_apply_dry_run_rolls_back() -> None:
    session = _session()
    words = _time_words(session)
    session.commit()
    old_guid = words[1].guid
    rows = read_apply_rows(_reviewed_tsv(session, {"flags": [_flag(3, "death")]}))

    result = apply_rows(session, rows, commit=False)

    assert len(result.applied) == 1
    session.refresh(words[1])
    assert (words[1].pos_subtype, words[1].guid) == ("time_period", old_guid)
    assert session.query(GuidTombstone).count() == 0
