"""Read-only request planning and serializable manifests for delayed answers."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Sequence

from sqlalchemy.orm import Session

from agents.lape2.catalog import CATALOG, SPECS, Kind
from storage.models.grammar_fact import GrammarFact
from storage.models.lemma_fact import LemmaFact
from storage.models.schema import Lemma
from storage.models.uncertain_llm_result import UncertainLLMResult
from storage.translation_helpers import (
    get_all_definitions,
    get_all_translation_disambiguations,
    get_all_translations,
    get_translation,
)

PLAN_VERSION = 1


def question_key(fact_type: str, language_code: str | None) -> str:
    return f"{language_code or 'concept'}__{fact_type}"


@dataclass(frozen=True)
class Question:
    fact_type: str
    language_code: str | None
    kind: Kind
    instruction: str
    values: tuple[str, ...]

    @property
    def key(self) -> str:
        return question_key(self.fact_type, self.language_code)

    @property
    def completion_type(self) -> str:
        return f"{self.fact_type}_status" if self.kind == "override" else self.fact_type


@dataclass(frozen=True)
class RequestPlan:
    lemma_id: int
    source: dict[str, Any]
    known: dict[str, str]
    questions: tuple[Question, ...]
    uncertain: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {"version": PLAN_VERSION, **asdict(self)}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RequestPlan:
        if data.get("version") != PLAN_VERSION:
            raise ValueError("Unsupported Lape2 request plan version")
        return cls(
            lemma_id=data["lemma_id"],
            source=data["source"],
            known=data["known"],
            questions=tuple(
                Question(**{**item, "values": tuple(item["values"])}) for item in data["questions"]
            ),
            uncertain=tuple(data["uncertain"]),
        )


def source_snapshot(session: Session, lemma: Lemma, languages: Sequence[str]) -> dict[str, Any]:
    translations = get_all_translations(session, lemma)
    if "en" in languages:
        translations["en"] = get_translation(session, lemma, "en")
    definitions = get_all_definitions(session, lemma)
    disambiguations = get_all_translation_disambiguations(session, lemma)
    return {
        "guid": lemma.guid,
        "word": lemma.lemma_text,
        "definition": lemma.definition_text,
        "disambiguation": lemma.disambiguation,
        "pos_type": lemma.pos_type,
        "pos_subtype": lemma.pos_subtype,
        "translations": {
            language: translations.get(language) for language in sorted(set(languages))
        },
        "translation_definitions": {
            language: definitions.get(language) for language in sorted(set(languages))
        },
        "translation_disambiguations": {
            language: disambiguations.get(language) for language in sorted(set(languages))
        },
    }


def stored_values(session: Session, lemma_id: int) -> dict[str, str]:
    grammar = session.query(GrammarFact).filter(GrammarFact.lemma_id == lemma_id).all()
    concepts = session.query(LemmaFact).filter(LemmaFact.lemma_id == lemma_id).all()
    return {
        **{
            question_key(row.fact_type, row.language_code): row.fact_value
            for row in grammar
            if row.fact_value and row.fact_value.strip()
        },
        **{
            question_key(row.fact_type, None): row.fact_value
            for row in concepts
            if row.fact_value and row.fact_value.strip()
        },
    }


def plan_request(
    session: Session,
    lemma: Lemma,
    languages: Sequence[str],
    *,
    facts: Sequence[str] | None = None,
    retry_uncertain: bool = False,
) -> RequestPlan:
    """Plan every applicable missing question; never load a client or write data.

    An override is complete only with its status and, when needed, its value.
    Existing overrides without a status are checked without being overwritten.
    """
    if facts is not None and set(facts) - CATALOG.keys():
        raise ValueError(f"Unknown facts: {sorted(set(facts) - CATALOG.keys())}")
    selected = set(facts) if facts is not None else set(CATALOG)
    # A filtered form check still needs its classifications to distinguish
    # absent slots from irregular forms. Ask for missing prerequisites together.
    if "plural" in selected:
        selected.add("number_type")
    if selected & {"comparative", "superlative"}:
        selected.add("gradability")
    source = source_snapshot(session, lemma, languages)
    existing = stored_values(session, lemma.id)
    uncertain_questions = {
        (row.topic, row.language_code)
        for row in session.query(UncertainLLMResult).filter_by(lemma_id=lemma.id).all()
    }
    known = {
        identifier: value
        for identifier, value in existing.items()
        if identifier.split("__", 1)[0] in {*languages, "concept"}
    }
    questions: list[Question] = []
    uncertain: list[str] = []
    for spec in SPECS:
        if spec.fact_type not in selected:
            continue
        targets: list[str | None] = [None]
        if spec.kind != "concept":
            targets = [language for language in sorted(set(languages))]
        for language_code in targets:
            if not spec.applies(lemma.pos_type, language_code):
                continue
            if (
                language_code is not None
                and not (source["translations"].get(language_code) or "").strip()
            ):
                continue
            completion_key = question_key(spec.completion_type, language_code)
            completion = existing.get(completion_key)
            if completion and (
                spec.kind != "override"
                or (
                    completion in ("regular", "not_applicable")
                    or (
                        completion == "override"
                        and question_key(spec.fact_type, language_code) in existing
                    )
                )
            ):
                continue
            if (spec.completion_type, language_code) in uncertain_questions:
                uncertain.append(question_key(spec.fact_type, language_code))
                if not retry_uncertain:
                    continue
            questions.append(
                Question(
                    spec.fact_type,
                    language_code,
                    spec.kind,
                    spec.instruction,
                    spec.allowed_values(language_code),
                )
            )
    return RequestPlan(lemma.id, source, known, tuple(questions), tuple(uncertain))
