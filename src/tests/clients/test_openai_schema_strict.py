#!/usr/bin/env python3
"""
Comprehensive tests for OpenAI schema conversion with strict validation.

OpenAI's strict schema mode requires:
1. All object types must have "additionalProperties": false
2. All object types must have "required" array listing ALL properties (no optional fields)
3. The "required" array must contain exactly the keys in "properties" (no extras, no missing)
"""

import unittest
import json
import sys
from pathlib import Path

# Add src directory to path
GREENLAND_SRC_PATH = str(Path(__file__).parent.parent.parent)
if GREENLAND_SRC_PATH not in sys.path:
    sys.path.insert(0, GREENLAND_SRC_PATH)

from clients.lib import to_openai_schema
from clients.types import Schema, SchemaProperty


class TestOpenAISchemaStrictMode(unittest.TestCase):
    """Test OpenAI schema conversion meets strict mode requirements."""

    def validate_openai_strict_schema(self, schema_dict, path="root"):
        """
        Recursively validate that a schema meets OpenAI's strict requirements.

        Args:
            schema_dict: Schema dictionary to validate
            path: Current path in schema (for error messages)

        Raises:
            AssertionError: If schema violates strict mode requirements
        """
        if not isinstance(schema_dict, dict):
            return

        schema_type = schema_dict.get("type")

        if schema_type == "object":
            # Rule 1: Must have additionalProperties set to false
            self.assertIn(
                "additionalProperties",
                schema_dict,
                f"At {path}: object type must have 'additionalProperties'"
            )
            self.assertEqual(
                schema_dict["additionalProperties"],
                False,
                f"At {path}: additionalProperties must be false"
            )

            # Rule 2: If has properties, must have required array
            if "properties" in schema_dict:
                self.assertIn(
                    "required",
                    schema_dict,
                    f"At {path}: object with properties must have 'required' array"
                )

                # Rule 3: Required must be a list
                self.assertIsInstance(
                    schema_dict["required"],
                    list,
                    f"At {path}: 'required' must be a list"
                )

                # Rule 4: Required must contain exactly all property keys
                prop_keys = set(schema_dict["properties"].keys())
                required_keys = set(schema_dict["required"])

                self.assertEqual(
                    prop_keys,
                    required_keys,
                    f"At {path}: 'required' must contain exactly all property keys. "
                    f"Properties: {prop_keys}, Required: {required_keys}. "
                    f"Missing: {prop_keys - required_keys}, Extra: {required_keys - prop_keys}"
                )

                # Recurse into properties
                for prop_name, prop_value in schema_dict["properties"].items():
                    self.validate_openai_strict_schema(
                        prop_value,
                        f"{path}.properties.{prop_name}"
                    )

        elif schema_type == "array":
            # Recurse into items
            if "items" in schema_dict:
                self.validate_openai_strict_schema(
                    schema_dict["items"],
                    f"{path}.items"
                )

        # Recurse into any other nested structures
        for key, value in schema_dict.items():
            if isinstance(value, dict) and key not in ["additionalProperties", "required", "properties", "items"]:
                self.validate_openai_strict_schema(value, f"{path}.{key}")

    def test_simple_schema(self):
        """Test simple schema with basic types."""
        schema = Schema(
            name="Simple",
            description="A simple schema",
            properties={
                "name": SchemaProperty("string", "User name"),
                "age": SchemaProperty("integer", "User age")
            }
        )

        openai_schema = to_openai_schema(schema)

        # Validate it meets strict requirements
        self.validate_openai_strict_schema(openai_schema)

        # Verify specific requirements
        self.assertEqual(openai_schema["type"], "object")
        self.assertEqual(openai_schema["additionalProperties"], False)
        self.assertEqual(set(openai_schema["required"]), {"name", "age"})

    def test_nested_object_schema(self):
        """Test schema with nested objects."""
        schema = Schema(
            name="User",
            description="User with address",
            properties={
                "name": SchemaProperty("string", "User name"),
                "address": SchemaProperty(
                    "object",
                    "User address",
                    properties={
                        "street": SchemaProperty("string", "Street"),
                        "city": SchemaProperty("string", "City")
                    }
                )
            }
        )

        openai_schema = to_openai_schema(schema)
        self.validate_openai_strict_schema(openai_schema)

    def test_array_of_strings(self):
        """Test schema with array of simple types."""
        schema = Schema(
            name="TagList",
            description="List of tags",
            properties={
                "tags": SchemaProperty(
                    "array",
                    "Tag list",
                    items={"type": "string"}
                )
            }
        )

        openai_schema = to_openai_schema(schema)
        self.validate_openai_strict_schema(openai_schema)

    def test_array_of_objects_inline(self):
        """Test schema with array of objects using inline definition."""
        schema = Schema(
            name="UserList",
            description="List of users",
            properties={
                "users": SchemaProperty(
                    "array",
                    "User list",
                    items={
                        "type": "object",
                        "properties": {
                            "name": {"type": "string", "description": "Name"},
                            "email": {"type": "string", "description": "Email"}
                        }
                    }
                )
            }
        )

        openai_schema = to_openai_schema(schema)
        self.validate_openai_strict_schema(openai_schema)

    def test_deeply_nested_array_of_objects(self):
        """Test deeply nested arrays of objects (like zvirblis schema)."""
        schema = Schema(
            name="SentenceGeneration",
            description="Generated sentences",
            properties={
                "sentences": SchemaProperty(
                    "array",
                    "List of sentences",
                    items={
                        "type": "object",
                        "properties": {
                            "text": {
                                "type": "string",
                                "description": "Sentence text"
                            },
                            "translations": {
                                "type": "object",
                                "description": "Translations",
                                "additionalProperties": {"type": "string"}
                            },
                            "words": {
                                "type": "array",
                                "description": "Words used",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "lemma": {"type": "string", "description": "Base form"},
                                        "role": {"type": "string", "description": "Role"},
                                        "form": {"type": "string", "description": "Actual form"}
                                    }
                                }
                            }
                        }
                    }
                )
            }
        )

        openai_schema = to_openai_schema(schema)
        self.validate_openai_strict_schema(openai_schema)

    def test_zvirblis_exact_schema(self):
        """Test the exact schema used in zvirblis.py."""
        schema = Schema(
            name="SentenceGeneration",
            description="Generated sentences with grammatical analysis",
            properties={
                "sentences": SchemaProperty(
                    type="array",
                    description="List of generated sentences",
                    items={
                        "type": "object",
                        "properties": {
                            "translations": {
                                "type": "object",
                                "description": "Sentence in each language (keys are language codes)",
                                "additionalProperties": {"type": "string"}
                            },
                            "pattern": {
                                "type": "string",
                                "description": "Sentence pattern type (SVO, SVAO, etc.)"
                            },
                            "tense": {
                                "type": "string",
                                "description": "Verb tense (present, past, future)"
                            },
                            "words_used": {
                                "type": "array",
                                "description": "All words used in the TARGET LANGUAGE sentence (not English)",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "lemma": {"type": "string", "description": "Base form of the word in target language"},
                                        "role": {"type": "string", "description": "Role in sentence (subject, verb, object, etc.)"},
                                        "language_code": {"type": "string", "description": "Target language code (e.g., 'lt', 'zh')"},
                                        "grammatical_form": {"type": "string", "description": "Form used (e.g., '3s_present', 'past_participle')"},
                                        "grammatical_case": {"type": "string", "description": "Case if applicable (nominative, accusative, etc.)"},
                                        "declined_form": {"type": "string", "description": "Actual form used in sentence"}
                                    },
                                    "required": ["lemma", "role"]
                                }
                            }
                        },
                        "required": ["translations", "pattern", "words_used"]
                    }
                )
            }
        )

        openai_schema = to_openai_schema(schema)

        # This should pass all strict validation
        self.validate_openai_strict_schema(openai_schema)

        # Print the schema for debugging
        print("\n=== Generated OpenAI Schema ===")
        print(json.dumps(openai_schema, indent=2))

    def test_object_with_additional_properties_string(self):
        """Test object with additionalProperties: {type: string}."""
        schema = Schema(
            name="Translations",
            description="Translation map",
            properties={
                "translations": SchemaProperty(
                    "object",
                    "Language code to translation mapping",
                    items={"type": "string"}
                )
            }
        )

        openai_schema = to_openai_schema(schema)

        # Note: For objects with additionalProperties, we need special handling
        # The translations object should have additionalProperties but no required array
        # since it's a dynamic map
        self.assertEqual(openai_schema["type"], "object")


if __name__ == '__main__':
    unittest.main(verbosity=2)
