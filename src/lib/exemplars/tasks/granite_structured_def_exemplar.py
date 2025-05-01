#!/usr/bin/python3

"""
Exemplar task for generating comprehensive word definitions with a structured JSON schema.
"""

import os
from typing import Dict, List, Optional

from lib.exemplars.base import (
    register_exemplar, ExemplarType, compare_models, generate_report
)
from clients.types import Schema, SchemaProperty
import util.prompt_loader

# Create a Schema for word definitions using the classes from clients/types.py
def create_definition_schema() -> Schema:
    """Create a Schema object for comprehensive word definitions."""
    
    # Create SchemaProperty for the definitions array items
    definition_properties = {
        "definition": SchemaProperty(
            type="string",
            description="The definition text"
        ),
        "part_of_speech": SchemaProperty(
            type="string",
            description="The part of speech for this definition",
            enum=["noun", "verb", "adjective", "adverb", "pronoun", 
                  "preposition", "conjunction", "interjection", 
                  "determiner", "article", "numeral", "auxiliary", "modal"]
        ),
        "subtype": SchemaProperty(
            type="string",
            description="The part-of-speech subtype"
        ),
        "phonetic": SchemaProperty(
            type="string",
            description="Simplified phonetic pronunciation with stressed syllables in caps"
        ),
        "lemma": SchemaProperty(
            type="string",
            description="The base form of the word"
        ),
        "ipa": SchemaProperty(
            type="string",
            description="IPA pronunciation of the word (American English)"
        ),
        "is_special_case": SchemaProperty(
            type="boolean",
            description="Whether this is a special case (foreign word, part of name, etc.)",
            default=False
        ),
        "examples": SchemaProperty(
            type="array",
            description="Example sentences showing usage",
            items={"type": "string"}
        ),
        "notes": SchemaProperty(
            type="string",
            description="Additional notes about this definition",
            required=False
        ),
        "chinese_translation": SchemaProperty(
            type="string",
            description="Chinese translation for this specific meaning"
        ),
        "korean_translation": SchemaProperty(
            type="string",
            description="Korean translation for this specific meaning"
        ),
        "confidence": SchemaProperty(
            type="number",
            description="Confidence score for this definition (0-1)",
            minimum=0,
            maximum=1
        )
    }
    
    # Create the definition item schema
    definition_schema = Schema(
        name="Definition",
        description="A single definition of the word",
        properties=definition_properties
    )
    
    # Create the main schema with word and definitions properties
    return Schema(
        name="WordDefinition",
        description="A comprehensive definition of a word with all its meanings",
        properties={
            "word": SchemaProperty(
                type="string",
                description="The word being defined"
            ),
            "definitions": SchemaProperty(
                type="array",
                description="List of definitions for the word",
                items={"type": "object"},
                array_items_schema=definition_schema
            )
        }
    )

long_context = util.prompt_loader.get_context("wordfreq", "definitions")

# Register the comprehensive word definition exemplar
register_exemplar(
    id="comprehensive_definition",
    name="JSON-Schema Comprehensive Word Definition",
    prompt="""
Define the word "granite" comprehensively, covering all its meanings.

Please provide a detailed response that follows the schema I've provided.
""",
    description="Tests the model's ability to provide comprehensive word definitions with detailed linguistic information.",
    type=ExemplarType.LINGUISTIC,
    tags=["definition", "linguistics", "translation", "structured_output"],
    context=long_context,
    temperature=0.3,  # Lower temperature for more factual responses
    structured_output=create_definition_schema()
)

# Function to run this exemplar with a specific word and models
def run_definition_exemplar(word="granite", models=None, num_models=3):
    """
    Run the comprehensive definition exemplar with specified models.
    
    Args:
        word: The word to define
        models: List of model names to use (if None, uses top models from database)
        num_models: Number of models to use if models parameter is None
    """
    from lib.exemplars import runner, storage, registry
    
    # Update the prompt with the specific word
    exemplar = registry.get_exemplar("comprehensive_definition")
    if exemplar:
        exemplar.prompt = exemplar.prompt.format(word=word)
        registry.register_exemplar(exemplar)
    
    if models is None:
        # Get models from database
        all_models = runner.get_model_names()
        # Use the first num_models models, or all if fewer available
        models = all_models[:min(num_models, len(all_models))]
        if not models:
            print("No models available in database. Using default models.")
            models = ["gpt-4o-mini-2024-07-18", "smollm2:360m"]
    
    results = []
    for model in models:
        # Run the exemplar and save the result
        result = runner.run_exemplar("comprehensive_definition", model)
        storage.save_result(result)
        results.append(result)
    
    # Generate and return the report
    report_path = generate_report("comprehensive_definition")
    print(f"Report generated at: {report_path}")
    print(f"Definitions for '{word}' generated with models: {', '.join(models)}")
    return results

# This function can be called with different words
def define_word(word, models=None):
    """Wrapper function to define a specific word."""
    return run_definition_exemplar(word=word, models=models)

if __name__ == "__main__":
    # Default execution - define "granite" with available models
    run_definition_exemplar()