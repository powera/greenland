#!/usr/bin/python3
"""
Schema conversion utilities for various LLM clients.

This module provides a unified Schema dataclass that can be
converted to the appropriate format for different LLM clients:
- OpenAI
- Anthropic
- Google Gemini
- Ollama
"""

import copy
import json
import logging
import os
from typing import Any, Dict, List, Optional

from clients.types import Schema, SchemaProperty

logger = logging.getLogger(__name__)

# A single chat message in the provider-neutral "dialect": a role of "user" or
# "assistant" and string content. Clients translate these into their own request
# shapes (OpenAI Responses input items, Anthropic messages, Gemini contents).
ChatMessage = Dict[str, str]

# Filler used when a synthetic assistant turn must be inserted to keep roles
# alternating for providers that require it (Anthropic, Gemini).
ALTERNATION_ACK: str = "Understood."

# Maximum size of a serialized JSON schema, in tokens. A schema is sent with
# every request that uses it, so a large one is a recurring cost on every call.
# The usual cause is embedding a full enum: listing every GrammaticalForm value
# (1238 of them, ~7100 tokens) to ask about a single English word cost more than
# the instructions and the query combined. If a schema trips this, narrow the
# enum to the values that are actually possible, or describe the format in the
# prompt and drop the enum.
MAX_SCHEMA_TOKENS = 2048

# Default output-token limit when the caller asks for nothing in particular.
# Each backend passes its own historical value as ``backend_default`` so that
# omitting ``max_tokens`` reproduces exactly what that backend did before.
DEFAULT_BRIEF_TOKENS: int = 512

# Per-model-family ceiling on output tokens. This is not the model's true API
# maximum; it is the largest single response this project is willing to pay for.
# Prefix-keyed and deliberately coarse so a new point release does not need an
# entry -- an unmatched model falls back to DEFAULT_OUTPUT_CEILING.
MODEL_OUTPUT_CEILINGS: Dict[str, int] = {
    "gpt-5": 32768,
    "gpt-4o": 16384,
    "claude": 16384,
    "gemini": 8192,
}
DEFAULT_OUTPUT_CEILING: int = 4096

# Headroom applied to a caller's estimate of its own response size, by
# limit_from_estimate(). An estimate is a guess, and the cost of guessing low is
# a truncated response that fails the whole call; the cost of guessing high is
# nothing, since output tokens are billed as generated, not as reserved. The
# additive term covers fixed per-response overhead (envelope punctuation, a
# trailing object) that does not scale with the estimate, and the floor keeps
# very small requests from being sized absurdly tight.
ESTIMATE_SAFETY_FACTOR: float = 1.35
ESTIMATE_SAFETY_OVERHEAD_TOKENS: int = 100
MIN_ESTIMATED_LIMIT_TOKENS: int = 512


class SchemaTooLargeError(ValueError):
    """Raised when a serialized schema exceeds MAX_SCHEMA_TOKENS."""


class LLMCallsDisabledError(RuntimeError):
    """Raised when GREENLAND_DISABLE_LLM blocks an outbound LLM request."""


class TruncatedResponseError(RuntimeError):
    """Raised when a backend stopped generating because it hit the token limit.

    Distinct from a malformed response: the model was answering correctly and
    ran out of room. Callers that can resize and retry should catch this
    specifically; callers that cannot should let it propagate rather than
    persisting the partial answer.
    """


def limit_from_estimate(estimated_tokens: int) -> int:
    """Turn a caller's estimate of its response size into a token limit.

    The single place the estimate-to-limit policy lives, so it can be tuned
    globally rather than per call site. Callers estimate how large their own
    response should be (which they know: word counts, item counts) and this
    adds the safety margin.

    Args:
        estimated_tokens: The caller's estimate of its response size, in tokens.

    Returns:
        A token limit at least MIN_ESTIMATED_LIMIT_TOKENS. Still subject to the
        model ceiling, which resolve_output_tokens() applies.
    """
    if estimated_tokens < 0:
        estimated_tokens = 0
    padded = int(estimated_tokens * ESTIMATE_SAFETY_FACTOR) + ESTIMATE_SAFETY_OVERHEAD_TOKENS
    return max(padded, MIN_ESTIMATED_LIMIT_TOKENS)


def ceiling_for_model(model: str) -> int:
    """Largest output-token limit allowed for a model, by name prefix."""
    for prefix, ceiling in MODEL_OUTPUT_CEILINGS.items():
        if model.startswith(prefix):
            return ceiling
    return DEFAULT_OUTPUT_CEILING


def resolve_output_tokens(
    model: str,
    *,
    brief: bool,
    requested: Optional[int],
    backend_default: int,
    brief_default: int = DEFAULT_BRIEF_TOKENS,
) -> int:
    """Decide the output-token limit for one request.

    Shared by every backend so the policy is one testable function rather than a
    hardcoded literal per client.

    Args:
        model: Model name, used to pick the ceiling.
        brief: The caller's coarse "keep it short" flag.
        requested: An explicit limit, normally from limit_from_estimate(). When
            None, the result is exactly what this backend used before max_tokens
            existed, so callers that do not pass one are unaffected.
        backend_default: This backend's historical non-brief default.
        brief_default: This backend's historical brief default.

    Returns:
        The token limit to send, clamped to the model ceiling.
    """
    if requested is None:
        return brief_default if brief else backend_default

    ceiling = ceiling_for_model(model)
    if requested > ceiling:
        logger.warning(
            "Requested output limit %d exceeds the %d-token ceiling for model %s; "
            "clamping. A response that needs more than this should be split by the "
            "caller rather than truncated.",
            requested,
            ceiling,
            model,
        )
        return ceiling
    return requested


def assert_llm_calls_enabled(backend: str) -> None:
    """Refuse to send an outbound LLM request when GREENLAND_DISABLE_LLM=1 .

    This is an operator-facing kill switch: it lets a bulk agent run against the
    database with a hard guarantee that nothing reaches a paid backend, so code
    paths that generate data mechanically (e.g. langtools.en rule-based forms)
    still run while any LLM fallback fails loudly instead of silently spending
    money.

    Call this at the point of the outbound HTTP request, not in a wrapper.
    Each backend client defines its own generate_chat/warm_model, and callers
    hold client objects directly, so a guard on any higher layer can be routed
    around -- only the request boundary catches every caller.

    Args:
        backend: Backend name, for the error message (e.g. "openai").
    """
    if os.environ.get("GREENLAND_DISABLE_LLM") != "1":
        return
    raise LLMCallsDisabledError(
        f"Outbound {backend} LLM request blocked: GREENLAND_DISABLE_LLM=1 is set. "
        f"Unset it to allow live LLM calls, or use a code path that does not "
        f"require an LLM."
    )


def count_schema_tokens(schema_dict: Dict[str, Any]) -> int:
    """Count tokens in a serialized schema, for size enforcement."""
    import tiktoken

    encoder = tiktoken.get_encoding("cl100k_base")
    return len(encoder.encode(json.dumps(schema_dict)))


def _check_schema_size(schema_dict: Dict[str, Any], schema_name: str, provider: str) -> None:
    """Raise if the serialized schema is too large to send on every request.

    Args:
        schema_dict: The provider-format schema about to be returned
        schema_name: Schema.name, for the error message
        provider: Provider name, for the error message

    Raises:
        SchemaTooLargeError: If the schema exceeds MAX_SCHEMA_TOKENS
    """
    token_count = count_schema_tokens(schema_dict)
    if token_count > MAX_SCHEMA_TOKENS:
        largest = _largest_enums(schema_dict)
        detail = ""
        if largest:
            detail = " Largest enums: " + ", ".join(
                f"{path} ({count} values)" for path, count in largest
            )
        raise SchemaTooLargeError(
            f"{provider} schema {schema_name!r} is {token_count} tokens, over the "
            f"{MAX_SCHEMA_TOKENS} limit. A schema is sent on every request that uses "
            f"it, so this is a per-call cost.{detail}"
        )


def _largest_enums(schema_dict: Any, path: str = "", found: Any = None) -> List[Any]:
    """Find the largest enum lists in a schema, to point at the likely cause."""
    if found is None:
        found = []
    if isinstance(schema_dict, dict):
        for key, value in schema_dict.items():
            if key == "enum" and isinstance(value, list):
                found.append((path or "<root>", len(value)))
            elif isinstance(value, (dict, list)):
                _largest_enums(value, f"{path}.{key}" if path else key, found)
    elif isinstance(schema_dict, list):
        for index, item in enumerate(schema_dict):
            _largest_enums(item, f"{path}[{index}]", found)
    return sorted(found, key=lambda pair: pair[1], reverse=True)[:3]


def normalize_alternating_messages(
    messages: List[ChatMessage], ack: str = ALTERNATION_ACK
) -> List[ChatMessage]:
    """Insert synthetic assistant turns so message roles strictly alternate.

    Some providers (Anthropic, Gemini) reject two consecutive messages with the
    same role. Callers may pass several consecutive ``user`` messages (e.g. one
    per source); this inserts a short assistant acknowledgement between any two
    same-role messages so the resulting list alternates user/assistant.

    Args:
        messages: Provider-neutral messages, each ``{"role", "content"}``.
        ack: Content used for inserted assistant acknowledgements.

    Returns:
        A new list with assistant acks inserted where needed. The input is not
        mutated. An empty input yields an empty list.
    """
    normalized: List[ChatMessage] = []
    for message in messages:
        if normalized and normalized[-1]["role"] == message["role"]:
            filler_role = "assistant" if message["role"] == "user" else "user"
            normalized.append({"role": filler_role, "content": ack})
        normalized.append({"role": message["role"], "content": message["content"]})
    return normalized


def _ensure_additional_properties(schema_dict: Dict[str, Any]) -> None:
    """
    Recursively ensure all object types have additionalProperties set to False
    and all properties are listed in the required array.
    This is required by OpenAI's strict schema validation.

    Args:
        schema_dict: Schema dictionary to modify in-place
    """
    if not isinstance(schema_dict, dict):
        return

    # If this is an object type, ensure it has additionalProperties and required
    if schema_dict.get("type") == "object":
        # OpenAI strict mode requires additionalProperties to be false (not a schema)
        # If it's currently set to a schema like {"type": "string"}, convert to false
        if "additionalProperties" in schema_dict:
            if isinstance(schema_dict["additionalProperties"], dict):
                # This is trying to use dynamic properties (map/dictionary)
                # OpenAI strict mode doesn't support this - convert to false
                # The caller should have defined explicit properties instead
                schema_dict["additionalProperties"] = False
        else:
            schema_dict["additionalProperties"] = False

        # OpenAI requires all properties to be in the required array
        if "properties" in schema_dict and len(schema_dict["properties"]) > 0:
            all_prop_keys = list(schema_dict["properties"].keys())
            if "required" not in schema_dict:
                schema_dict["required"] = all_prop_keys
            else:
                # Ensure the required array includes ONLY the properties that exist
                # (no extras, no missing)
                schema_dict["required"] = all_prop_keys

            # Recurse into properties
            for prop_value in schema_dict["properties"].values():
                _ensure_additional_properties(prop_value)

    # If this has items (array), recurse into items
    if "items" in schema_dict:
        _ensure_additional_properties(schema_dict["items"])

    # Recurse into all nested dictionaries
    for key, value in schema_dict.items():
        if isinstance(value, dict) and key not in ["additionalProperties", "required"]:
            _ensure_additional_properties(value)


def to_openai_schema(schema: Schema) -> Dict[str, Any]:
    """
    Convert Schema to OpenAI's schema format.

    OpenAI doesn't support the "optional" concept directly in its schema.
    Instead, it uses the "required" field at the schema level listing all required properties.
    """
    result: Dict[str, Any] = {
        "type": "object",
        "properties": {},
        "required": schema.all_properties(),
        "additionalProperties": False,
    }

    for name, prop in schema.properties.items():
        property_schema: Dict[str, Any] = {
            "type": prop.type,
        }

        if prop.description:
            property_schema["description"] = prop.description

        if prop.enum:
            property_schema["enum"] = prop.enum

        # Add minimum/maximum constraints for numeric types
        if prop.type in ["integer", "number"]:
            if prop.minimum is not None:
                property_schema["minimum"] = prop.minimum
            if prop.maximum is not None:
                property_schema["maximum"] = prop.maximum

        # Handle nested objects
        if prop.type == "object" and prop.object_schema:
            # Convert nested schema
            nested_schema = to_openai_schema(prop.object_schema)
            # Copy properties and required fields
            property_schema["properties"] = nested_schema["properties"]
            if "required" in nested_schema and nested_schema["required"]:
                property_schema["required"] = nested_schema["required"]
            property_schema["additionalProperties"] = nested_schema.get(
                "additionalProperties", False
            )
        elif prop.type == "object" and prop.properties:
            # Handle inline object definition
            property_schema["properties"] = {}
            required_props = []

            for sub_name, sub_prop in prop.properties.items():
                sub_schema: Dict[str, Any] = {"type": sub_prop.type}

                if sub_prop.description:
                    sub_schema["description"] = sub_prop.description

                if sub_prop.enum:
                    sub_schema["enum"] = sub_prop.enum

                if sub_prop.type in ["integer", "number"]:
                    if sub_prop.minimum is not None:
                        sub_schema["minimum"] = sub_prop.minimum
                    if sub_prop.maximum is not None:
                        sub_schema["maximum"] = sub_prop.maximum

                if sub_prop.type == "array" and sub_prop.items:
                    sub_schema["items"] = sub_prop.items

                if sub_prop.required:
                    required_props.append(sub_name)

                property_schema["properties"][sub_name] = sub_schema

            if required_props:
                property_schema["required"] = required_props

            property_schema["additionalProperties"] = False

        # Handle array items
        elif prop.type == "array" and prop.array_items_schema:
            # Handle array of objects with a full schema
            property_schema["items"] = to_openai_schema(prop.array_items_schema)
        elif prop.type == "array" and prop.items:
            # Handle simple array items or array of objects with inline schema
            if isinstance(prop.items, dict) and prop.items.get("type") == "object":
                # Ensure additionalProperties is set for object schemas
                items_copy = copy.deepcopy(prop.items)
                if "additionalProperties" not in items_copy:
                    items_copy["additionalProperties"] = False
                # OpenAI requires all properties to be in the required array
                if "properties" in items_copy and "required" not in items_copy:
                    items_copy["required"] = list(items_copy["properties"].keys())
                elif "properties" in items_copy and "required" in items_copy:
                    # Ensure all properties are in required array for OpenAI
                    items_copy["required"] = list(items_copy["properties"].keys())
                property_schema["items"] = items_copy
            else:
                property_schema["items"] = prop.items

        result["properties"][name] = property_schema

    _recursive_clean_for_openai(result)
    # Ensure all nested objects have additionalProperties set (required by OpenAI)
    _ensure_additional_properties(result)
    _check_schema_size(result, schema.name, "OpenAI")
    return result


def to_anthropic_schema(schema: Schema) -> Dict[str, Any]:
    """
    Convert Schema to Anthropic's schema format.

    Anthropic's schema is similar to JSON Schema with a few differences.
    """
    result: Dict[str, Any] = {
        "type": "object",
        "properties": {},
        "required": schema.required_properties(),
    }

    for name, prop in schema.properties.items():
        property_schema: Dict[str, Any] = {
            "type": prop.type,
        }

        if prop.description:
            property_schema["description"] = prop.description

        if prop.enum:
            property_schema["enum"] = prop.enum

        # Add minimum/maximum constraints for numeric types
        if prop.type in ["integer", "number"]:
            if prop.minimum is not None:
                property_schema["minimum"] = prop.minimum
            if prop.maximum is not None:
                property_schema["maximum"] = prop.maximum

        # Handle nested objects
        if prop.type == "object" and prop.object_schema:
            # Convert nested schema
            nested_schema = to_anthropic_schema(prop.object_schema)
            # Copy properties and required fields
            property_schema["properties"] = nested_schema["properties"]
            if "required" in nested_schema and nested_schema["required"]:
                property_schema["required"] = nested_schema["required"]
            property_schema["additionalProperties"] = nested_schema.get(
                "additionalProperties", False
            )
        elif prop.type == "object" and prop.properties:
            # Handle inline object definition
            property_schema["properties"] = {}
            required_props = []

            for sub_name, sub_prop in prop.properties.items():
                sub_schema: Dict[str, Any] = {"type": sub_prop.type}

                if sub_prop.description:
                    sub_schema["description"] = sub_prop.description

                if sub_prop.enum:
                    sub_schema["enum"] = sub_prop.enum

                if sub_prop.type in ["integer", "number"]:
                    if sub_prop.minimum is not None:
                        sub_schema["minimum"] = sub_prop.minimum
                    if sub_prop.maximum is not None:
                        sub_schema["maximum"] = sub_prop.maximum

                if sub_prop.type == "array" and sub_prop.items:
                    sub_schema["items"] = sub_prop.items

                if sub_prop.required:
                    required_props.append(sub_name)

                property_schema["properties"][sub_name] = sub_schema

            if required_props:
                property_schema["required"] = required_props

            property_schema["additionalProperties"] = False

        # Handle array items
        elif prop.type == "array" and prop.array_items_schema:
            # Handle array of objects with a full schema
            property_schema["items"] = to_anthropic_schema(prop.array_items_schema)
        elif prop.type == "array" and prop.items:
            # Handle simple array items or array of objects with inline schema
            property_schema["items"] = prop.items

        # Add default value if specified
        if prop.default is not None:
            property_schema["default"] = prop.default

        result["properties"][name] = property_schema

    _check_schema_size(result, schema.name, "Anthropic")
    return result


def to_gemini_schema(schema: Schema) -> Dict[str, Any]:
    """
    Convert Schema to Google Gemini's schema format.

    Gemini uses a slightly different approach where the schema is an items schema
    for an array with a single item, and requires propertyOrdering.
    """
    result: Dict[str, Any] = {
        "type": "object",
        "properties": {},
        "required": schema.required_properties(),
    }

    for name, prop in schema.properties.items():
        property_schema: Dict[str, Any] = {
            "type": prop.type,
        }

        if prop.description:
            property_schema["description"] = prop.description

        if prop.enum:
            property_schema["enum"] = prop.enum

        # Add minimum/maximum constraints for numeric types
        if prop.type in ["integer", "number"]:
            if prop.minimum is not None:
                property_schema["minimum"] = prop.minimum
            if prop.maximum is not None:
                property_schema["maximum"] = prop.maximum

        # Handle nested objects
        if prop.type == "object" and prop.object_schema:
            # Convert nested schema
            nested_schema = to_gemini_schema(prop.object_schema)
            # Copy properties and required fields
            property_schema["properties"] = nested_schema["properties"]
            if "required" in nested_schema and nested_schema["required"]:
                property_schema["required"] = nested_schema["required"]
            property_schema["additionalProperties"] = nested_schema.get(
                "additionalProperties", False
            )
            if "propertyOrdering" in nested_schema:
                property_schema["propertyOrdering"] = nested_schema["propertyOrdering"]
        elif prop.type == "object" and prop.properties:
            # Handle inline object definition
            property_schema["properties"] = {}
            required_props = []
            sub_property_names = []

            for sub_name, sub_prop in prop.properties.items():
                sub_schema: Dict[str, Any] = {"type": sub_prop.type}
                sub_property_names.append(sub_name)

                if sub_prop.description:
                    sub_schema["description"] = sub_prop.description

                if sub_prop.enum:
                    sub_schema["enum"] = sub_prop.enum

                if sub_prop.type in ["integer", "number"]:
                    if sub_prop.minimum is not None:
                        sub_schema["minimum"] = sub_prop.minimum
                    if sub_prop.maximum is not None:
                        sub_schema["maximum"] = sub_prop.maximum

                if sub_prop.type == "array" and sub_prop.items:
                    sub_schema["items"] = sub_prop.items

                if sub_prop.required:
                    required_props.append(sub_name)

                property_schema["properties"][sub_name] = sub_schema

            if required_props:
                property_schema["required"] = required_props

            # Include propertyOrdering for nested objects too
            property_schema["propertyOrdering"] = sub_property_names
            property_schema["additionalProperties"] = prop.additional_properties

        # Handle array items
        elif prop.type == "array" and prop.array_items_schema:
            # Handle array of objects with a full schema
            property_schema["items"] = to_gemini_schema(prop.array_items_schema)
        elif prop.type == "array" and prop.items:
            # Handle simple array items or array of objects with inline schema
            property_schema["items"] = prop.items

        # Add default value if specified
        if prop.default is not None:
            property_schema["default"] = prop.default

        result["properties"][name] = property_schema

    # Add propertyOrdering required by Gemini
    result["propertyOrdering"] = list(schema.properties.keys())

    _check_schema_size(result, schema.name, "Gemini")
    return result


def to_ollama_schema(schema: Schema) -> Dict[str, Any]:
    """
    Convert Schema to Ollama's schema format.

    Ollama follows standard JSON Schema conventions.
    """
    result: Dict[str, Any] = {
        "type": "object",
        "properties": {},
        "required": schema.required_properties(),
        "additionalProperties": False,
    }

    for name, prop in schema.properties.items():
        property_schema: Dict[str, Any] = {
            "type": prop.type,
        }

        if prop.description:
            property_schema["description"] = prop.description

        if prop.enum:
            property_schema["enum"] = prop.enum

        # Add minimum/maximum constraints for numeric types
        if prop.type in ["integer", "number"]:
            if prop.minimum is not None:
                property_schema["minimum"] = prop.minimum
            if prop.maximum is not None:
                property_schema["maximum"] = prop.maximum

        # Handle nested objects
        if prop.type == "object" and prop.object_schema:
            # Convert nested schema
            nested_schema = to_ollama_schema(prop.object_schema)
            # Copy properties and required fields
            property_schema["properties"] = nested_schema["properties"]
            if "required" in nested_schema and nested_schema["required"]:
                property_schema["required"] = nested_schema["required"]
            property_schema["additionalProperties"] = nested_schema.get(
                "additionalProperties", False
            )
        elif prop.type == "object" and prop.properties:
            # Handle inline object definition
            property_schema["properties"] = {}
            required_props = []

            for sub_name, sub_prop in prop.properties.items():
                sub_schema: Dict[str, Any] = {"type": sub_prop.type}

                if sub_prop.description:
                    sub_schema["description"] = sub_prop.description

                if sub_prop.enum:
                    sub_schema["enum"] = sub_prop.enum

                if sub_prop.type in ["integer", "number"]:
                    if sub_prop.minimum is not None:
                        sub_schema["minimum"] = sub_prop.minimum
                    if sub_prop.maximum is not None:
                        sub_schema["maximum"] = sub_prop.maximum

                if sub_prop.type == "array" and sub_prop.items:
                    sub_schema["items"] = sub_prop.items

                if sub_prop.required:
                    required_props.append(sub_name)

                property_schema["properties"][sub_name] = sub_schema

            if required_props:
                property_schema["required"] = required_props

            property_schema["additionalProperties"] = prop.additional_properties

        # Handle array items
        elif prop.type == "array" and prop.array_items_schema:
            # Handle array of objects with a full schema
            property_schema["items"] = to_ollama_schema(prop.array_items_schema)
        elif prop.type == "array" and prop.items:
            # Handle simple array items or array of objects with inline schema
            property_schema["items"] = prop.items

        # Add default value if specified
        if prop.default is not None:
            property_schema["default"] = prop.default

        result["properties"][name] = property_schema

    _check_schema_size(result, schema.name, "Ollama")
    return result


def _recursive_clean_for_openai(schema_part: Dict[str, Any]) -> None:
    """
    Recursively clean a schema dict for OpenAI, removing properties that cause issues.

    Args:
        schema_part: A schema or part of a schema to clean
    """
    if not isinstance(schema_part, dict):
        return

    # Remove minimum/maximum from the current level
    schema_part.pop("minimum", None)
    schema_part.pop("maximum", None)

    # Process properties if they exist
    if "properties" in schema_part and isinstance(schema_part["properties"], dict):
        for prop in schema_part["properties"].values():
            if isinstance(prop, dict):
                _recursive_clean_for_openai(prop)

    # Process nested items for arrays
    if "items" in schema_part and isinstance(schema_part["items"], dict):
        _recursive_clean_for_openai(schema_part["items"])

    # Check for nested 'items' with 'properties' (array of objects)
    if (
        "items" in schema_part
        and isinstance(schema_part["items"], dict)
        and "properties" in schema_part["items"]
    ):
        for prop in schema_part["items"]["properties"].values():
            if isinstance(prop, dict):
                _recursive_clean_for_openai(prop)


def schema_from_dict(schema_dict: Dict[str, Any]) -> Schema:
    """
    Convert a standard JSON schema dictionary to a Schema object.

    This is useful for converting existing schema dictionaries to our unified format.

    Args:
        schema_dict: A JSON schema dictionary

    Returns:
        Schema object
    """
    # Extract basic properties
    name = schema_dict.get("title", schema_dict.get("name", "Schema"))
    description = schema_dict.get("description", "")
    additional_properties = schema_dict.get("additionalProperties", False)

    # Extract property definitions
    properties = {}
    required_props = schema_dict.get("required", [])

    if "properties" in schema_dict:
        for prop_name, prop_def in schema_dict["properties"].items():
            # Is property required?
            is_required = prop_name in required_props

            # Basic property attributes
            prop_type = prop_def.get("type", "string")
            prop_desc = prop_def.get("description", "")

            # Create property object
            prop = SchemaProperty(type=prop_type, description=prop_desc, required=is_required)

            # Handle constraints for numeric types
            if prop_type in ["integer", "number"]:
                prop.minimum = prop_def.get("minimum")
                prop.maximum = prop_def.get("maximum")

            # Handle enum values
            if "enum" in prop_def:
                prop.enum = prop_def["enum"]

            # Handle default values
            if "default" in prop_def:
                prop.default = prop_def["default"]

            # Handle nested objects
            if prop_type == "object" and "properties" in prop_def:
                # Create a sub-schema for nested object
                sub_schema_dict = {
                    "title": f"{prop_name}Object",
                    "description": prop_desc,
                    "properties": prop_def["properties"],
                    "required": prop_def.get("required", []),
                    "additionalProperties": prop_def.get("additionalProperties", False),
                }

                prop.object_schema = schema_from_dict(sub_schema_dict)
                prop.additional_properties = prop_def.get("additionalProperties", False)

            # Handle array items
            if prop_type == "array" and "items" in prop_def:
                items = prop_def["items"]

                # If items is an object schema
                if isinstance(items, dict):
                    if items.get("type") == "object" and "properties" in items:
                        # Create a schema for array items
                        items_schema_dict = {
                            "title": f"{prop_name}Item",
                            "description": items.get("description", "Array item"),
                            "properties": items["properties"],
                            "required": items.get("required", []),
                            "additionalProperties": items.get("additionalProperties", False),
                        }

                        prop.array_items_schema = schema_from_dict(items_schema_dict)
                    else:
                        # For simple items or non-object schemas
                        prop.items = items
                else:
                    # Handle non-dict items (should be rare)
                    prop.items = {"type": "string"}

            properties[prop_name] = prop

    return Schema(name=name, description=description, properties=properties)
