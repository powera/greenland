"""Tests for concept-body batch completion."""

import json
from typing import Any, Iterator, List, Optional

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from concepts.generate.batch import BATCH_OPERATION, complete_concept_body_batch
from storage.crud.concept import get_concept_by_slug
from storage.models.concept import Base


class FakeBatchRequest:
    """The subset of a BatchQueue row that completion reads."""

    def __init__(
        self,
        custom_id: str,
        *,
        body: Optional[str] = "A generated body.",
        seed_title: Optional[str] = "Art Deco",
        qid: str = "Q42",
    ) -> None:
        self.custom_id = custom_id
        self.additional_metadata = (
            json.dumps(
                {
                    "operation_type": BATCH_OPERATION,
                    "qid": qid,
                    "seed": {
                        "qid": qid,
                        "title": seed_title,
                        "summary": "A decorative arts style.",
                        "sources": [{"url": "https://example.test/art-deco"}],
                    },
                    "source_model": "test-model",
                }
            )
            if seed_title is not None
            else None
        )
        self.response_body = (
            json.dumps({"body": {"choices": [{"message": {"content": body}}]}})
            if body is not None
            else None
        )


@pytest.fixture()
def session() -> Iterator[Session]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db_session:
        yield db_session


def test_stashed_seed_and_generated_body_become_a_concept(session: Session) -> None:
    results = complete_concept_body_batch([FakeBatchRequest("voveraite_Q42")], session, "batch_1")

    assert results == {"processed": 1, "created": 1, "skipped": 0, "failed": 0}
    concept = get_concept_by_slug(session, "Art Deco")
    assert concept is not None
    assert concept.body == "A generated body."
    assert concept.source_model == "test-model"


def test_a_second_completion_of_the_same_seed_is_skipped(session: Session) -> None:
    complete_concept_body_batch([FakeBatchRequest("voveraite_Q42")], session, "batch_1")
    results = complete_concept_body_batch([FakeBatchRequest("voveraite_Q42")], session, "batch_2")

    assert results["created"] == 0
    assert results["skipped"] == 1


def test_requests_without_a_stashed_seed_fail_without_stopping_the_batch(
    session: Session,
) -> None:
    requests: List[Any] = [
        FakeBatchRequest("voveraite_Q1", seed_title=None),
        FakeBatchRequest("voveraite_Q42"),
    ]

    results = complete_concept_body_batch(requests, session, "batch_1")

    assert results == {"processed": 2, "created": 1, "skipped": 0, "failed": 1}


def test_requests_without_a_generated_body_fail(session: Session) -> None:
    results = complete_concept_body_batch(
        [FakeBatchRequest("voveraite_Q42", body=None)], session, "batch_1"
    )

    assert results["failed"] == 1
    assert get_concept_by_slug(session, "Art Deco") is None
