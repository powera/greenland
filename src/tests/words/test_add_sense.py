"""Tests for the domain-sense add path (words.add_sense).

add_sense adds the meaning a word has in one field -- "check" in chess -- next
to the headword's existing senses, and asks the model in the same call whether
one of those senses already is the one wanted. The LLM call is stubbed here;
what is covered is everything around it: the free pre-check that makes a re-run
cost nothing, the covered / moved / created branches, and a covered_by answer
that names no listed sense.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Generator, List, Optional

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

import storage.models  # noqa: F401
from storage.backend.config import BackendType, DataSourceConfig
from storage.crud.lemma_tags import read_tags
from storage.crud.uncertain_llm_result import get_uncertain_llm_result
from storage.models import Base, DerivativeForm, Lemma
from storage.models.schema import SENSE_PROMINENCE_RARE
from storage.models.uncertain_llm_result import TOPIC_TRANSLATION
from storage.models.variant_form import VARIANT_KIND_ABBREVIATION, VariantForm
from storage.translation_helpers import get_translation
from words.add_sense import add_sense, build_sense_prompt, build_subtype_prompt
from words.translation_populate import missing_translation_languages


@pytest.fixture()
def db_engine(tmp_path: Path) -> Generator[Engine, None, None]:
    engine = create_engine(f"sqlite:///{tmp_path / 'add_sense.sqlite'}")
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture()
def session(db_engine: Engine) -> Generator[Session, None, None]:
    factory = sessionmaker(bind=db_engine)
    db_session = factory()
    # Two existing senses, neither labelled: the everyday "check" and the chess
    # queen as the database holds it today.
    db_session.add_all(
        [
            Lemma(
                lemma_text="check",
                disambiguation="examine",
                definition_text="To examine something to make sure it is correct.",
                pos_type="verb",
                pos_subtype="mental_state",
                guid="V01_001",
                difficulty_level=460,
            ),
            Lemma(
                lemma_text="queen",
                definition_text="The most powerful piece in chess.",
                pos_type="noun",
                pos_subtype="small_movable_object",
                guid="N01_001",
                difficulty_level=200,
            ),
        ]
    )
    db_session.commit()
    yield db_session
    db_session.close()


@pytest.fixture()
def config() -> DataSourceConfig:
    return DataSourceConfig(
        backend_type=BackendType.SQLITE, sqlite_path=":memory:", model="test-model"
    )


class _FakeResponse:
    def __init__(self, structured_data: Any) -> None:
        self.structured_data = structured_data


class _FakeClient:
    """Stand-in for UnifiedLLMClient returning one canned sense."""

    def __init__(self, structured_data: Any) -> None:
        self._structured_data = structured_data
        self.calls: List[Dict[str, Any]] = []

    def generate_chat(self, **kwargs: Any) -> _FakeResponse:
        self.calls.append(kwargs)
        return _FakeResponse(self._structured_data)


def _rated(translation: str, confidence: Optional[float] = 0.95) -> Dict[str, Any]:
    """One translation field as the schema asks for it."""
    rated: Dict[str, Any] = {"translation": translation}
    if confidence is not None:
        rated["confidence"] = confidence
    return rated


def _chess_check(covered_by: int = 0) -> Dict[str, Any]:
    return {
        "covered_by": covered_by,
        "definition": "In chess, a move that attacks the opposing king.",
        "pos": "noun",
        "pos_subtype": "concept_idea",
        "phonetic_spelling": "CHEK",
        "ipa_spelling": "/tʃɛk/",
        "examples": ["White gave check with the rook."],
        "lithuanian_translation": _rated("šachas"),
        "spanish_translation": _rated("jaque"),
        "spanish_latam_translation": _rated("jaque"),
        "french_translation": _rated("échec"),
        "chinese_translation": _rated("将军"),
        "confidence": 0.9,
    }


def _add(
    session: Session,
    config: DataSourceConfig,
    client: Optional[_FakeClient],
    **kwargs: Any,
) -> Any:
    defaults: Dict[str, Any] = {
        "word": "check",
        "domain": "chess",
        "disambiguation": "chess",
        "hint": "an attack on the king",
        "config": config,
        "client": client,
        "difficulty_level": 1202,
        "tags": ["sports_games", "chess"],
    }
    defaults.update(kwargs)
    return add_sense(session, **defaults)


class TestCreation:
    def test_new_sense_is_written_beside_the_existing_one(
        self, session: Session, config: DataSourceConfig
    ) -> None:
        client = _FakeClient(_chess_check())

        result = _add(session, config, client)

        assert result.status == "created"
        assert result.missing_languages == []
        lemma = session.query(Lemma).filter(Lemma.guid == result.guid).one()
        assert (lemma.lemma_text, lemma.disambiguation) == ("check", "chess")
        assert lemma.difficulty_level == 1202
        assert lemma.sense_prominence == SENSE_PROMINENCE_RARE
        assert read_tags(lemma) == ["chess", "sports_games"]
        assert get_translation(session, lemma, "lt") == "šachas"
        assert session.query(Lemma).filter(Lemma.lemma_text == "check").count() == 2

    def test_low_confidence_translation_is_left_missing(
        self, session: Session, config: DataSourceConfig
    ) -> None:
        # Chess "skewer" as luna answered it: sure of the Chinese, guessing at
        # the Spanish and French with the words for neighboring tactics.
        sense = _chess_check()
        sense["spanish_translation"] = _rated("clavada", 0.6)
        sense["french_translation"] = _rated("attaque à la découverte", 0.84)

        result = _add(session, config, _FakeClient(sense))

        assert result.status == "created"
        assert result.missing_languages == ["es", "fr"]
        assert result.low_confidence == {
            "es": {"translation": "clavada", "confidence": 0.6},
            "fr": {"translation": "attaque à la découverte", "confidence": 0.84},
        }
        assert "es" not in result.translations
        lemma = session.query(Lemma).filter(Lemma.guid == result.guid).one()
        assert get_translation(session, lemma, "es") is None
        assert get_translation(session, lemma, "fr") is None
        assert get_translation(session, lemma, "es-419") == "jaque"
        assert get_translation(session, lemma, "zh") == "将军"

    def test_low_confidence_translation_is_recorded_as_uncertain(
        self, session: Session, config: DataSourceConfig
    ) -> None:
        sense = _chess_check()
        sense["spanish_translation"] = _rated("clavada", 0.6)

        result = _add(session, config, _FakeClient(sense))

        lemma = session.query(Lemma).filter(Lemma.guid == result.guid).one()
        row = get_uncertain_llm_result(session, TOPIC_TRANSLATION, "es", lemma_id=lemma.id)
        assert row is not None
        assert row.note == f"{config.model} leaned clavada (0.60)"
        assert missing_translation_languages(session, lemma, ["es", "fr"]) == []
        assert missing_translation_languages(
            session, lemma, ["es", "fr"], retry_uncertain=True
        ) == ["es"]
        assert get_uncertain_llm_result(session, TOPIC_TRANSLATION, "zh", lemma_id=lemma.id) is None

    def test_translation_at_the_floor_is_kept(
        self, session: Session, config: DataSourceConfig
    ) -> None:
        sense = _chess_check()
        sense["french_translation"] = _rated("échec", 0.85)

        result = _add(session, config, _FakeClient(sense))

        assert result.low_confidence == {}
        assert result.translations["fr"] == "échec"

    def test_unrated_translation_is_left_missing(
        self, session: Session, config: DataSourceConfig
    ) -> None:
        sense = _chess_check()
        sense["lithuanian_translation"] = _rated("šachas", None)

        result = _add(session, config, _FakeClient(sense))

        assert result.missing_languages == ["lt"]
        assert result.low_confidence == {"lt": {"translation": "šachas", "confidence": None}}

    def test_translations_are_rated_per_language(self) -> None:
        _context, _prompt, schema = build_sense_prompt("check", "chess", None, [])

        rated = schema.properties["lithuanian_translation"]
        assert rated.type == "object"
        assert set(rated.properties or {}) == {"translation", "confidence"}

    def test_base_form_is_attached(self, session: Session, config: DataSourceConfig) -> None:
        result = _add(session, config, _FakeClient(_chess_check()))

        lemma = session.query(Lemma).filter(Lemma.guid == result.guid).one()
        forms = session.query(DerivativeForm).filter(DerivativeForm.lemma_id == lemma.id).all()
        assert [(form.derivative_form_text, form.is_base_form) for form in forms] == [
            ("check", True)
        ]

    def test_prompt_carries_domain_hint_and_existing_senses(
        self, session: Session, config: DataSourceConfig
    ) -> None:
        client = _FakeClient(_chess_check())
        _add(session, config, client)

        # The sense call, then the subtype call.
        assert len(client.calls) == 2
        prompt = client.calls[0]["prompt"]
        assert "'check' in chess" in prompt
        assert "an attack on the king" in prompt
        assert "1. check (examine) [verb/mental_state]" in prompt

    def test_abbreviation_is_recorded_as_a_variant(
        self, session: Session, config: DataSourceConfig
    ) -> None:
        sense = dict(_chess_check(), definition="In cricket, a way of being given out.")
        result = _add(
            session,
            config,
            _FakeClient(sense),
            word="leg before wicket",
            domain="cricket",
            disambiguation=None,
            hint=None,
            abbreviation="LBW",
        )

        lemma = session.query(Lemma).filter(Lemma.guid == result.guid).one()
        variant = session.query(VariantForm).filter(VariantForm.lemma_id == lemma.id).one()
        assert (variant.variant_form_text, variant.variant_kind) == (
            "LBW",
            VARIANT_KIND_ABBREVIATION,
        )


class TestExistingSenses:
    def test_covered_sense_is_tagged_not_duplicated(
        self, session: Session, config: DataSourceConfig
    ) -> None:
        result = _add(
            session,
            config,
            _FakeClient(_chess_check(covered_by=1)),
            word="queen",
            hint=None,
        )

        assert result.status == "covered"
        assert result.guid == "N01_001"
        queen = session.query(Lemma).filter(Lemma.lemma_text == "queen").one()
        assert read_tags(queen) == ["chess", "sports_games"]
        # Only tagged: level and label are left as they were.
        assert queen.difficulty_level == 200
        assert queen.disambiguation is None

    def test_relevel_moves_the_covered_sense(
        self, session: Session, config: DataSourceConfig
    ) -> None:
        result = _add(
            session,
            config,
            _FakeClient(_chess_check(covered_by=1)),
            word="queen",
            hint=None,
            relevel_existing=True,
        )

        assert result.status == "moved"
        queen = session.query(Lemma).filter(Lemma.lemma_text == "queen").one()
        assert queen.difficulty_level == 1202
        assert queen.disambiguation == "chess"
        assert queen.sense_prominence == SENSE_PROMINENCE_RARE

    def test_rerun_after_create_makes_no_llm_call(
        self, session: Session, config: DataSourceConfig
    ) -> None:
        created = _add(session, config, _FakeClient(_chess_check()))
        client = _FakeClient(_chess_check())

        result = _add(session, config, client)

        assert result.status == "already_exists"
        assert result.guid == created.guid
        assert client.calls == []

    def test_label_match_is_tagged_without_a_call(
        self, session: Session, config: DataSourceConfig
    ) -> None:
        # "check (examine)" carries the label asked for, so it is the sense --
        # and it is still marked as the list's.
        client = _FakeClient(_chess_check())

        result = _add(session, config, client, domain="checking", disambiguation="examine")

        assert result.status == "already_exists"
        assert client.calls == []
        check = session.query(Lemma).filter(Lemma.guid == "V01_001").one()
        assert read_tags(check) == ["chess", "sports_games"]

    def test_rerun_after_covered_matches_on_tags(
        self, session: Session, config: DataSourceConfig
    ) -> None:
        # The covered queen got tags but no label; the tags are what a re-run
        # recognises it by.
        _add(session, config, _FakeClient(_chess_check(covered_by=1)), word="queen")
        client = _FakeClient(_chess_check(covered_by=1))

        result = _add(session, config, client, word="queen")

        assert result.status == "already_exists"
        assert client.calls == []

    def test_covered_by_naming_no_sense_writes_nothing(
        self, session: Session, config: DataSourceConfig
    ) -> None:
        result = _add(session, config, _FakeClient(_chess_check(covered_by=5)))

        assert result.status == "error"
        assert session.query(Lemma).filter(Lemma.lemma_text == "check").count() == 1


class TestValidation:
    def test_invalid_pos_is_an_error(self, session: Session, config: DataSourceConfig) -> None:
        sense = dict(_chess_check(), pos="modal", pos_subtype="modal")

        result = _add(session, config, _FakeClient(sense))

        assert result.status == "error"
        assert session.query(Lemma).filter(Lemma.lemma_text == "check").count() == 1

    @pytest.mark.parametrize("subtype", ["noun_other", "other"])
    def test_catch_all_subtype_is_refused(
        self, session: Session, config: DataSourceConfig, subtype: str
    ) -> None:
        sense = dict(_chess_check(), pos_subtype=subtype)

        result = _add(session, config, _FakeClient(sense))

        assert result.status == "error"
        assert "catch-all" in (result.error or "")
        assert session.query(Lemma).filter(Lemma.lemma_text == "check").count() == 1

    def test_catch_all_is_not_offered(self, session: Session, config: DataSourceConfig) -> None:
        client = _FakeClient(_chess_check())
        _add(session, config, client)

        assert "pos_subtype" not in client.calls[0]["json_schema"].properties
        schema = client.calls[1]["json_schema"]
        assert "other" not in schema.properties["pos_subtype"].enum
        assert "- other:" not in client.calls[1]["context"]

    def test_closed_class_makes_no_subtype_call(
        self, session: Session, config: DataSourceConfig
    ) -> None:
        sense = {**_chess_check(), "pos": "preposition"}
        sense.pop("pos_subtype")
        client = _FakeClient(sense)
        result = _add(session, config, client)

        assert len(client.calls) == 1
        assert result.status == "created"
        assert result.pos_subtype == "preposition_other"

    def test_covered_sense_makes_no_subtype_call(
        self, session: Session, config: DataSourceConfig
    ) -> None:
        client = _FakeClient(_chess_check(covered_by=1))
        result = _add(session, config, client, word="queen", hint=None)

        assert result.status == "covered"
        assert len(client.calls) == 1

    def test_empty_domain_is_rejected_before_the_call(
        self, session: Session, config: DataSourceConfig
    ) -> None:
        client = _FakeClient(_chess_check())

        result = _add(session, config, client, domain="  ")

        assert result.status == "error"
        assert client.calls == []


class TestFixedSubtype:
    def test_fixed_subtype_overrides_the_model(
        self, session: Session, config: DataSourceConfig
    ) -> None:
        # The model is not asked, but a stray answer must not win either.
        sense = dict(_chess_check(), pos="verb", pos_subtype="mental_state")
        client = _FakeClient(sense)

        result = _add(session, config, client, pos_subtype="strategic_tactic")

        assert result.status == "created"
        lemma = session.query(Lemma).filter(Lemma.guid == result.guid).one()
        assert (lemma.pos_type, lemma.pos_subtype) == ("noun", "strategic_tactic")

    def test_fixed_subtype_is_not_asked_for(
        self, session: Session, config: DataSourceConfig
    ) -> None:
        client = _FakeClient(_chess_check())

        _add(session, config, client, pos_subtype="strategic_tactic")

        call = client.calls[0]
        assert "pos" not in call["json_schema"].properties
        assert "pos_subtype" not in call["json_schema"].properties
        assert "NOUN SUBTYPES" not in call["context"]
        assert "It is a noun." in call["prompt"]
        assert "an attack on the king" in call["prompt"]

    @pytest.mark.parametrize("subtype", ["no_such_subtype", "noun_other"])
    def test_unusable_subtype_is_rejected_before_the_call(
        self, session: Session, config: DataSourceConfig, subtype: str
    ) -> None:
        client = _FakeClient(_chess_check())

        result = _add(session, config, client, pos_subtype=subtype)

        assert result.status == "error"
        assert client.calls == []

    def test_covered_sense_keeps_its_own_subtype(
        self, session: Session, config: DataSourceConfig
    ) -> None:
        result = _add(
            session,
            config,
            _FakeClient(_chess_check(covered_by=1)),
            word="queen",
            hint=None,
            pos_subtype="strategic_tactic",
        )

        assert result.status == "covered"
        queen = session.query(Lemma).filter(Lemma.lemma_text == "queen").one()
        assert queen.pos_subtype == "small_movable_object"


def _basketball_dunk(pos_subtype: str) -> Dict[str, Any]:
    """The verb "dunk"; the one canned answer serves both calls."""
    return dict(
        _chess_check(),
        definition="In basketball, to score by pushing the ball down through the hoop.",
        pos_subtype=pos_subtype,
    )


class TestFixedPartOfSpeech:
    def test_part_of_speech_is_told_and_subtype_still_asked(
        self, session: Session, config: DataSourceConfig
    ) -> None:
        client = _FakeClient(_basketball_dunk("physical_action"))

        result = _add(session, config, client, word="dunk", domain="basketball", pos_type="verb")

        assert result.status == "created"
        assert (result.pos_type, result.pos_subtype) == ("verb", "physical_action")
        assert "pos" not in client.calls[0]["json_schema"].properties
        assert "It is a verb." in client.calls[0]["prompt"]
        assert len(client.calls) == 2

    def test_noun_tags_do_not_stand_in_for_the_verb(
        self, session: Session, config: DataSourceConfig
    ) -> None:
        # The same list tags both; the verb must still be described and made.
        noun = _add(session, config, _FakeClient(_chess_check()), word="dunk", pos_type="noun")
        client = _FakeClient(_basketball_dunk("physical_action"))

        verb = _add(session, config, client, word="dunk", pos_type="verb")

        assert (noun.status, verb.status) == ("created", "created")
        assert noun.guid != verb.guid
        assert client.calls

    def test_rerun_of_the_verb_matches_only_the_verb(
        self, session: Session, config: DataSourceConfig
    ) -> None:
        noun = _add(session, config, _FakeClient(_chess_check()), word="dunk", pos_type="noun")
        verb = _add(
            session,
            config,
            _FakeClient(_basketball_dunk("physical_action")),
            word="dunk",
            pos_type="verb",
        )
        client = _FakeClient(_chess_check())

        noun_again = _add(session, config, client, word="dunk", pos_type="noun")
        verb_again = _add(session, config, client, word="dunk", pos_type="verb")

        assert (noun_again.guid, verb_again.guid) == (noun.guid, verb.guid)
        assert client.calls == []

    def test_other_parts_of_speech_are_not_offered_as_matches(
        self, session: Session, config: DataSourceConfig
    ) -> None:
        # "check (examine)" is a verb; asked for the noun, it is not listed.
        client = _FakeClient(_chess_check())

        _add(session, config, client, pos_type="noun", disambiguation="chess")

        assert "examine" not in client.calls[0]["prompt"]

    def test_unknown_part_of_speech_is_rejected_before_the_call(
        self, session: Session, config: DataSourceConfig
    ) -> None:
        client = _FakeClient(_chess_check())

        result = _add(session, config, client, pos_type="gerund")

        assert result.status == "error"
        assert client.calls == []

    def test_subtype_of_another_part_of_speech_is_rejected(
        self, session: Session, config: DataSourceConfig
    ) -> None:
        client = _FakeClient(_chess_check())

        result = _add(session, config, client, pos_type="verb", pos_subtype="strategic_tactic")

        assert result.status == "error"
        assert client.calls == []


class TestSubtypeGuidance:
    def test_sense_context_lists_no_subtypes(self) -> None:
        context, _prompt, schema = build_sense_prompt("volley", "tennis", None, [])

        assert "SUBTYPES" not in context
        assert "pos_subtype" not in schema.properties

    def test_subtype_call_describes_only_its_part_of_speech(self) -> None:
        context, prompt, schema = build_subtype_prompt(
            "volley", "tennis", "In tennis, a shot hit before the ball bounces.", "noun"
        )

        assert "- participant_role: A slot a person fills" in context
        assert "- performance_technique: A named way" in context
        assert "- other:" not in context
        assert "- physical_action:" not in context  # a verb subtype
        assert "'volley' as a term of tennis" in prompt
        assert "other" not in (schema.properties["pos_subtype"].enum or [])
