"""Tests for missing-synonym discovery."""

from typing import Iterator, List

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from storage.crud.operation_log import log_operation
from storage.models.operation_log import OperationLog
from storage.models.schema import Base, Lemma
from words.synonym_coverage import ALL_FORM_TYPES, find_missing_synonyms


@pytest.fixture()
def session() -> Iterator[Session]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db_session:
        yield db_session
        db_session.close()


def _add_lemma(session: Session, guid: str, text: str) -> Lemma:
    lemma = Lemma(
        lemma_text=text,
        definition_text=f"a {text}",
        pos_type="noun",
        guid=guid,
    )
    session.add(lemma)
    session.commit()
    return lemma


def _record_scan(session: Session, lemma: Lemma, language_code: str) -> None:
    """Record the scan the coverage check treats as "already processed"."""
    log_operation(
        session,
        operation_type="synonym_scan",
        source=f"sernas-agent:{language_code}",
        lemma_id=lemma.id,
    )
    session.commit()


def test_unscanned_lemmas_are_reported_as_missing(session: Session) -> None:
    lemma = _add_lemma(session, "N00_001", "street")

    report = find_missing_synonyms(session, lemmas=[lemma], language_code="en")

    assert report.error is None
    assert report.checked_languages == ["en"]
    assert report.checked_form_types == ALL_FORM_TYPES
    assert report.total_missing == 1
    missing = report.for_language("en")[0]
    assert missing.guid == "N00_001"
    assert missing.english == "street"
    assert missing.translation == "street"
    assert missing.pos_type == "noun"


def test_scanned_lemmas_are_not_reported_again(session: Session) -> None:
    lemma = _add_lemma(session, "N00_002", "road")
    _record_scan(session, lemma, "en")

    report = find_missing_synonyms(session, lemmas=[lemma], language_code="en")

    assert report.total_missing == 0
    assert report.for_language("en") == []


def test_languages_without_a_translation_are_skipped(session: Session) -> None:
    lemma = _add_lemma(session, "N00_003", "river")

    report = find_missing_synonyms(session, lemmas=[lemma], language_code="lt")

    # The lemma has no Lithuanian translation, so there is nothing to scan for.
    assert report.total_missing == 0


def test_form_type_filter_is_reported_as_the_only_checked_type(session: Session) -> None:
    lemma = _add_lemma(session, "N00_004", "lane")

    report = find_missing_synonyms(
        session, lemmas=[lemma], language_code="en", form_type="abbreviation"
    )

    assert report.checked_form_types == ["abbreviation"]


def test_default_language_set_covers_english_and_supported_languages(session: Session) -> None:
    lemma = _add_lemma(session, "N00_005", "path")

    report = find_missing_synonyms(session, lemmas=[lemma])

    assert report.checked_languages[0] == "en"
    assert len(report.checked_languages) > 1
    # English is listed once even though it is also a supported language.
    assert report.checked_languages.count("en") == 1
    # Only English has a value to scan (the lemma text itself).
    assert report.total_missing == 1


def test_report_totals_sum_every_language(session: Session) -> None:
    lemmas: List[Lemma] = [
        _add_lemma(session, "N00_006", "hill"),
        _add_lemma(session, "N00_007", "valley"),
    ]

    report = find_missing_synonyms(session, lemmas=lemmas, language_code="en")

    assert report.total_missing == 2


def test_scan_records_without_an_entity_guid_still_count_as_processed(
    session: Session,
) -> None:
    """The SERNAS canary.

    The operation log is not just an audit trail here: ``has_synonym_scan_record``
    reads it as state, keyed on the ``lemma_id`` column. Rows written before
    ``entity_guid`` existed carry NULL there, and every row this agent writes
    still keys on ``lemma_id``. If that reference is ever moved to
    ``entity_guid`` instead of alongside it, this check goes blind and SERNAS
    re-scans the entire corpus.
    """
    lemma = _add_lemma(session, "N00_009", "avenue")
    _record_scan(session, lemma, "en")

    stored = session.query(OperationLog).filter_by(operation_type="synonym_scan").one()
    assert stored.entity_guid is None
    assert stored.lemma_id == lemma.id

    report = find_missing_synonyms(session, lemmas=[lemma], language_code="en")
    assert report.total_missing == 0
