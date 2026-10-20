"""Compile a frozen request plan to the common direct/batch LLM call type."""

import json

from agents.lape2.catalog import SPECS
from agents.lape2.planner import RequestPlan
from clients.types import LLMCall, Schema, SchemaProperty
from util.prompt_loader import get_context, get_prompt


def build_context() -> str:
    """Keep shared fact definitions and allowed values in reusable context."""
    definitions: list[dict[str, object]] = []
    for spec in SPECS:
        definition: dict[str, object] = {
            "fact_type": spec.fact_type,
            "instruction": spec.instruction,
        }
        if spec.values:
            definition["allowed_values"] = list(spec.values)
        elif spec.kind != "concept":
            value_languages: dict[tuple[str, ...], list[str]] = {}
            for language in spec.languages():
                values = spec.allowed_values(language)
                if values:
                    value_languages.setdefault(values, []).append(language)
            if value_languages:
                definition["allowed_values_by_language"] = [
                    {"languages": languages, "values": list(values)}
                    for values, languages in value_languages.items()
                ]
        definitions.append(definition)
    return (
        get_context("grammar", "lape2")
        + "\n\nFact definitions and allowed values. Question keys use language__fact_type; "
        "concept__fact_type identifies a sense-level fact. Follow these value sets "
        "even though the response schema uses strings.\n"
        + json.dumps(definitions, ensure_ascii=False, indent=2)
    )


def build_query(plan: RequestPlan) -> LLMCall:
    if not plan.questions:
        raise ValueError("No unanswered questions in this request plan")
    properties: dict[str, SchemaProperty] = {}
    question_keys: list[str] = []
    for question in plan.questions:
        # Definitions and value sets live once in shared context.
        properties[question.key] = SchemaProperty(
            "object",
            properties={
                "value": SchemaProperty("string"),
                "confidence": SchemaProperty("number"),
            },
        )
        question_keys.append(question.key)
    # Keep the frozen source intact for stale-result checks, while omitting
    # absent translation metadata from the model's input.
    prompt_source = {
        **plan.source,
        **{
            field: {
                language: value
                for language, value in plan.source[field].items()
                if value is not None
            }
            for field in ("translation_definitions", "translation_disambiguations")
        },
    }
    prompt = get_prompt("grammar", "lape2").format(
        source=json.dumps(prompt_source, ensure_ascii=False, indent=2),
        known=json.dumps(plan.known, ensure_ascii=False, indent=2),
        questions=json.dumps(question_keys, ensure_ascii=False, indent=2),
    )
    return LLMCall(
        prompt,
        Schema("Lape2Grammar", "Missing grammar for one sense", properties, max_schema_tokens=3072),
        build_context(),
        max_tokens=1024 + 180 * len(plan.questions),
    )
