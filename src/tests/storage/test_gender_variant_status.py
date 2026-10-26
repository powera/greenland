"""A person noun's gender answer: variant rows plus a gender_variant_status per language."""

from typing import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import storage.models  # noqa: F401
from storage.crud.gender_variant import (
    GenderVariantAnswer,
    convert_llm_response_to_gender_answers,
    get_gender_variant_status,
    needs_gender_variant_check,
    store_gender_variant_answer,
)
from storage.crud.uncertain_llm_result import get_uncertain_llm_result
from storage.crud.variant_form import add_variant_form
from storage.models.guid_prefixes import human_subtypes, is_human_subtype
from storage.models.schema import Base, Lemma
from storage.models.variant_form import (
    GENDER_VARIANT_STATUS_FACT,
    VARIANT_KIND_GENDER,
    VariantForm,
)
from storage.translation_helpers import set_translation
from words.translation_populate import store_populated_translations

SOURCE = "test/gender-variant-status"


@pytest.fixture()
def session() -> Iterator[Session]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as database_session:
        yield database_session
    engine.dispose()


def _lemma(session: Session, guid: str, word: str, subtype: str) -> Lemma:
    lemma = Lemma(
        guid=guid,
        lemma_text=word,
        definition_text=f"A {word}.",
        pos_type="noun",
        pos_subtype=subtype,
    )
    session.add(lemma)
    session.flush()
    return lemma


def _rows(session: Session, lemma: Lemma, language: str) -> dict[str, tuple[str, str | None]]:
    return {
        row.variant_key: (row.variant_form_text, row.grammatical_gender)
        for row in session.query(VariantForm).filter_by(
            lemma_id=lemma.id, language_code=language, variant_kind=VARIANT_KIND_GENDER
        )
    }


def test_person_subtypes_follow_kind_of_human() -> None:
    assert is_human_subtype("noun", "human")
    assert is_human_subtype("noun", "occupation")
    assert is_human_subtype("noun", "nationality")
    assert not is_human_subtype("noun", "animal")
    assert not is_human_subtype("verb", "human")
    assert not is_human_subtype("noun", None)
    assert {"human", "family_relation", "occupation", "nationality"} <= set(human_subtypes())


def test_pair_stores_both_words_and_marks_the_language(session: Session) -> None:
    actor = _lemma(session, "N36_047", "actor", "occupation")
    answer = GenderVariantAnswer("actor", "actriz", "masculine", "Feminine")
    assert store_gender_variant_answer(session, actor, "es", answer, SOURCE) == "pair"
    assert _rows(session, actor, "es") == {
        "male": ("actor", "masculine"),
        "female": ("actriz", "feminine"),
    }
    assert get_gender_variant_status(session, actor.id, "es") == "pair"
    assert not needs_gender_variant_check(session, actor, "es")


def test_common_gender_noun_is_a_pair_of_the_same_word(session: Session) -> None:
    student = _lemma(session, "N01_100", "student", "human")
    answer = GenderVariantAnswer("estudiante", "estudiante", "masculine", "feminine")
    assert store_gender_variant_answer(session, student, "es", answer, SOURCE) == "pair"
    assert _rows(session, student, "es")["female"] == ("estudiante", "feminine")


def test_english_never_gets_a_grammatical_gender(session: Session) -> None:
    actor = _lemma(session, "N36_047", "actor", "occupation")
    answer = GenderVariantAnswer("actor", "actress", "masculine", "feminine")
    store_gender_variant_answer(session, actor, "en", answer, SOURCE)
    assert _rows(session, actor, "en") == {"male": ("actor", None), "female": ("actress", None)}


def test_none_writes_only_the_status(session: Session) -> None:
    teacher = _lemma(session, "N36_001", "teacher", "occupation")
    assert store_gender_variant_answer(session, teacher, "zh", GenderVariantAnswer(), SOURCE) == (
        "none"
    )
    assert _rows(session, teacher, "zh") == {}
    assert get_gender_variant_status(session, teacher.id, "zh") == "none"
    assert get_gender_variant_status(session, teacher.id, "fr") is None
    assert needs_gender_variant_check(session, teacher, "fr")


def test_same_word_and_gender_for_both_is_none(session: Session) -> None:
    person = _lemma(session, "N01_060", "person", "human")
    answer = GenderVariantAnswer("žmogus", "žmogus", "masculine", "masculine")
    assert store_gender_variant_answer(session, person, "lt", answer, SOURCE) == "none"
    assert _rows(session, person, "lt") == {}


def test_one_sided_answer_is_refused(session: Session) -> None:
    teacher = _lemma(session, "N36_001", "teacher", "occupation")
    answer = GenderVariantAnswer(male="", female="maestra")
    assert store_gender_variant_answer(session, teacher, "es", answer, SOURCE) is None
    assert get_gender_variant_status(session, teacher.id, "es") is None


def test_non_person_noun_is_rejected(session: Session) -> None:
    dog = _lemma(session, "N02_001", "dog", "animal")
    with pytest.raises(ValueError, match="not a person noun"):
        store_gender_variant_answer(session, dog, "es", GenderVariantAnswer(), SOURCE)
    with pytest.raises(ValueError, match="person noun"):
        add_variant_form(
            session,
            dog,
            "perra",
            "es",
            "female",
            "noun/es_singular",
            variant_kind=VARIANT_KIND_GENDER,
            link_word_token=False,
        )
    assert not needs_gender_variant_check(session, dog, "es")


def test_checked_or_hand_written_language_is_left_alone(session: Session) -> None:
    actor = _lemma(session, "N36_047", "actor", "occupation")
    store_gender_variant_answer(
        session, actor, "es", GenderVariantAnswer("actor", "actriz"), SOURCE
    )
    assert store_gender_variant_answer(session, actor, "es", GenderVariantAnswer(), SOURCE) is None
    # Spanish genders are derived from the key when none is given.
    assert _rows(session, actor, "es")["female"] == ("actriz", "feminine")

    # Rows a person wrote, with no status yet: not asked about again.
    add_variant_form(
        session,
        actor,
        "acteur",
        "fr",
        "male",
        "noun/fr_singular",
        variant_kind=VARIANT_KIND_GENDER,
        is_base_form=True,
        link_word_token=False,
    )
    assert not needs_gender_variant_check(session, actor, "fr")
    assert store_gender_variant_answer(session, actor, "fr", GenderVariantAnswer(), SOURCE) is None


def test_replace_clears_the_old_answer(session: Session) -> None:
    cousin = _lemma(session, "N35_076", "cousin", "family_relation")
    store_gender_variant_answer(
        session, cousin, "en", GenderVariantAnswer("cousin", "cousin"), SOURCE
    )
    assert (
        store_gender_variant_answer(
            session, cousin, "en", GenderVariantAnswer(), SOURCE, replace_existing=True
        )
        == "none"
    )
    assert _rows(session, cousin, "en") == {}
    assert get_gender_variant_status(session, cousin.id, "en") == "none"


def test_low_confidence_records_the_question_as_uncertain(session: Session) -> None:
    teacher = _lemma(session, "N36_001", "teacher", "occupation")
    stored = store_gender_variant_answer(
        session,
        teacher,
        "lt",
        GenderVariantAnswer("mokytojas", "mokytoja"),
        SOURCE,
        confidence=0.3,
        model="test-model",
    )
    assert stored is None
    assert get_gender_variant_status(session, teacher.id, "lt") is None
    assert get_uncertain_llm_result(session, GENDER_VARIANT_STATUS_FACT, "lt", lemma_id=teacher.id)


def test_converter_reads_only_languages_that_answered() -> None:
    answers = convert_llm_response_to_gender_answers(
        {
            "spanish_translation": {
                "translation": "actor",
                "male": "actor",
                "female": "actriz",
                "male_grammatical_gender": "masculine",
                "female_grammatical_gender": "feminine",
            },
            "french_translation": {"translation": "acteur", "confidence": 0.9},
            "chinese_translation": {"translation": "演员", "male": "", "female": ""},
        }
    )
    assert set(answers) == {"es", "zh"}
    assert answers["es"].is_pair
    assert answers["zh"].is_none


def test_populate_stores_translation_and_gender_together(session: Session) -> None:
    actor = _lemma(session, "N36_047", "actor", "occupation")
    set_translation(session, actor, "fr", "acteur")
    outcome = store_populated_translations(
        session,
        actor,
        {
            "spanish_translation": {
                "translation": "actor",
                "confidence": 0.95,
                "male": "actor",
                "female": "actriz",
                "male_grammatical_gender": "masculine",
                "female_grammatical_gender": "feminine",
            },
            # Already translated: the translation is kept, the gender check is new.
            "french_translation": {
                "translation": "comédien",
                "confidence": 0.9,
                "male": "acteur",
                "female": "actrice",
                "male_grammatical_gender": "masculine",
                "female_grammatical_gender": "feminine",
            },
        },
        ["es", "fr"],
        SOURCE,
    )
    assert outcome.written == ["es"]
    assert outcome.gender_checked == ["es", "fr"]
    assert _rows(session, actor, "fr")["female"] == ("actrice", "feminine")


def test_populate_skips_gender_for_an_uncertain_translation(session: Session) -> None:
    actor = _lemma(session, "N36_047", "actor", "occupation")
    outcome = store_populated_translations(
        session,
        actor,
        {
            "spanish_translation": {
                "translation": "actor",
                "confidence": 0.2,
                "male": "actor",
                "female": "actriz",
            }
        },
        ["es"],
        SOURCE,
    )
    assert outcome.uncertain == ["es"]
    assert outcome.gender_checked == []
    assert get_gender_variant_status(session, actor.id, "es") is None


def test_gender_pattern_decides_the_answer() -> None:
    from storage.crud.gender_variant import gender_answer_from_fields

    common = gender_answer_from_fields({"gender_pattern": "common_gender"}, "artista")
    assert common == GenderVariantAnswer("artista", "artista", "masculine", "feminine")
    assert common.is_pair
    # one_word wins over words the model filled in anyway.
    one = gender_answer_from_fields(
        {"gender_pattern": "one_word", "male": "clown", "female": "clownesse"}, "clown"
    )
    assert one is not None and one.is_none
    separate = gender_answer_from_fields(
        {"gender_pattern": "separate_words", "male": "actor", "female": "actriz"}, "actor"
    )
    assert separate == GenderVariantAnswer("actor", "actriz")


def test_converter_builds_common_gender_from_the_translation() -> None:
    answers = convert_llm_response_to_gender_answers(
        {"spanish_translation": {"translation": "cantante", "gender_pattern": "common_gender"}}
    )
    assert answers["es"] == GenderVariantAnswer("cantante", "cantante", "masculine", "feminine")


def test_person_noun_requests_carry_fewer_languages(session: Session) -> None:
    from words.translation_populate import populate_groups

    actor = _lemma(session, "N36_047", "actor", "occupation")
    dog = _lemma(session, "N02_001", "dog", "animal")
    languages = ["lt", "zh", "fr", "es", "es-419", "de", "it", "nl", "pt", "sv"]
    assert [len(group) for group in populate_groups(languages, actor)] == [6, 4]
    assert [len(group) for group in populate_groups(languages, dog)] == [10]


def test_common_gender_in_an_ungendered_language_is_none(session: Session) -> None:
    tailor = _lemma(session, "N36_070", "tailor", "occupation")
    answer = GenderVariantAnswer("tailor", "tailor", "masculine", "feminine")
    assert store_gender_variant_answer(session, tailor, "en", answer, SOURCE) == "none"
    assert _rows(session, tailor, "en") == {}
