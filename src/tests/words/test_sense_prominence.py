"""Tests for words.sense_prominence: grouping, prompt build, parsing, applying."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Dict, List, Optional

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from storage.models.schema import (
    SENSE_PROMINENCE_COMMON,
    SENSE_PROMINENCE_RARE,
    SENSE_PROMINENCE_VERY_COMMON,
    Base,
    Lemma,
)
from words.sense_prominence import (
    ProminenceRating,
    apply_ratings,
    build_prompt,
    find_duplicate_text_groups,
    rate_group,
)


def _make_session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def _add_lemma(
    session: Session,
    text: str,
    definition: str,
    *,
    pos_type: str = "noun",
    prominence: Optional[str] = None,
) -> Lemma:
    lemma = Lemma(
        lemma_text=text,
        definition_text=definition,
        pos_type=pos_type,
        sense_prominence=prominence,
    )
    session.add(lemma)
    session.flush()
    return lemma


class _FakeClient:
    """Stands in for UnifiedLLMClient, returning a canned structured response."""

    def __init__(self, payload: Any, raises: bool = False) -> None:
        self.payload = payload
        self.raises = raises
        self.prompts: List[str] = []

    def generate_chat(self, prompt: str, model: str, json_schema: Any, context: str) -> Any:
        self.prompts.append(prompt)
        if self.raises:
            raise RuntimeError("model exploded")
        return SimpleNamespace(structured_data=self.payload)


def _ratings_payload(pairs: List[tuple[int, str]]) -> Dict[str, Any]:
    return {
        "ratings": [
            {"sense_number": number, "sense_prominence": prominence, "reasoning": "because"}
            for number, prominence in pairs
        ]
    }


class TestFindDuplicateTextGroups:
    def test_single_sense_lemma_is_not_a_group(self) -> None:
        """A lemma with no homograph takes the full token share regardless."""
        with _make_session() as session:
            _add_lemma(session, "elephant", "a large mammal")
            assert find_duplicate_text_groups(session) == []

    def test_shared_spelling_returns_every_sense(self) -> None:
        with _make_session() as session:
            _add_lemma(session, "top", "the highest point")
            _add_lemma(session, "top", "a spinning toy")
            _add_lemma(session, "top", "a garment")
            _add_lemma(session, "elephant", "a large mammal")

            groups = find_duplicate_text_groups(session)

            assert len(groups) == 1
            lemma_text, senses = groups[0]
            assert lemma_text == "top"
            assert len(senses) == 3

    def test_limit_caps_group_count(self) -> None:
        with _make_session() as session:
            for text in ("bank", "bat", "top"):
                _add_lemma(session, text, f"{text} one")
                _add_lemma(session, text, f"{text} two")

            assert len(find_duplicate_text_groups(session, limit=2)) == 2

    def test_only_unrated_skips_an_already_rated_spelling(self) -> None:
        with _make_session() as session:
            _add_lemma(session, "bank", "money", prominence=SENSE_PROMINENCE_VERY_COMMON)
            _add_lemma(session, "bank", "river edge", prominence=SENSE_PROMINENCE_COMMON)
            _add_lemma(session, "bat", "club")
            _add_lemma(session, "bat", "mammal")

            groups = find_duplicate_text_groups(session, only_unrated=True)

            assert [text for text, _ in groups] == ["bat"]

    def test_only_unrated_skips_a_uniformly_common_spelling(self) -> None:
        """A group the model judged all-common is rated, not unrated.

        Inferring rated-ness from "differs from common" made this group
        eligible on every run, so the same spelling was paid for repeatedly
        and its verdict never recorded.
        """
        with _make_session() as session:
            _add_lemma(session, "spade", "card suit", prominence=SENSE_PROMINENCE_COMMON)
            _add_lemma(session, "spade", "digging tool", prominence=SENSE_PROMINENCE_COMMON)

            groups = find_duplicate_text_groups(session, only_unrated=True)

            assert groups == []

    def test_only_unrated_keeps_a_partly_rated_spelling(self) -> None:
        """One unrated sense is enough: the judgment is comparative."""
        with _make_session() as session:
            _add_lemma(session, "pen", "writing tool", prominence=SENSE_PROMINENCE_VERY_COMMON)
            _add_lemma(session, "pen", "animal enclosure")

            groups = find_duplicate_text_groups(session, only_unrated=True)

            assert [text for text, _ in groups] == ["pen"]

    def test_unrated_sense_is_reported_as_none(self) -> None:
        with _make_session() as session:
            _add_lemma(session, "bat", "club")
            _add_lemma(session, "bat", "mammal", prominence=SENSE_PROMINENCE_COMMON)

            _, senses = find_duplicate_text_groups(session)[0]

            assert [sense.current_prominence for sense in senses] == [
                None,
                SENSE_PROMINENCE_COMMON,
            ]


class TestBuildPrompt:
    def test_lists_every_sense_numbered_from_one(self) -> None:
        with _make_session() as session:
            _add_lemma(session, "top", "the highest point")
            _add_lemma(session, "top", "a spinning toy", pos_type="noun")
            _, senses = find_duplicate_text_groups(session)[0]

            prompt = build_prompt("top", senses)

            assert "1. (noun) the highest point" in prompt
            assert "2. (noun) a spinning toy" in prompt
            assert '"top"' in prompt


class TestRateGroup:
    def test_ratings_map_back_by_sense_number(self) -> None:
        with _make_session() as session:
            first = _add_lemma(session, "top", "the highest point")
            second = _add_lemma(session, "top", "a spinning toy")
            _, senses = find_duplicate_text_groups(session)[0]

            # Deliberately out of order: matching must use sense_number, not
            # array position.
            client = _FakeClient(
                _ratings_payload([(2, SENSE_PROMINENCE_RARE), (1, SENSE_PROMINENCE_VERY_COMMON)])
            )
            ratings, error = rate_group(client, "top", senses)

            assert error is None
            by_id = {rating.lemma_id: rating.prominence for rating in ratings}
            assert by_id[first.id] == SENSE_PROMINENCE_VERY_COMMON
            assert by_id[second.id] == SENSE_PROMINENCE_RARE

    def test_out_of_range_sense_number_is_discarded(self) -> None:
        with _make_session() as session:
            _add_lemma(session, "top", "the highest point")
            _add_lemma(session, "top", "a spinning toy")
            _, senses = find_duplicate_text_groups(session)[0]

            client = _FakeClient(
                _ratings_payload([(1, SENSE_PROMINENCE_VERY_COMMON), (7, SENSE_PROMINENCE_RARE)])
            )
            ratings, error = rate_group(client, "top", senses)

            assert error is None
            assert len(ratings) == 1

    def test_duplicate_sense_number_is_discarded(self) -> None:
        with _make_session() as session:
            _add_lemma(session, "top", "the highest point")
            _add_lemma(session, "top", "a spinning toy")
            _, senses = find_duplicate_text_groups(session)[0]

            client = _FakeClient(
                _ratings_payload([(1, SENSE_PROMINENCE_VERY_COMMON), (1, SENSE_PROMINENCE_RARE)])
            )
            ratings, error = rate_group(client, "top", senses)

            assert len(ratings) == 1
            assert ratings[0].prominence == SENSE_PROMINENCE_VERY_COMMON

    def test_unknown_prominence_label_is_discarded(self) -> None:
        with _make_session() as session:
            _add_lemma(session, "top", "the highest point")
            _add_lemma(session, "top", "a spinning toy")
            _, senses = find_duplicate_text_groups(session)[0]

            client = _FakeClient(_ratings_payload([(1, "extremely_common"), (2, "rare")]))
            ratings, error = rate_group(client, "top", senses)

            assert [rating.prominence for rating in ratings] == [SENSE_PROMINENCE_RARE]

    def test_malformed_response_reports_an_error(self) -> None:
        with _make_session() as session:
            _add_lemma(session, "top", "the highest point")
            _add_lemma(session, "top", "a spinning toy")
            _, senses = find_duplicate_text_groups(session)[0]

            ratings, error = rate_group(_FakeClient({"nope": []}), "top", senses)

            assert ratings == []
            assert error == "malformed response"

    def test_client_exception_is_reported_not_raised(self) -> None:
        with _make_session() as session:
            _add_lemma(session, "top", "the highest point")
            _add_lemma(session, "top", "a spinning toy")
            _, senses = find_duplicate_text_groups(session)[0]

            ratings, error = rate_group(_FakeClient(None, raises=True), "top", senses)

            assert ratings == []
            assert error is not None
            assert "RuntimeError" in error

    def test_repeated_labels_are_allowed(self) -> None:
        """Two senses may genuinely be equally common; they then split evenly."""
        with _make_session() as session:
            _add_lemma(session, "bank", "money")
            _add_lemma(session, "bank", "river edge")
            _, senses = find_duplicate_text_groups(session)[0]

            client = _FakeClient(
                _ratings_payload(
                    [(1, SENSE_PROMINENCE_VERY_COMMON), (2, SENSE_PROMINENCE_VERY_COMMON)]
                )
            )
            ratings, error = rate_group(client, "bank", senses)

            assert {rating.prominence for rating in ratings} == {SENSE_PROMINENCE_VERY_COMMON}


class TestApplyRatings:
    def test_only_changed_lemmas_are_reported(self) -> None:
        with _make_session() as session:
            unchanged = _add_lemma(
                session, "top", "the highest point", prominence=SENSE_PROMINENCE_COMMON
            )
            changed = _add_lemma(
                session, "top", "a spinning toy", prominence=SENSE_PROMINENCE_COMMON
            )

            applied = apply_ratings(
                session,
                [
                    ProminenceRating(unchanged.id, SENSE_PROMINENCE_COMMON, ""),
                    ProminenceRating(changed.id, SENSE_PROMINENCE_RARE, ""),
                ],
            )

            assert applied == [changed.id]
            assert changed.sense_prominence == SENSE_PROMINENCE_RARE
            assert unchanged.sense_prominence == SENSE_PROMINENCE_COMMON

    def test_rating_an_unrated_sense_common_is_a_change(self) -> None:
        """NULL -> "common" is how a rating gets recorded.

        Skipping it as a no-op would leave the sense unrated, so
        ``--only-unrated`` would ask about it again on the next run.
        """
        with _make_session() as session:
            lemma = _add_lemma(session, "bat", "mammal")
            assert lemma.sense_prominence is None

            applied = apply_ratings(
                session, [ProminenceRating(lemma.id, SENSE_PROMINENCE_COMMON, "")]
            )

            assert applied == [lemma.id]
            assert lemma.sense_prominence == SENSE_PROMINENCE_COMMON

    def test_missing_lemma_is_skipped(self) -> None:
        with _make_session() as session:
            assert apply_ratings(session, [ProminenceRating(9999, SENSE_PROMINENCE_RARE, "")]) == []
