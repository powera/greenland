"""Exercise Lape2's actual planner, structured requests and durable writes offline."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator
from unittest.mock import Mock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from agents.lape2 import results as lape2_results
from agents.lape2.catalog import CATALOG
from agents.lape2.cli import get_argument_parser, main, select_plans
from agents.lape2.job import LAPE2_JOB, apply, prepare
from agents.lape2.planner import RequestPlan, plan_request, stored_values
from agents.lape2.query import build_query
from agents.lape2.results import apply_answers, validate_answer
from clients.lib import LLMCallsDisabledError
from clients.types import LLMCall, Response
from storage.config.grammar_fact_registry import is_release_grammar_fact_type
from storage.crud.uncertain_llm_result import get_uncertain_llm_result
from storage.models import Base, Lemma
from storage.models.grammar_fact import GrammarFact
from storage.models.lemma_fact import LemmaFact
from storage.translation_helpers import set_translation
from workqueue.llm_batch import StageContext, run_inline
from workqueue.registry import get_llm_job

CTX = StageContext(model="fake-model", via="inline")


@pytest.fixture()
def session() -> Iterator[Session]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as database_session:
        yield database_session
    engine.dispose()


def lemma(session: Session, text: str = "cat", pos: str = "noun", **translations: str) -> Lemma:
    word = Lemma(
        lemma_text=text,
        pos_type=pos,
        guid=f"test-{text}",
        definition_text=f"One particular sense of {text}",
        disambiguation="this sense",
        pos_subtype="animal" if pos == "noun" else None,
    )
    session.add(word)
    session.flush()
    for language, translation in translations.items():
        set_translation(session, word, language, translation)
    session.commit()
    return word


def answer(value: str, confidence: float = 0.95) -> dict[str, Any]:
    return {"value": value, "confidence": confidence, "explanation": "For this sense"}


def save(session: Session, plan: RequestPlan, data: dict[str, Any]) -> Any:
    report = apply_answers(session, plan, data, min_confidence=0.7, model="fake-model")
    session.commit()
    return report


def test_one_query_has_exact_missing_questions_across_languages(session: Session) -> None:
    word = lemma(session, fr="chat", zh="猫")
    session.add(
        GrammarFact(
            lemma_id=word.id,
            language_code="fr",
            fact_type="grammatical_gender",
            fact_value="masculine",
        )
    )
    session.commit()
    plan = plan_request(session, word, ["en", "fr", "zh", "de"])
    query = build_query(plan)
    assert "fr__grammatical_gender" not in query.schema.properties
    assert {
        "fr__countability",
        "zh__measure_words",
        "en__plural",
        "concept__individuation",
    } <= query.schema.properties.keys()
    assert not any(identifier.startswith("de__") for identifier in query.schema.properties)
    assert not any("verb" in identifier for identifier in query.schema.properties)
    assert "this sense" in query.prompt and "猫" in query.prompt
    assert "fr__grammatical_gender" in query.prompt  # supplied as known context
    assert session.query(GrammarFact).count() == 1
    countability_schema = query.schema.properties["en__countability"].object_schema
    assert countability_schema is not None
    countability_values = countability_schema.properties["value"].enum
    assert countability_values is not None and "countable" in countability_values
    restored = RequestPlan.from_dict(json.loads(json.dumps(plan.to_dict())))
    assert restored == plan
    assert build_query(restored) == query


def test_context_is_fixed_and_form_filters_add_prerequisites(session: Session) -> None:
    word = lemma(session)
    plural_plan = plan_request(session, word, ["en"], facts=["plural"])
    assert {question.key for question in plural_plan.questions} == {"en__plural", "en__number_type"}
    adjective = lemma(session, "happy", "adjective")
    comparison_plan = plan_request(session, adjective, ["en"], facts=["comparative"])
    assert {question.key for question in comparison_plan.questions} == {
        "en__comparative",
        "en__gradability",
    }
    assert build_query(plural_plan).context == build_query(comparison_plan).context


def test_explicit_regular_paradigm_and_plural_completion_are_durable(session: Session) -> None:
    word = lemma(session)
    plan = plan_request(session, word, ["en"], facts=["plural", "countability"])
    report = save(
        session,
        plan,
        {
            "en__plural": answer("cats"),
            "en__number_type": answer("regular"),
            "en__countability": answer("countable"),
        },
    )
    assert report.written == 3 and report.rejected == 0
    assert stored_values(session, word.id) == {
        "en__number_type": "regular",
        "en__countability": "countable",
        "en__plural_status": "regular",
    }
    assert not plan_request(session, word, ["en"], facts=["plural", "countability"]).questions
    assert is_release_grammar_fact_type("en", "plural_status")


def test_irregular_plural_stores_override_and_status_together(session: Session) -> None:
    word = lemma(session, "mouse")
    plan = plan_request(session, word, ["en"], facts=["plural"])
    report = save(
        session, plan, {"en__number_type": answer("regular"), "en__plural": answer("mice")}
    )
    assert report.written == 2
    assert stored_values(session, word.id)["en__plural"] == "mice"
    assert stored_values(session, word.id)["en__plural_status"] == "override"


def test_singular_only_and_non_gradable_have_explicit_inapplicable_checks(session: Session) -> None:
    noun = lemma(session, "furniture")
    noun_plan = plan_request(session, noun, ["en"], facts=["plural"])
    assert (
        save(
            session,
            noun_plan,
            {"en__number_type": answer("singulare_tantum"), "en__plural": answer("")},
        ).written
        == 2
    )
    assert stored_values(session, noun.id)["en__plural_status"] == "not_applicable"
    adjective = lemma(session, "wooden", "adjective")
    adjective_plan = plan_request(session, adjective, ["en"], facts=["comparative", "superlative"])
    assert (
        save(
            session,
            adjective_plan,
            {
                "en__gradability": answer("non_gradable"),
                "en__comparative": answer(""),
                "en__superlative": answer(""),
            },
        ).written
        == 3
    )
    assert stored_values(session, adjective.id)["en__comparative_status"] == "not_applicable"


def test_multilingual_answers_and_concepts_persist_independently(session: Session) -> None:
    word = lemma(session, fr="chat", zh="猫")
    plan = plan_request(
        session, word, ["fr", "zh"], facts=["grammatical_gender", "measure_words", "individuation"]
    )
    report = save(
        session,
        plan,
        {
            "fr__grammatical_gender": answer("masculine"),
            "zh__measure_words": answer("只"),
            "concept__individuation": answer("individual"),
        },
    )
    assert report.written == 3
    assert session.query(LemmaFact).one().fact_value == "individual"
    assert not plan_request(
        session, word, ["fr", "zh"], facts=["grammatical_gender", "measure_words", "individuation"]
    ).questions


def test_uncertainty_is_per_answer_and_retry_only_includes_unfinished_facts(
    session: Session,
) -> None:
    word = lemma(session, fr="chat")
    plan = plan_request(session, word, ["en", "fr"], facts=["countability"])
    report = save(
        session,
        plan,
        {"en__countability": answer("countable"), "fr__countability": answer("countable", 0.4)},
    )
    assert (report.written, report.rejected) == (1, 1)
    assert get_uncertain_llm_result(session, "countability", "fr", lemma_id=word.id) is not None
    retry = plan_request(session, word, ["en", "fr"], facts=["countability"], retry_uncertain=True)
    assert [question.key for question in retry.questions] == ["fr__countability"]
    assert not plan_request(session, word, ["fr"], facts=["countability"]).questions
    save(session, retry, {"fr__countability": answer("countable")})
    assert get_uncertain_llm_result(session, "countability", "fr", lemma_id=word.id) is None


def test_low_confidence_form_does_not_mark_check_complete(session: Session) -> None:
    word = lemma(session)
    plan = plan_request(session, word, ["en"], facts=["plural"])
    save(
        session,
        plan,
        {"en__number_type": answer("regular", 0.4), "en__plural": answer("cats", 0.4)},
    )
    assert not stored_values(session, word.id)
    assert get_uncertain_llm_result(session, "plural_status", "en", lemma_id=word.id) is not None


def test_confident_form_waits_for_uncertain_classification(session: Session) -> None:
    word = lemma(session)
    plan = plan_request(session, word, ["en"], facts=["plural"])
    report = save(
        session, plan, {"en__number_type": answer("regular", 0.4), "en__plural": answer("cats")}
    )
    assert report.written == 0
    assert "number_type" in report.errors["en__plural"]


@pytest.mark.parametrize(
    "raw",
    [
        answer("bogus"),
        answer(""),
        answer("countable", float("nan")),
        answer("countable", float("inf")),
        answer("countable", True),
        answer("countable", -0.1),
        {"value": "countable"},
        {**answer("countable"), "unexpected": 1},
    ],
)
def test_malformed_or_invalid_answers_are_rejected(session: Session, raw: Any) -> None:
    word = lemma(session)
    question = plan_request(session, word, ["en"], facts=["countability"]).questions[0]
    with pytest.raises(ValueError):
        validate_answer(question, raw)


def test_bad_answer_does_not_discard_valid_sibling_or_accept_unrequested_data(
    session: Session,
) -> None:
    word = lemma(session, fr="chat")
    plan = plan_request(session, word, ["en", "fr"], facts=["countability"])
    report = save(
        session,
        plan,
        {
            "en__countability": answer("countable"),
            "fr__countability": answer("invented"),
            "fr__grammatical_gender": answer("masculine"),
        },
    )
    assert (report.written, report.rejected) == (1, 2)
    assert stored_values(session, word.id) == {"en__countability": "countable"}


@pytest.mark.parametrize("changed", ["sense", "translation", "known_fact"])
def test_stale_request_is_rejected_before_writing(session: Session, changed: str) -> None:
    word = lemma(session, fr="chat")
    known = GrammarFact(
        lemma_id=word.id, language_code="fr", fact_type="grammatical_gender", fact_value="masculine"
    )
    session.add(known)
    session.commit()
    plan = plan_request(session, word, ["fr"], facts=["countability"])
    if changed == "sense":
        word.definition_text = "Another sense"
    elif changed == "translation":
        set_translation(session, word, "fr", "félin")
    else:
        known.fact_value = "common"
    session.commit()
    with pytest.raises(ValueError, match="Stale request"):
        save(session, plan, {"fr__countability": answer("countable")})
    assert "fr__countability" not in stored_values(session, word.id)


def test_newly_curated_answer_is_preserved_and_partial_results_are_idempotent(
    session: Session,
) -> None:
    word = lemma(session, fr="chat")
    plan = plan_request(session, word, ["en", "fr"], facts=["countability"])
    session.add(
        GrammarFact(
            lemma_id=word.id,
            language_code="fr",
            fact_type="countability",
            fact_value="both",
            verified=True,
        )
    )
    session.commit()
    data = {"en__countability": answer("countable"), "fr__countability": answer("countable")}
    report = save(session, plan, data)
    assert (report.written, report.skipped) == (1, 1)
    assert stored_values(session, word.id)["fr__countability"] == "both"
    assert save(session, plan, data).skipped == 2


def test_existing_override_without_status_is_not_overwritten(session: Session) -> None:
    word = lemma(session, "mouse")
    session.add(
        GrammarFact(
            lemma_id=word.id,
            language_code="en",
            fact_type="plural",
            fact_value="mice",
            verified=True,
        )
    )
    session.commit()
    plan = plan_request(session, word, ["en"], facts=["plural"])
    report = save(
        session, plan, {"en__number_type": answer("regular"), "en__plural": answer("mouses")}
    )
    assert "en__plural" in report.errors
    assert stored_values(session, word.id)["en__plural"] == "mice"
    assert "en__plural_status" not in stored_values(session, word.id)


def test_verb_principal_parts_are_in_same_call_as_classifications(session: Session) -> None:
    word = lemma(session, "walk", "verb", fr="marcher")
    plan = plan_request(session, word, ["en", "fr"])
    keys = {question.key for question in plan.questions}
    assert {
        "en__past",
        "en__past_participle",
        "en__verb_transitivity",
        "fr__auxiliary_verb",
        "fr__verb_reflexivity",
    } <= keys
    assert "en__plural" not in keys
    data = {
        "en__past": answer("walked"),
        "en__past_participle": answer("walked"),
        "en__verb_transitivity": answer("intransitive"),
        "fr__auxiliary_verb": answer("avoir"),
        "fr__verb_reflexivity": answer("non_reflexive"),
        "fr__past_participle": answer("marché"),
    }
    assert save(session, plan, data).written == len(keys)


def test_direct_runner_uses_one_call_and_persists_results(session: Session) -> None:
    word = lemma(session, fr="chat")
    state = {
        "lemma_id": word.id,
        "languages": ["en", "fr"],
        "facts": ["countability"],
        "min_confidence": 0.7,
    }
    client = Mock()
    client.generate_chat.return_value = Response(
        "", {"en__countability": answer("countable"), "fr__countability": answer("countable")}, None
    )
    outcomes = run_inline(session, LAPE2_JOB, [state], client, "fake-model")
    assert outcomes[0].status == "written"
    assert client.generate_chat.call_count == 1
    assert stored_values(session, word.id) == {
        "en__countability": "countable",
        "fr__countability": "countable",
    }
    assert get_llm_job("lape2") is LAPE2_JOB
    old_job = get_llm_job("lape")
    assert old_job is not None and old_job.name == "lape"  # old job still intact


def test_disabled_llm_error_propagates(session: Session) -> None:
    word = lemma(session)
    client = Mock()
    client.generate_chat.side_effect = LLMCallsDisabledError("disabled")
    state = {
        "lemma_id": word.id,
        "languages": ["en"],
        "facts": ["countability"],
        "min_confidence": 0.7,
    }
    with pytest.raises(LLMCallsDisabledError):
        run_inline(session, LAPE2_JOB, [state], client, "fake-model")
    assert not stored_values(session, word.id)


def test_saved_manifest_not_current_missing_questions_controls_application(
    session: Session,
) -> None:
    word = lemma(session, fr="chat")
    state = {
        "lemma_id": word.id,
        "languages": ["en", "fr"],
        "facts": ["countability"],
        "min_confidence": 0.7,
    }
    call = prepare(session, state, CTX)
    assert isinstance(call, LLMCall)
    frozen = json.loads(json.dumps(state))
    session.add(
        GrammarFact(
            lemma_id=word.id, language_code="en", fact_type="countability", fact_value="both"
        )
    )
    session.commit()
    outcome = apply(
        session,
        frozen,
        {"en__countability": answer("countable"), "fr__countability": answer("countable")},
        CTX,
    )
    session.commit()
    assert outcome.status == "written"
    assert frozen["report"]["skipped"] == 1
    assert stored_values(session, word.id)["en__countability"] == "both"


def test_limit_applies_after_completed_lemmas(session: Session) -> None:
    completed = lemma(session, "cat")
    missing = lemma(session, "dog")
    session.add(
        GrammarFact(
            lemma_id=completed.id,
            language_code="en",
            fact_type="countability",
            fact_value="countable",
        )
    )
    session.commit()
    args = get_argument_parser().parse_args(
        ["coverage", "--languages", "en", "--facts", "countability", "--limit", "1"]
    )
    assert [plan.lemma_id for plan in select_plans(session, args)] == [missing.id]


@pytest.mark.parametrize("command", ["coverage", "preview", "populate"])
def test_read_only_cli_modes_do_not_construct_clients_or_back_up(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    command: str,
) -> None:
    word = lemma(session)
    monkeypatch.setattr("agents.lape2.cli.create_session", lambda config, readonly=False: session)
    monkeypatch.setattr("agents.lape2.cli.get_data_source_config", Mock())
    forbidden_client = Mock(side_effect=AssertionError("No client in read-only mode"))
    monkeypatch.setattr("agents.lape2.cli.UnifiedLLMClient.from_config", forbidden_client)
    monkeypatch.setattr(
        "storage.backup.create_backup",
        Mock(side_effect=AssertionError("No backup in read-only mode")),
    )
    monkeypatch.setattr(
        "sys.argv",
        [
            "lape2",
            command,
            "--guid",
            str(word.guid),
            "--languages",
            "en",
            "--facts",
            "countability",
            "--dry-run",
        ],
    )
    main()
    output = capsys.readouterr().out
    assert "questions: 1" in output
    if command == "preview":
        assert '"schema"' in output and '"context"' in output
    forbidden_client.assert_not_called()


def test_catalog_uses_registered_language_capabilities() -> None:
    assert CATALOG["countability"].languages() == ("en", "lt", "es", "es-419", "fr", "zh")
    assert CATALOG["grammatical_gender"].allowed_values("fr") == ("masculine", "feminine", "common")
    assert not is_release_grammar_fact_type("zh", "plural_status")


def test_full_noun_bundle_fits_explicit_schema_budget(session: Session) -> None:
    from clients.lib import count_schema_tokens, to_openai_schema

    languages = sorted(
        {
            language
            for spec in CATALOG.values()
            if spec.kind != "concept"
            for language in spec.languages()
        }
    )
    word = lemma(session, **{language: "cat" for language in languages if language != "en"})
    plan = plan_request(session, word, languages)
    query = build_query(plan)
    schema = to_openai_schema(query.schema)
    assert len(plan.questions) >= 29
    assert query.schema.max_schema_tokens == 3072
    assert count_schema_tokens(schema) <= 3072
    assert '"description"' not in json.dumps(schema)
    assert set(schema["properties"]) == {question.key for question in plan.questions}


def test_all_staged_answers_can_be_rolled_back(session: Session) -> None:
    word = lemma(session, "mouse")
    plan = plan_request(session, word, ["en"], facts=["plural"])
    apply_answers(
        session,
        plan,
        {"en__number_type": answer("regular"), "en__plural": answer("mice")},
        min_confidence=0.7,
        model="fake",
    )
    session.rollback()
    assert stored_values(session, word.id) == {}


@pytest.mark.parametrize(
    ("text", "gradability", "comparative", "superlative"),
    [
        ("happy", "synthetic", "happier", "happiest"),
        ("beautiful", "periphrastic", "more beautiful", "most beautiful"),
    ],
)
def test_comparison_checks_use_confirmed_strategy(
    session: Session, text: str, gradability: str, comparative: str, superlative: str
) -> None:
    word = lemma(session, text, "adjective")
    plan = plan_request(session, word, ["en"], facts=["comparative", "superlative"])
    report = save(
        session,
        plan,
        {
            "en__gradability": answer(gradability),
            "en__comparative": answer(comparative),
            "en__superlative": answer(superlative),
        },
    )
    assert report.written == 3 and report.rejected == 0
    assert stored_values(session, word.id) == {
        "en__gradability": gradability,
        "en__comparative_status": "regular",
        "en__superlative_status": "regular",
    }


def test_french_feminine_uses_mechanical_reproducibility(session: Session) -> None:
    word = lemma(session, "active", "adjective", fr="actif")
    plan = plan_request(session, word, ["fr"], facts=["feminine_form"])
    assert save(session, plan, {"fr__feminine_form": answer("active")}).written == 1
    assert stored_values(session, word.id) == {"fr__feminine_form_status": "regular"}


def test_plural_only_keeps_the_citation_plural(session: Session) -> None:
    word = lemma(session, "pants")
    plan = plan_request(session, word, ["en"], facts=["plural"])
    assert (
        save(
            session,
            plan,
            {"en__number_type": answer("plurale_tantum"), "en__plural": answer("pants")},
        ).written
        == 2
    )
    assert stored_values(session, word.id)["en__plural_status"] == "regular"


def test_persistence_failure_rolls_back_the_lemma(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    word = lemma(session, "mouse")
    state = {"lemma_id": word.id, "languages": ["en"], "facts": ["plural"], "min_confidence": 0.7}
    client = Mock()
    client.generate_chat.return_value = Response(
        "", {"en__number_type": answer("regular"), "en__plural": answer("mice")}, None
    )
    original_log = lape2_results.log_entity_operation
    calls = 0

    def failing_log(*args: Any, **kwargs: Any) -> Any:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise ValueError("Simulated storage/logging failure after staging the override")
        return original_log(*args, **kwargs)

    monkeypatch.setattr("agents.lape2.results.log_entity_operation", failing_log)
    assert run_inline(session, LAPE2_JOB, [state], client, "fake")[0].status == "failed"
    assert stored_values(session, word.id) == {}


def test_plural_status_and_concept_facts_survive_release_export_and_reload(
    session: Session, tmp_path: Path
) -> None:
    from storage.backend.jsonl.session import JSONLSession
    from storage.backend.jsonl.storage import JSONLStorage
    from storage.release.lemma import export_to_release

    word = lemma(session)
    plan = plan_request(session, word, ["en"], facts=["plural", "individuation"])
    save(
        session,
        plan,
        {
            "en__number_type": answer("regular"),
            "en__plural": answer("cats"),
            "concept__individuation": answer("individual"),
        },
    )
    export_to_release(session, tmp_path / "lemmas")
    record = json.loads((tmp_path / "lemmas" / "nouns" / "animal" / "en.jsonl").read_text().strip())
    assert {item["fact_type"]: item["fact_value"] for item in record["grammar_facts"]} == {
        "number_type": "regular",
        "plural_status": "regular",
    }
    storage = JSONLStorage(str(tmp_path))
    storage.ensure_initialized()
    reloaded = JSONLSession(storage)
    try:
        database = reloaded._get_sqlite_session()
        imported = database.query(Lemma).filter_by(guid=word.guid).one()
        assert not plan_request(
            database, imported, ["en"], facts=["plural", "individuation"]
        ).questions
    finally:
        reloaded.close()
