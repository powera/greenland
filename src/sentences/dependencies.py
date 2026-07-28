#!/usr/bin/python3

"""Phase-4 Universal Dependencies pass over an already-decomposed sentence.

Dependency heads point at tokens by number, and the numbering that matters is
the one the decomposition pass produced — not our own tokenization, which the
decomposition prompt is explicitly free to diverge from (merged multiword
entries, CJK languages with no whitespace tokenization at all). So UD cannot be
folded into the decomposition call: it is a separate call that takes the stored
words as an explicit numbered list and returns a relation + head for each.

Mirrors :mod:`sentences.decomposition`: prompt builders, a schema builder, and
a query helper with the same ``_usage`` token accounting.
"""

import json
import logging
from typing import Any, Dict, List, Optional, Set

from clients.unified_client import UnifiedLLMClient
from langtools.ud_relations import ROOT_HEAD_POSITION, ROOT_RELATION, sorted_ud_relations
from storage.translation_helpers import LANGUAGE_NAMES

import util.prompt_loader

logger = logging.getLogger(__name__)

_DEPENDENCIES_PROMPT_PATH = "dependencies"


def build_dependency_context() -> str:
    """Return the context block for the Phase-4 dependency pass."""
    return util.prompt_loader.get_context("sentence_decomposition", _DEPENDENCIES_PROMPT_PATH)


def _format_numbered_tokens(words: List[Dict[str, Any]]) -> str:
    """Render the decomposed words as the numbered list heads refer to.

    Positions come from each word's own ``position`` when present, falling back
    to list order, so the numbering matches what was stored.
    """
    lines: List[str] = []
    for index, word in enumerate(words):
        position = word.get("position")
        if not isinstance(position, int):
            position = index
        surface_form = str(word.get("surface_form") or word.get("target_language_text") or "")
        part_of_speech = str(word.get("part_of_speech") or "").strip()
        line = f"  {position}  {surface_form}"
        if part_of_speech:
            line += f"  ({part_of_speech})"
        lines.append(line)
    return "\n".join(lines)


def build_dependency_prompt(
    *,
    language_code: str,
    sentence_text: str,
    words: List[Dict[str, Any]],
) -> str:
    """Build the Phase-4 prompt for one already-decomposed language.

    ``words`` are decomposition word dicts (``position``, ``surface_form``,
    ``part_of_speech``, ...). They are rendered as an explicit numbered list;
    without that numbering a head index is meaningless.
    """
    return util.prompt_loader.get_prompt(
        "sentence_decomposition", _DEPENDENCIES_PROMPT_PATH
    ).format(
        language_code=language_code,
        language_name=LANGUAGE_NAMES.get(language_code, language_code),
        sentence_text=sentence_text,
        numbered_tokens=_format_numbered_tokens(words) or "  (none provided)",
        word_count=len(words),
    )


def build_dependency_schema(*, word_count: int) -> Dict[str, Any]:
    """Schema for the Phase-4 response: one relation + head per token.

    ``ud_head_position`` is bounded to ``[-1, word_count - 1]`` so a provider
    that enforces the schema rejects out-of-range heads structurally, and
    ``ud_relation`` is a closed enum of the core UD labels.
    """
    return {
        "type": "object",
        "properties": {
            "words": {
                "type": "array",
                "minItems": word_count,
                "maxItems": word_count,
                "items": {
                    "type": "object",
                    "properties": {
                        "position": {
                            "type": "integer",
                            "minimum": 0,
                            "maximum": max(word_count - 1, 0),
                        },
                        "ud_relation": {
                            "type": "string",
                            "description": "Core Universal Dependencies relation label",
                            "enum": sorted_ud_relations(),
                        },
                        "ud_head_position": {
                            "type": "integer",
                            "description": "Position of the head token; -1 for the sentence root",
                            "minimum": ROOT_HEAD_POSITION,
                            "maximum": max(word_count - 1, 0),
                        },
                    },
                    "required": ["position", "ud_relation", "ud_head_position"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["words"],
        "additionalProperties": False,
    }


def validate_dependency_tree(words: List[Dict[str, Any]]) -> List[str]:
    """Return human-readable structural problems with a dependency parse.

    Structural checks only — exactly one root, every position covered exactly
    once, heads in range, no self-loops, no cycles. Whether a given relation is
    linguistically apt (a ``det`` on a verb, say) is a judgment call the model
    makes better than a rule table would, so it is deliberately not checked.

    An empty list means the parse is usable.
    """
    problems: List[str] = []
    word_count = len(words)
    if word_count == 0:
        return ["No words returned"]

    heads_by_position: Dict[int, int] = {}
    seen_positions: Set[int] = set()
    root_positions: List[int] = []

    for entry in words:
        raw_position = entry.get("position")
        if not isinstance(raw_position, int) or isinstance(raw_position, bool):
            problems.append(f"Non-integer position: {raw_position!r}")
            continue
        if raw_position < 0 or raw_position >= word_count:
            problems.append(f"Position {raw_position} out of range 0..{word_count - 1}")
            continue
        if raw_position in seen_positions:
            problems.append(f"Duplicate position {raw_position}")
            continue
        seen_positions.add(raw_position)

        raw_head = entry.get("ud_head_position")
        if not isinstance(raw_head, int) or isinstance(raw_head, bool):
            problems.append(f"Non-integer head at position {raw_position}: {raw_head!r}")
            continue
        if raw_head == ROOT_HEAD_POSITION:
            root_positions.append(raw_position)
            if entry.get("ud_relation") != ROOT_RELATION:
                problems.append(
                    f"Position {raw_position} has head -1 but relation "
                    f"{entry.get('ud_relation')!r}, expected {ROOT_RELATION!r}"
                )
            continue
        if entry.get("ud_relation") == ROOT_RELATION:
            problems.append(
                f"Position {raw_position} has relation {ROOT_RELATION!r} but head {raw_head}, "
                f"expected {ROOT_HEAD_POSITION}"
            )
        if raw_head < 0 or raw_head >= word_count:
            problems.append(
                f"Head {raw_head} at position {raw_position} out of range 0..{word_count - 1}"
            )
            continue
        if raw_head == raw_position:
            problems.append(f"Position {raw_position} is its own head")
            continue
        heads_by_position[raw_position] = raw_head

    missing_positions = sorted(set(range(word_count)) - seen_positions)
    if missing_positions:
        problems.append(
            "Missing positions: " + ", ".join(str(position) for position in missing_positions)
        )

    if not root_positions:
        problems.append("No root: exactly one word must have head -1")
    elif len(root_positions) > 1:
        problems.append(
            "Multiple roots at positions " + ", ".join(str(p) for p in sorted(root_positions))
        )

    problems.extend(_find_cycles(heads_by_position))
    return problems


def _find_cycles(heads_by_position: Dict[int, int]) -> List[str]:
    """Report each cycle reachable by walking heads upward."""
    problems: List[str] = []
    reported: Set[frozenset] = set()

    for start in sorted(heads_by_position):
        seen: List[int] = []
        seen_set: Set[int] = set()
        current = start
        while current in heads_by_position:
            if current in seen_set:
                cycle = seen[seen.index(current) :]
                key = frozenset(cycle)
                if key not in reported:
                    reported.add(key)
                    problems.append(
                        "Cycle in head graph: " + " -> ".join(str(p) for p in cycle + [current])
                    )
                break
            seen.append(current)
            seen_set.add(current)
            current = heads_by_position[current]

    return problems


def query_sentence_dependencies(
    *,
    prompt: str,
    client: UnifiedLLMClient,
    model: str,
    json_schema: Dict[str, Any],
    context: Optional[str] = None,
) -> Dict[str, Any]:
    """Execute a Phase-4 dependency query and return structured JSON."""
    try:
        response = client.generate_chat(
            prompt=prompt,
            model=model,
            json_schema=json_schema,
            context=context,
        )
    except Exception as error:
        logger.error("Error querying sentence dependencies: %s", error)
        return {"success": False, "error": str(error)}

    result: Any = response.structured_data or response.response_text
    if not result:
        return {"success": False, "error": "Empty response from LLM"}

    if isinstance(result, str):
        try:
            result = json.loads(result)
        except json.JSONDecodeError as error:
            return {"success": False, "error": f"Invalid JSON response: {error}"}

    if not isinstance(result, dict):
        return {"success": False, "error": "Structured response is not an object"}

    merged: Dict[str, Any] = {"success": True}
    merged.update(result)
    if response.usage is not None:
        merged["_usage"] = {
            "tokens_in": getattr(response.usage, "tokens_in", None),
            "tokens_out": getattr(response.usage, "tokens_out", None),
            "total_tokens": getattr(response.usage, "total_tokens", None),
        }
    return merged
