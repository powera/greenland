#!/usr/bin/python3
"""Unit tests for schema conversion library."""

import unittest
import json
from typing import Dict, Any

import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from clients.lib import (
    Schema, SchemaProperty, 
    to_openai_schema, to_anthropic_schema, to_gemini_schema, to_ollama_schema,
    schema_from_dict
)


class SchemaConversionTestCase(unittest.TestCase):
    """Tests for schema conversion utilities."""

    def test_simple_schema_conversion(self):
        """Test basic schema conversion with simple properties."""
        schema = Schema(
            name="UserProfile",
            description="A user profile object",
            properties={
                "name": SchemaProperty("string", "Full name of the user"),
                "age": SchemaProperty("integer", "Age in years", minimum=0, maximum=120),
                "is_active": SchemaProperty("boolean", "Whether the user is active"),
                "interests": SchemaProperty("array", "List of interests", required=False,
                                          items={"type": "string"})
            }
        )

        # Convert to different formats
        openai_schema = to_openai_schema(schema)
        anthropic_schema = to_anthropic_schema(schema)
        gemini_schema = to_gemini_schema(schema)
        ollama_schema = to_ollama_schema(schema)

        # Verify OpenAI schema - all properties required, regardless of schema
        self.assertEqual(openai_schema["type"], "object")
        self.assertEqual(len(openai_schema["properties"]), 4)
        self.assertEqual(len(openai_schema["required"]), 4)
        
        # OpenAI shouldn't have min/max properties
        self.assertNotIn("minimum", openai_schema["properties"]["age"])
        self.assertNotIn("maximum", openai_schema["properties"]["age"])

        # Verify Anthropic schema
        self.assertEqual(anthropic_schema["type"], "object")
        self.assertEqual(len(anthropic_schema["properties"]), 4)
        self.assertEqual(len(anthropic_schema["required"]), 3)
        
        # Anthropic can have min/max
        self.assertIn("minimum", anthropic_schema["properties"]["age"])
        self.assertIn("maximum", anthropic_schema["properties"]["age"])

        # Verify Gemini schema
        self.assertEqual(gemini_schema["type"], "object")
        self.assertEqual(len(gemini_schema["properties"]), 4)
        self.assertEqual(len(gemini_schema["required"]), 3)
        
        # Check for propertyOrdering
        self.assertIn("propertyOrdering", gemini_schema)
        self.assertEqual(len(gemini_schema["propertyOrdering"]), 4)

        # Verify Ollama schema
        self.assertEqual(ollama_schema["type"], "object")
        self.assertEqual(len(ollama_schema["properties"]), 4)
        self.assertEqual(len(ollama_schema["required"]), 3)

    def test_nested_object_schema(self):
        """Test schema conversion with nested objects."""
        address_properties = {
            "street": SchemaProperty("string", "Street address"),
            "city": SchemaProperty("string", "City name"),
            "zip": SchemaProperty("string", "ZIP code", required=False)
        }
        
        schema = Schema(
            name="UserWithAddress",
            description="User with address information",
            properties={
                "name": SchemaProperty("string", "Full name of the user"),
                "address": SchemaProperty(
                    "object", 
                    "User's address",
                    properties=address_properties,
                    additional_properties=False
                )
            }
        )

        # Convert to different formats
        openai_schema = to_openai_schema(schema)
        anthropic_schema = to_anthropic_schema(schema)
        gemini_schema = to_gemini_schema(schema)
        ollama_schema = to_ollama_schema(schema)

        # Verify nested structures in OpenAI schema
        self.assertIn("address", openai_schema["properties"])
        self.assertEqual(openai_schema["properties"]["address"]["type"], "object")
        self.assertIn("properties", openai_schema["properties"]["address"])
        self.assertIn("street", openai_schema["properties"]["address"]["properties"])
        self.assertIn("city", openai_schema["properties"]["address"]["properties"])
        self.assertIn("zip", openai_schema["properties"]["address"]["properties"])
        
        # Check that required fields are correctly propagated
        # NOTE: OpenAI strict mode requires ALL properties to be in required array
        # (no optional fields supported)
        self.assertIn("required", openai_schema["properties"]["address"])
        self.assertIn("street", openai_schema["properties"]["address"]["required"])
        self.assertIn("city", openai_schema["properties"]["address"]["required"])
        self.assertIn("zip", openai_schema["properties"]["address"]["required"])  # OpenAI requires all properties

        # Verify Gemini has propertyOrdering at both levels
        self.assertIn("propertyOrdering", gemini_schema)
        self.assertIn("propertyOrdering", gemini_schema["properties"]["address"])
        self.assertEqual(len(gemini_schema["properties"]["address"]["propertyOrdering"]), 3)

    def test_array_of_objects_schema(self):
        """Test schema conversion with arrays of objects."""
        item_properties = {
            "id": SchemaProperty("string", "Item identifier"),
            "name": SchemaProperty("string", "Item name"),
            "price": SchemaProperty("number", "Item price", minimum=0)
        }
        
        item_schema = Schema(
            name="Item",
            description="Shopping cart item",
            properties=item_properties
        )
        
        schema = Schema(
            name="ShoppingCart",
            description="Shopping cart with items",
            properties={
                "customer_id": SchemaProperty("string", "Customer identifier"),
                "items": SchemaProperty(
                    "array", 
                    "List of items in cart",
                    array_items_schema=item_schema
                )
            }
        )

        # Convert to different formats
        openai_schema = to_openai_schema(schema)
        gemini_schema = to_gemini_schema(schema)

        # Verify array structure in OpenAI schema
        self.assertIn("items", openai_schema["properties"])
        self.assertEqual(openai_schema["properties"]["items"]["type"], "array")
        self.assertIn("items", openai_schema["properties"]["items"])
        self.assertEqual(openai_schema["properties"]["items"]["items"]["type"], "object")
        self.assertIn("id", openai_schema["properties"]["items"]["items"]["properties"])
        
        # Verify propertyOrdering in array items for Gemini
        self.assertIn("propertyOrdering", gemini_schema["properties"]["items"]["items"])

    def test_realistic_schema_conversion(self):
        """Test conversion with a realistic schema from linguistic_client."""
        # This is inspired by query_definitions schema in linguistic_client.py
        definition_prop = SchemaProperty(
            "object",
            "Definition of the word",
            properties={
                "definition": SchemaProperty("string", "The definition of the word for this specific meaning"),
                "pos": SchemaProperty("string", "The part of speech for this definition (noun, verb, etc.)"),
                "pos_subtype": SchemaProperty("string", "A subtype for the part of speech"),
                "phonetic_spelling": SchemaProperty("string", "Phonetic spelling of the word"),
                "lemma": SchemaProperty("string", "The base form (lemma) for this definition"),
                "ipa_spelling": SchemaProperty("string", "International Phonetic Alphabet for the word"),
                "special_case": SchemaProperty("boolean", "Whether this is a special case (foreign word, part of name, etc.)"),
                "examples": SchemaProperty(
                    "array",
                    "Example sentences using this definition",
                    items={"type": "string", "description": "Example sentence using this definition"}
                ),
                "notes": SchemaProperty("string", "Additional notes about this definition"),
                "chinese_translation": SchemaProperty("string", "The Chinese translation of the word"),
                "korean_translation": SchemaProperty("string", "The Korean translation of the word"),
                "confidence": SchemaProperty("number", "Confidence score from 0-1"),
            }
        )
        
        schema = Schema(
            name="WordDefinitions",
            description="Definitions for a word",
            properties={
                "definitions": SchemaProperty(
                    "array",
                    "List of definitions for the word",
                    array_items_schema=Schema(
                        name="Definition",
                        description="A single definition of the word",
                        properties=definition_prop.properties
                    )
                )
            }
        )

        # Convert to different formats
        openai_schema = to_openai_schema(schema)
        anthropic_schema = to_anthropic_schema(schema)
        gemini_schema = to_gemini_schema(schema)
        ollama_schema = to_ollama_schema(schema)

        # Verify nested array of objects structure
        self.assertIn("definitions", openai_schema["properties"])
        self.assertEqual(openai_schema["properties"]["definitions"]["type"], "array")
        self.assertEqual(openai_schema["properties"]["definitions"]["items"]["type"], "object")
        
        # Check definitions array item properties
        definitions_items = openai_schema["properties"]["definitions"]["items"]
        self.assertIn("properties", definitions_items)
        self.assertIn("definition", definitions_items["properties"])
        self.assertIn("pos", definitions_items["properties"])
        self.assertIn("examples", definitions_items["properties"])
        
        # Verify examples array in definition
        self.assertEqual(definitions_items["properties"]["examples"]["type"], "array")
        self.assertEqual(definitions_items["properties"]["examples"]["items"]["type"], "string")
        
        # Verify propertyOrdering in Gemini schema at all levels
        self.assertIn("propertyOrdering", gemini_schema)
        self.assertIn("propertyOrdering", gemini_schema["properties"]["definitions"]["items"])

    def test_schema_with_enums(self):
        """Test schema conversion with enum constraints."""
        schema = Schema(
            name="OrderStatus",
            description="Information about an order",
            properties={
                "id": SchemaProperty("string", "Order identifier"),
                "status": SchemaProperty(
                    "string", 
                    "Current status of the order",
                    enum=["pending", "processing", "shipped", "delivered", "cancelled"]
                ),
                "payment_method": SchemaProperty(
                    "string",
                    "Payment method used",
                    enum=["credit_card", "paypal", "bank_transfer"],
                    required=False
                )
            }
        )

        # Convert to different formats
        openai_schema = to_openai_schema(schema)
        anthropic_schema = to_anthropic_schema(schema)

        # Verify enum fields
        self.assertIn("enum", openai_schema["properties"]["status"])
        self.assertEqual(len(openai_schema["properties"]["status"]["enum"]), 5)
        self.assertIn("enum", openai_schema["properties"]["payment_method"])
        self.assertEqual(len(openai_schema["properties"]["payment_method"]["enum"]), 3)
        
        # Check the same for Anthropic
        self.assertIn("enum", anthropic_schema["properties"]["status"])
        self.assertEqual(len(anthropic_schema["properties"]["status"]["enum"]), 5)

    def test_cleaning_for_openai(self):
        """Test cleaning schema for OpenAI requirements."""
        schema = Schema(
            name="ProductInfo",
            description="Product information",
            properties={
                "id": SchemaProperty("string", "Product identifier"),
                "price": SchemaProperty("number", "Product price", minimum=0, maximum=10000),
                "dimensions": SchemaProperty(
                    "object",
                    "Product dimensions",
                    properties={
                        "length": SchemaProperty("number", "Length in cm", minimum=0),
                        "width": SchemaProperty("number", "Width in cm", minimum=0),
                        "height": SchemaProperty("number", "Height in cm", minimum=0)
                    }
                ),
                "ratings": SchemaProperty(
                    "array",
                    "Customer ratings",
                    array_items_schema=Schema(
                        name="Rating",
                        description="Customer rating",
                        properties={
                            "score": SchemaProperty("integer", "Rating score (1-5)", minimum=1, maximum=5),
                            "comment": SchemaProperty("string", "Rating comment", required=False)
                        }
                    )
                )
            }
        )

        # Convert to OpenAI schema
        openai_schema = to_openai_schema(schema)
        
        # Verify min/max are removed at all levels
        self.assertNotIn("minimum", openai_schema["properties"]["price"])
        self.assertNotIn("maximum", openai_schema["properties"]["price"])
        
        # Check nested object properties
        self.assertNotIn("minimum", openai_schema["properties"]["dimensions"]["properties"]["length"])
        
        # Check array items
        self.assertNotIn("minimum", openai_schema["properties"]["ratings"]["items"]["properties"]["score"])
        self.assertNotIn("maximum", openai_schema["properties"]["ratings"]["items"]["properties"]["score"])

    def test_schema_from_dict(self):
        """Test converting dictionary schema to Schema object."""
        schema_dict = {
            "type": "object",
            "title": "TranslationRequest",
            "description": "Request for word translation",
            "properties": {
                "word": {
                    "type": "string",
                    "description": "Word to translate"
                },
                "source_language": {
                    "type": "string",
                    "description": "Source language code",
                    "enum": ["en", "fr", "es", "de", "zh"]
                },
                "target_language": {
                    "type": "string",
                    "description": "Target language code",
                    "enum": ["en", "fr", "es", "de", "zh"]
                },
                "include_examples": {
                    "type": "boolean",
                    "description": "Whether to include example sentences",
                    "default": False
                }
            },
            "required": ["word", "source_language", "target_language"],
            "additionalProperties": False
        }
        
        # Convert dictionary to Schema
        schema = schema_from_dict(schema_dict)
        
        # Verify conversion
        self.assertEqual(schema.name, "TranslationRequest")
        self.assertEqual(schema.description, "Request for word translation")
        self.assertEqual(len(schema.properties), 4)
        
        # Check property details
        self.assertEqual(schema.properties["word"].type, "string")
        self.assertEqual(schema.properties["word"].required, True)
        self.assertTrue(schema.properties["source_language"].required)
        self.assertFalse(schema.properties["include_examples"].required)
        
        # Check enum values
        self.assertEqual(len(schema.properties["source_language"].enum), 5)
        self.assertIn("en", schema.properties["source_language"].enum)

    def test_realistic_linguistic_client_schema(self):
        """Test with a full realistic schema from linguistic_client."""
        # This is based on query_pronunciation schema from linguistic_client.py
        schema_dict = {
            "type": "object",
            "properties": {
                "pronunciation": {
                    "type": "object",
                    "properties": {
                        "ipa": {
                            "type": "string",
                            "description": "IPA pronunciation for the word in American English"
                        },
                        "phonetic": {
                            "type": "string",
                            "description": "Simple phonetic pronunciation (e.g. 'SOO-duh-nim' for 'pseudonym')"
                        },
                        "alternatives": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "variant": {
                                        "type": "string",
                                        "description": "Variant name (e.g. 'British', 'Australian', 'Alternative')"
                                    },
                                    "ipa": {
                                        "type": "string",
                                        "description": "IPA pronunciation for this variant"
                                    }
                                },
                                "additionalProperties": False,
                                "required": ["variant", "ipa"]
                            },
                            "description": "Alternative valid pronunciations (British, Australian, etc.)"
                        },
                        "confidence": {
                            "type": "number",
                            "description": "Confidence score from 0-1"
                        },
                        "notes": {
                            "type": "string",
                            "description": "Additional notes about the pronunciation"
                        }
                    },
                    "additionalProperties": False,
                    "required": ["ipa", "phonetic", "alternatives", "confidence", "notes"]
                }
            },
            "additionalProperties": False,
            "required": ["pronunciation"]
        }
        
        # Convert dictionary to Schema
        schema = schema_from_dict(schema_dict)
        
        # Convert to all formats
        openai_schema = to_openai_schema(schema)
        anthropic_schema = to_anthropic_schema(schema)
        gemini_schema = to_gemini_schema(schema)
        ollama_schema = to_ollama_schema(schema)
        
        # Verify complex nested structure is preserved
        self.assertIn("pronunciation", openai_schema["properties"])
        self.assertEqual(openai_schema["properties"]["pronunciation"]["type"], "object")
        self.assertIn("alternatives", openai_schema["properties"]["pronunciation"]["properties"])
        self.assertEqual(openai_schema["properties"]["pronunciation"]["properties"]["alternatives"]["type"], "array")
        
        # Check array item properties
        alt_items = openai_schema["properties"]["pronunciation"]["properties"]["alternatives"]["items"]
        self.assertEqual(alt_items["type"], "object")
        self.assertIn("variant", alt_items["properties"])
        
        # Verify required fields at multiple levels
        self.assertIn("pronunciation", openai_schema["required"])
        self.assertIn("required", openai_schema["properties"]["pronunciation"])
        self.assertIn("ipa", openai_schema["properties"]["pronunciation"]["required"])
        
        # Verify Gemini has propertyOrdering at all levels
        self.assertIn("propertyOrdering", gemini_schema)
        self.assertIn("propertyOrdering", gemini_schema["properties"]["pronunciation"])
        self.assertIn("propertyOrdering", gemini_schema["properties"]["pronunciation"]["properties"]["alternatives"]["items"])
        
        # Verify OpenAI cleaning removes all min/max constraints
        self.assertEqual(openai_schema["properties"]["pronunciation"]["properties"]["confidence"]["type"], "number")
        self.assertNotIn("minimum", openai_schema["properties"]["pronunciation"]["properties"]["confidence"])


if __name__ == "__main__":
    unittest.main()