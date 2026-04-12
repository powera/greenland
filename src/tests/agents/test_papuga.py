"""Tests for Papuga pronunciation coverage and queue behavior."""

from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from agents.papuga.agent import PapugaAgent
from agents.papuga.cli import _parse_language_codes, enqueue_papuga_work
from storage.backend.config import BackendType, DataSourceConfig
from storage.models.schema import Base, DerivativeForm, Lemma, LemmaTranslation
from workqueue.handlers.papuga import generate_pronunciations_for_lemma


def _build_config() -> DataSourceConfig:
    """Create a minimal Papuga config for tests."""
    return DataSourceConfig(
        backend_type=BackendType.SQLITE,
        sqlite_path=":memory:",
        model="gpt-5-mini",
    )


def test_check_missing_pronunciations_counts_partially_missing_forms() -> None:
    """Coverage mode should include forms missing either IPA or phonetic data."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    session = Session(engine)
    try:
        lemma = Lemma(
            lemma_text="eat",
            definition_text="to consume food",
            pos_type="verb",
            guid="V00_001",
        )
        session.add(lemma)
        session.flush()

        session.add_all(
            [
                DerivativeForm(
                    lemma_id=lemma.id,
                    derivative_form_text="eat",
                    language_code="en",
                    grammatical_form="infinitive",
                    is_base_form=True,
                    ipa_pronunciation="/iːt/",
                    phonetic_pronunciation=None,
                ),
                DerivativeForm(
                    lemma_id=lemma.id,
                    derivative_form_text="eats",
                    language_code="en",
                    grammatical_form="third_person_singular_present",
                    is_base_form=False,
                    ipa_pronunciation=None,
                    phonetic_pronunciation="EETS",
                ),
                DerivativeForm(
                    lemma_id=lemma.id,
                    derivative_form_text="ate",
                    language_code="en",
                    grammatical_form="past_tense",
                    is_base_form=False,
                    ipa_pronunciation="/eɪt/",
                    phonetic_pronunciation="AYT",
                ),
            ]
        )
        session.commit()

        agent = PapugaAgent(config=_build_config())
        with patch.object(agent, "get_session", return_value=session):
            result = agent.check_missing_pronunciations(lemma_id=lemma.id)

        assert result["total_missing"] == 2
        assert {item["word"] for item in result["missing_forms"]} == {"eat", "eats"}
    finally:
        session.close()
        engine.dispose()


def test_enqueue_papuga_work_enqueues_once_per_lemma_language() -> None:
    """Workqueue mode should enqueue lemma-level pronunciation tasks."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    session = Session(engine)
    try:
        lemma = Lemma(
            lemma_text="run",
            definition_text="to move quickly",
            pos_type="verb",
            guid="V00_002",
        )
        session.add(lemma)
        session.flush()

        session.add_all(
            [
                DerivativeForm(
                    lemma_id=lemma.id,
                    derivative_form_text="run",
                    language_code="en",
                    grammatical_form="infinitive",
                    is_base_form=True,
                    ipa_pronunciation=None,
                    phonetic_pronunciation=None,
                ),
                DerivativeForm(
                    lemma_id=lemma.id,
                    derivative_form_text="runs",
                    language_code="en",
                    grammatical_form="third_person_singular_present",
                    is_base_form=False,
                    ipa_pronunciation=None,
                    phonetic_pronunciation=None,
                ),
            ]
        )
        session.commit()

        captured_calls: list[dict[str, object]] = []

        class _Result:
            created = True

        def _fake_enqueue_task(db_session: Session, **kwargs: object) -> _Result:
            captured_calls.append(kwargs)
            return _Result()

        with patch("workqueue.task_queue.enqueue_task", side_effect=_fake_enqueue_task):
            results = enqueue_papuga_work(
                session=session,
                lemmas=[lemma],
                only_english=True,
                base_forms_only=False,
                dry_run=False,
            )

        assert results["enqueued"] == 1
        assert results["skipped"] == 0
        assert len(captured_calls) == 1
        assert captured_calls[0]["target_type"] == "lemma"
        assert captured_calls[0]["target_id"] == lemma.id
        assert captured_calls[0]["payload"] == {
            "lang_code": "en",
            "lemma_id": lemma.id,
            "all_forms_pronunciation": False,
        }
    finally:
        session.close()
        engine.dispose()


def test_parse_language_codes_normalizes_and_deduplicates() -> None:
    """CLI language parsing should normalize case/spacing and remove duplicates."""
    assert _parse_language_codes(" FR,es, fr ,ES ") == ["es", "fr"]
    assert _parse_language_codes("") is None


def test_enqueue_papuga_work_filters_selected_languages() -> None:
    """Workqueue enqueue should honor explicit language filters."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    session = Session(engine)
    try:
        lemma = Lemma(
            lemma_text="run",
            definition_text="to move quickly",
            pos_type="verb",
            guid="V00_00X",
        )
        session.add(lemma)
        session.flush()

        session.add_all(
            [
                DerivativeForm(
                    lemma_id=lemma.id,
                    derivative_form_text="run",
                    language_code="en",
                    grammatical_form="infinitive",
                    is_base_form=True,
                    ipa_pronunciation=None,
                    phonetic_pronunciation=None,
                ),
                DerivativeForm(
                    lemma_id=lemma.id,
                    derivative_form_text="corro",
                    language_code="es",
                    grammatical_form="present_1s",
                    is_base_form=False,
                    ipa_pronunciation=None,
                    phonetic_pronunciation=None,
                ),
            ]
        )
        session.commit()

        captured_calls = []

        class _Result:
            created = True

        def _fake_enqueue_task(db_session: Session, **kwargs: object) -> _Result:
            captured_calls.append(kwargs)
            return _Result()

        with patch("workqueue.task_queue.enqueue_task", side_effect=_fake_enqueue_task):
            results = enqueue_papuga_work(
                session=session,
                lemmas=[lemma],
                only_english=False,
                language_codes=["es"],
                all_forms_pronunciation=True,
                dry_run=False,
            )

        assert results["enqueued"] == 1
        assert len(captured_calls) == 1
        payload = captured_calls[0]["payload"]
        assert isinstance(payload, dict)
        assert payload["lang_code"] == "es"
    finally:
        session.close()
        engine.dispose()


def test_check_missing_pronunciations_includes_lemma_translation_targets() -> None:
    """Coverage mode should include lemma translations with missing pronunciation data."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    session = Session(engine)
    try:
        lemma = Lemma(
            lemma_text="dog",
            definition_text="a domesticated canine",
            pos_type="noun",
            guid="N00_003",
        )
        session.add(lemma)
        session.flush()
        session.add(
            LemmaTranslation(
                lemma_id=lemma.id,
                language_code="es",
                translation="perro",
                ipa_pronunciation=None,
                phonetic_pronunciation=None,
            )
        )
        session.commit()

        agent = PapugaAgent(config=_build_config())
        with patch.object(agent, "get_session", return_value=session):
            result = agent.check_missing_pronunciations(lemma_id=lemma.id, only_english=False)

        assert result["total_missing"] == 1
        assert result["missing_forms"][0]["target_type"] == "lemma_translation"
        assert result["missing_forms"][0]["word"] == "perro"
    finally:
        session.close()
        engine.dispose()


def test_generate_pronunciations_for_lemma_updates_lemma_translation() -> None:
    """Generating pronunciation data should also fill lemma translation pronunciation fields."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    session = Session(engine)
    try:
        lemma = Lemma(
            lemma_text="dog",
            definition_text="a domesticated canine",
            pos_type="noun",
            guid="N00_004",
        )
        session.add(lemma)
        session.flush()
        session.add(
            LemmaTranslation(
                lemma_id=lemma.id,
                language_code="es",
                translation="perro",
                ipa_pronunciation=None,
                phonetic_pronunciation=None,
            )
        )
        session.commit()

        with patch(
            "workqueue.handlers.papuga.generate_pronunciation_for_form",
            return_value=(True, "/ˈpero/", "PEH-roh"),
        ):
            generated_count, errors = generate_pronunciations_for_lemma(
                session=session,
                lemma=lemma,
                lang_code="es",
                config=_build_config(),
            )

        translation_row = (
            session.query(LemmaTranslation)
            .filter(LemmaTranslation.lemma_id == lemma.id, LemmaTranslation.language_code == "es")
            .first()
        )
        assert generated_count == 1
        assert errors == []
        assert translation_row is not None
        assert translation_row.ipa_pronunciation == "/ˈpero/"
        assert translation_row.phonetic_pronunciation == "PEH-roh"
    finally:
        session.close()
        engine.dispose()


def test_generate_pronunciations_for_lemma_reuses_existing_base_form_pronunciations() -> None:
    """Translation pronunciation backfill should reuse an already-populated base form."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    session = Session(engine)
    try:
        lemma = Lemma(
            lemma_text="eat",
            definition_text="to consume food",
            pos_type="verb",
            guid="V00_005",
        )
        session.add(lemma)
        session.flush()
        session.add(
            LemmaTranslation(
                lemma_id=lemma.id,
                language_code="es",
                translation="comer",
                ipa_pronunciation=None,
                phonetic_pronunciation=None,
            )
        )
        session.add(
            DerivativeForm(
                lemma_id=lemma.id,
                derivative_form_text="comer",
                language_code="es",
                grammatical_form="infinitive",
                is_base_form=True,
                ipa_pronunciation="/koˈmeɾ/",
                phonetic_pronunciation="koh-MEHR",
            )
        )
        session.commit()

        with patch("workqueue.handlers.papuga.generate_pronunciation_for_form") as mocked_generate:
            generated_count, errors = generate_pronunciations_for_lemma(
                session=session,
                lemma=lemma,
                lang_code="es",
                config=_build_config(),
            )

        translation_row = (
            session.query(LemmaTranslation)
            .filter(LemmaTranslation.lemma_id == lemma.id, LemmaTranslation.language_code == "es")
            .first()
        )
        assert generated_count == 1
        assert errors == []
        assert translation_row is not None
        assert translation_row.ipa_pronunciation == "/koˈmeɾ/"
        assert translation_row.phonetic_pronunciation == "koh-MEHR"
        mocked_generate.assert_not_called()
    finally:
        session.close()
        engine.dispose()


def test_generate_pronunciations_for_lemma_updates_rhyme_key_for_english_forms() -> None:
    """English pronunciation generation should keep the derivative rhyme key in sync."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    session = Session(engine)
    try:
        lemma = Lemma(
            lemma_text="cat",
            definition_text="a feline",
            pos_type="noun",
            guid="N00_006",
        )
        session.add(lemma)
        session.flush()
        session.add(
            DerivativeForm(
                lemma_id=lemma.id,
                derivative_form_text="cat",
                language_code="en",
                grammatical_form="singular",
                is_base_form=True,
                ipa_pronunciation=None,
                phonetic_pronunciation=None,
            )
        )
        session.commit()

        with patch(
            "workqueue.handlers.papuga.generate_pronunciation_for_form",
            return_value=(True, "/kæt/", "KAT"),
        ):
            generated_count, errors = generate_pronunciations_for_lemma(
                session=session,
                lemma=lemma,
                lang_code="en",
                config=_build_config(),
            )
            session.commit()

        refreshed_form = (
            session.query(DerivativeForm).filter(DerivativeForm.lemma_id == lemma.id).one()
        )
        assert generated_count == 1
        assert errors == []
        assert refreshed_form.ipa_pronunciation == "/kæt/"
        assert refreshed_form.rhyme_key == "æt"
    finally:
        session.close()
        engine.dispose()


def test_generate_pronunciations_for_lemma_creates_english_base_form_when_missing() -> None:
    """Lemma-only English entries should still get a stored base-form pronunciation."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    session = Session(engine)
    try:
        lemma = Lemma(
            lemma_text="quickly",
            definition_text="at a fast speed",
            pos_type="adverb",
            guid="D00_007",
        )
        session.add(lemma)
        session.commit()

        with patch(
            "workqueue.handlers.papuga.generate_pronunciation_for_form",
            return_value=(True, "/ˈkwɪkli/", "KWIK-lee"),
        ):
            generated_count, errors = generate_pronunciations_for_lemma(
                session=session,
                lemma=lemma,
                lang_code="en",
                config=_build_config(),
            )
            session.commit()

        generated_form = (
            session.query(DerivativeForm)
            .filter(DerivativeForm.lemma_id == lemma.id, DerivativeForm.language_code == "en")
            .one()
        )
        assert generated_count == 1
        assert errors == []
        assert generated_form.derivative_form_text == "quickly"
        assert generated_form.grammatical_form == "positive"
        assert generated_form.is_base_form is True
        assert generated_form.ipa_pronunciation == "/ˈkwɪkli/"
        assert generated_form.phonetic_pronunciation == "KWIK-lee"
    finally:
        session.close()
        engine.dispose()


def test_generate_pronunciations_for_lemma_skips_english_future_by_default() -> None:
    """Default pronunciation generation should skip optional English *_future forms."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    session = Session(engine)
    try:
        lemma = Lemma(
            lemma_text="walk",
            definition_text="to move on foot",
            pos_type="verb",
            guid="V00_008",
        )
        session.add(lemma)
        session.flush()
        session.add_all(
            [
                DerivativeForm(
                    lemma_id=lemma.id,
                    derivative_form_text="walk",
                    language_code="en",
                    grammatical_form="infinitive",
                    is_base_form=True,
                    ipa_pronunciation=None,
                    phonetic_pronunciation=None,
                ),
                DerivativeForm(
                    lemma_id=lemma.id,
                    derivative_form_text="will walk",
                    language_code="en",
                    grammatical_form="1s_future",
                    is_base_form=False,
                    ipa_pronunciation=None,
                    phonetic_pronunciation=None,
                ),
            ]
        )
        session.commit()

        with patch(
            "workqueue.handlers.papuga.generate_pronunciation_for_form",
            return_value=(True, "/wɔk/", "WAWK"),
        ) as mocked_generate:
            generated_count, errors = generate_pronunciations_for_lemma(
                session=session,
                lemma=lemma,
                lang_code="en",
                config=_build_config(),
            )
            session.commit()

        refreshed_forms = (
            session.query(DerivativeForm)
            .filter(DerivativeForm.lemma_id == lemma.id)
            .order_by(DerivativeForm.id)
            .all()
        )
        assert generated_count == 1
        assert errors == []
        assert mocked_generate.call_count == 1
        assert refreshed_forms[0].ipa_pronunciation == "/wɔk/"
        assert refreshed_forms[1].ipa_pronunciation is None
    finally:
        session.close()
        engine.dispose()


def test_generate_pronunciations_for_lemma_includes_english_future_with_override() -> None:
    """Override mode should include optional English *_future forms."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    session = Session(engine)
    try:
        lemma = Lemma(
            lemma_text="walk",
            definition_text="to move on foot",
            pos_type="verb",
            guid="V00_009",
        )
        session.add(lemma)
        session.flush()
        session.add_all(
            [
                DerivativeForm(
                    lemma_id=lemma.id,
                    derivative_form_text="walk",
                    language_code="en",
                    grammatical_form="infinitive",
                    is_base_form=True,
                    ipa_pronunciation=None,
                    phonetic_pronunciation=None,
                ),
                DerivativeForm(
                    lemma_id=lemma.id,
                    derivative_form_text="will walk",
                    language_code="en",
                    grammatical_form="1s_future",
                    is_base_form=False,
                    ipa_pronunciation=None,
                    phonetic_pronunciation=None,
                ),
            ]
        )
        session.commit()

        with patch(
            "workqueue.handlers.papuga.generate_pronunciation_for_form",
            return_value=(True, "/wɔk/", "WAWK"),
        ) as mocked_generate:
            generated_count, errors = generate_pronunciations_for_lemma(
                session=session,
                lemma=lemma,
                lang_code="en",
                config=_build_config(),
                all_forms_pronunciation=True,
            )
            session.commit()

        refreshed_forms = (
            session.query(DerivativeForm)
            .filter(DerivativeForm.lemma_id == lemma.id)
            .order_by(DerivativeForm.id)
            .all()
        )
        assert generated_count == 2
        assert errors == []
        assert mocked_generate.call_count == 2
        assert refreshed_forms[0].ipa_pronunciation == "/wɔk/"
        assert refreshed_forms[1].ipa_pronunciation == "/wɔk/"
    finally:
        session.close()
        engine.dispose()


def test_enqueue_papuga_work_respects_optional_form_override() -> None:
    """Queue selection should skip English *_future by default and include with override."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    session = Session(engine)
    try:
        lemma = Lemma(
            lemma_text="jump",
            definition_text="to leap",
            pos_type="verb",
            guid="V00_010",
        )
        session.add(lemma)
        session.flush()
        session.add(
            DerivativeForm(
                lemma_id=lemma.id,
                derivative_form_text="will jump",
                language_code="en",
                grammatical_form="1s_future",
                is_base_form=False,
                ipa_pronunciation=None,
                phonetic_pronunciation=None,
            )
        )
        session.commit()

        with patch("workqueue.task_queue.enqueue_task") as mocked_enqueue:
            default_results = enqueue_papuga_work(
                session=session,
                lemmas=[lemma],
                only_english=True,
                all_forms_pronunciation=False,
                dry_run=False,
            )
            override_results = enqueue_papuga_work(
                session=session,
                lemmas=[lemma],
                only_english=True,
                all_forms_pronunciation=True,
                dry_run=False,
            )

        assert default_results["enqueued"] == 0
        assert override_results["enqueued"] == 1
        assert mocked_enqueue.call_count == 1
        assert mocked_enqueue.call_args.kwargs["payload"]["all_forms_pronunciation"] is True
    finally:
        session.close()
        engine.dispose()
