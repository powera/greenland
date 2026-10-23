"""Compile a frozen request plan to the common direct/batch LLM call type."""

import json
from collections.abc import Sequence

from agents.lape2.catalog import SPECS
from agents.lape2.planner import RequestPlan
from clients.types import LLMCall, Schema, SchemaProperty
from util.prompt_loader import get_context, get_prompt


def build_context(pos_type: str, languages: Sequence[str]) -> str:
    """Describe every applicable fact, independent of completion and fact filters."""
    targets = sorted(set(languages))
    sections = [
        get_context("grammar", "lape2"),
        f"Part of speech: {pos_type}. Requested languages: {', '.join(targets)}.",
        "Fact reference. Question keys use language__fact_type; concept__fact_type "
        "identifies a sense-level fact. Answer only the requested questions. "
        "Follow these value sets even though the response schema uses strings.",
    ]
    if pos_type == "noun":
        sections.append(
            "Countability, number paradigm, individuation, and concreteness are different "
            "dimensions. A mass noun is not automatically singular-only. "
            "Singular-only senses have no plural. A plural-only noun keeps its plural text."
        )
    if pos_type in ("adjective", "adverb"):
        sections.append("Non-gradable senses have no comparative or superlative.")
    for spec in SPECS:
        applicable = [language for language in targets if spec.applies(pos_type, language)]
        concept = spec.kind == "concept" and spec.applies(pos_type, None)
        if not applicable and not concept:
            continue
        scope = "concept" if concept else ", ".join(applicable)
        lines = [f"{spec.fact_type} [{scope}]: {spec.instruction}"]
        if spec.values:
            lines.append("Allowed values: " + " | ".join(spec.values) + ".")
        elif not concept:
            value_languages: dict[tuple[str, ...], list[str]] = {}
            for language in applicable:
                values = spec.allowed_values(language)
                if values:
                    value_languages.setdefault(values, []).append(language)
            for values, group in value_languages.items():
                lines.append(f"Allowed values ({', '.join(group)}): {' | '.join(values)}.")
        sections.append("\n".join(lines))
    return "\n\n".join(sections)


def render_json(value: object) -> str:
    """Serialize deterministically with line breaks but no indentation."""
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=0)


def build_query(plan: RequestPlan) -> LLMCall:
    if not plan.questions:
        raise ValueError("No unanswered questions in this request plan")
    properties: dict[str, SchemaProperty] = {}
    question_keys: list[str] = []
    for question in sorted(plan.questions, key=lambda item: item.key):
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
        **{field: value for field, value in plan.source.items() if field != "guid"},
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
        source=render_json(prompt_source),
        known=render_json(plan.known),
        questions=render_json(question_keys),
    )
    return LLMCall(
        prompt,
        Schema("Lape2Grammar", "Missing grammar for one sense", properties, max_schema_tokens=3072),
        build_context(plan.source["pos_type"], tuple(plan.source["translations"])),
        max_tokens=1024 + 180 * len(plan.questions),
    )
