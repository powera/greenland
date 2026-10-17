"""Compile a frozen request plan to the common direct/batch LLM call type."""

import json

from agents.lape2.planner import RequestPlan
from clients.types import LLMCall, Schema, SchemaProperty
from util.prompt_loader import get_context, get_prompt


def build_query(plan: RequestPlan) -> LLMCall:
    if not plan.questions:
        raise ValueError("No unanswered questions in this request plan")
    properties: dict[str, SchemaProperty] = {}
    instructions: list[dict[str, object]] = []
    for question in plan.questions:
        # Instructions already live in the prompt. Repeating them on every
        # schema object and value field doubled the input for large bundles.
        properties[question.key] = SchemaProperty(
            "object",
            object_schema=Schema(
                "Answer",
                "",
                {
                    "value": SchemaProperty("string", enum=list(question.values) or None),
                    "confidence": SchemaProperty("number", minimum=0, maximum=1),
                    "explanation": SchemaProperty("string"),
                },
            ),
        )
        instructions.append(
            {
                "key": question.key,
                "instruction": question.instruction,
            }
        )
    prompt = get_prompt("grammar", "lape2").format(
        source=json.dumps(plan.source, ensure_ascii=False, indent=2),
        known=json.dumps(plan.known, ensure_ascii=False, indent=2),
        questions=json.dumps(instructions, ensure_ascii=False, indent=2),
    )
    return LLMCall(
        prompt,
        Schema("Lape2Grammar", "Missing grammar for one sense", properties, max_schema_tokens=3072),
        get_context("grammar", "lape2"),
        max_tokens=1024 + 180 * len(plan.questions),
    )
