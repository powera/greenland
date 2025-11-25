#!/usr/bin/python3

"""
Exemplar tasks for testing the wordfreq translation system.

This module creates exemplars that test the LinguisticClient's query_definitions method
with specific words to ensure the translation and linguistic analysis system works correctly.
"""

import json
from typing import Dict, List, Optional, Any

from lib.exemplars.base import (
    register_exemplar, ExemplarType, compare_models, generate_report
)
from clients.types import Schema, SchemaProperty
import util.prompt_loader
from wordfreq.storage.models.enums import GrammaticalForm
from wordfreq.storage import database as linguistic_db

# Get the context used by the actual wordfreq system
wordfreq_context = util.prompt_loader.get_context("wordfreq", "definitions")

# Valid parts of speech (matching the actual system)
VALID_POS_TYPES = {
    "noun", "verb", "adjective", "adverb", "pronoun", 
    "preposition", "conjunction", "interjection", "determiner",
    "article", "numeral", "auxiliary", "modal"
}

def create_wordfreq_schema() -> Schema:
    """Create the exact schema used by the wordfreq translation system."""
    
    # Get valid grammatical forms for the schema
    valid_grammatical_forms = [form.value for form in GrammaticalForm]
    
    return Schema(
        name="WordDefinitions",
        description="Definitions and forms for a word",
        properties={
            "definitions": SchemaProperty(
                type="array",
                description="List of definitions and forms for the word",
                array_items_schema=Schema(
                    name="WordForm",
                    description="A single form/definition of the word",
                    properties={
                        "definition": SchemaProperty("string", "The definition of the word for this specific meaning"),
                        "pos": SchemaProperty("string", "The part of speech for this definition (noun, verb, etc.)", enum=list(VALID_POS_TYPES)),
                        "pos_subtype": SchemaProperty("string", "A subtype for the part of speech", enum=linguistic_db.get_all_pos_subtypes()),
                        "lemma": SchemaProperty("string", "The base form (lemma) for this definition"),
                        "grammatical_form": SchemaProperty("string", "The specific grammatical form (e.g., verb/infinitive, noun/plural)", enum=valid_grammatical_forms),
                        "is_base_form": SchemaProperty("boolean", "Whether this is the base form (infinitive, singular, etc.)"),
                        "phonetic_spelling": SchemaProperty("string", "Phonetic spelling of the word"),
                        "ipa_spelling": SchemaProperty("string", "International Phonetic Alphabet for the word"),
                        "special_case": SchemaProperty("boolean", "Whether this is a special case (foreign word, part of name, etc.)"),
                        "examples": SchemaProperty(
                            type="array",
                            description="Example sentences using this specific form",
                            items={"type": "string", "description": "Example sentence using this form"}
                        ),
                        "notes": SchemaProperty("string", "Additional notes about this form"),
                        "chinese_translation": SchemaProperty("string", "The Chinese translation of this form"),
                        "korean_translation": SchemaProperty("string", "The Korean translation of this form"),
                        "french_translation": SchemaProperty("string", "The French translation of this form"),
                        "swahili_translation": SchemaProperty("string", "The Swahili translation of this form"),
                        "vietnamese_translation": SchemaProperty("string", "The Vietnamese translation of this form"),
                        "lithuanian_translation": SchemaProperty("string", "The Lithuanian translation of this form"),
                        "confidence": SchemaProperty("number", "Confidence score from 0-1"),
                    }
                )
            )
        }
    )

def create_wordfreq_prompt(word: str) -> str:
    """Create the exact prompt used by the wordfreq translation system."""
    return f"""Provide comprehensive dictionary definitions for the word '{word}'. 

For each definition, include:
1. The specific grammatical form (e.g., verb/infinitive, noun/singular, verb/present_participle)
2. Whether it's the base form (infinitive for verbs, singular for nouns, etc.)
3. The lemma (base concept) this form represents
4. Specific example sentences that demonstrate this exact form

Pay special attention to distinguishing between different grammatical forms of the same lemma (e.g., "running" as gerund vs present participle)."""

# Register the vinegar exemplar
register_exemplar(
    id="wordfreq_vinegar",
    name="Wordfreq Translation Test: Vinegar",
    prompt=create_wordfreq_prompt("vinegar"),
    description="Tests the wordfreq translation system with the word 'vinegar' - a common noun with clear translations across languages.",
    type=ExemplarType.LINGUISTIC,
    tags=["wordfreq", "translation", "definitions", "structured_output", "vinegar"],
    context=wordfreq_context,
    temperature=0.3,  # Lower temperature for more factual responses
    structured_output=create_wordfreq_schema()
)

# Register the bicycle exemplar
register_exemplar(
    id="wordfreq_bicycle",
    name="Wordfreq Translation Test: Bicycle",
    prompt=create_wordfreq_prompt("bicycle"),
    description="Tests the wordfreq translation system with the word 'bicycle' - a common noun that can also be used as a verb, testing multiple POS handling.",
    type=ExemplarType.LINGUISTIC,
    tags=["wordfreq", "translation", "definitions", "structured_output", "bicycle"],
    context=wordfreq_context,
    temperature=0.3,  # Lower temperature for more factual responses
    structured_output=create_wordfreq_schema()
)

def run_wordfreq_exemplar(word: str, models: Optional[List[str]] = None, num_models: int = 3) -> List[Dict]:
    """
    Run a wordfreq exemplar with specified models.
    
    Args:
        word: The word to test ("vinegar" or "bicycle")
        models: List of model names to use (if None, uses top models from database)
        num_models: Number of models to use if models parameter is None
        
    Returns:
        List of ExemplarResult objects
    """
    from lib.exemplars.base import ExemplarRunner, ExemplarRegistry, ExemplarStorage
    
    # Determine exemplar ID based on word
    exemplar_id = f"wordfreq_{word.lower()}"
    
    # Initialize components
    registry = ExemplarRegistry()
    storage = ExemplarStorage()
    runner = ExemplarRunner(registry)
    
    if models is None:
        # Get models from database
        all_models = runner.get_model_names()
        # Use the first num_models models, or all if fewer available
        models = all_models[:min(num_models, len(all_models))]
        if not models:
            print("No models available in database. Using default models.")
            models = ["gpt-4o-mini-2024-07-18", "claude-3-5-haiku-20241022"]
    
    results = []
    for model in models:
        try:
            # Run the exemplar and save the result
            result = runner.run_exemplar(exemplar_id, model)
            storage.save_result(result)
            results.append(result)
            print(f"✓ Completed {exemplar_id} with {model}")
        except Exception as e:
            print(f"✗ Failed {exemplar_id} with {model}: {e}")
    
    # Generate and return the report
    try:
        report_path = generate_report(exemplar_id)
        print(f"Report generated at: {report_path}")
    except Exception as e:
        print(f"Failed to generate report: {e}")
    
    print(f"Wordfreq translation test for '{word}' completed with models: {', '.join(models)}")
    return results

def run_vinegar_exemplar(models: Optional[List[str]] = None, num_models: int = 3) -> List[Dict]:
    """Run the vinegar wordfreq exemplar."""
    return run_wordfreq_exemplar("vinegar", models, num_models)

def run_bicycle_exemplar(models: Optional[List[str]] = None, num_models: int = 3) -> List[Dict]:
    """Run the bicycle wordfreq exemplar."""
    return run_wordfreq_exemplar("bicycle", models, num_models)

def run_both_exemplars(models: Optional[List[str]] = None, num_models: int = 3) -> Dict[str, List[Dict]]:
    """
    Run both vinegar and bicycle exemplars.
    
    Args:
        models: List of model names to use
        num_models: Number of models to use if models parameter is None
        
    Returns:
        Dictionary with results for both words
    """
    print("Running wordfreq translation exemplars for 'vinegar' and 'bicycle'...")
    print("=" * 60)
    
    results = {}
    
    print("\n1. Testing 'vinegar':")
    print("-" * 30)
    results["vinegar"] = run_vinegar_exemplar(models, num_models)
    
    print("\n2. Testing 'bicycle':")
    print("-" * 30)
    results["bicycle"] = run_bicycle_exemplar(models, num_models)
    
    print("\n" + "=" * 60)
    print("All wordfreq translation exemplars completed!")
    
    return results

def validate_wordfreq_response(response_data: Dict[str, Any], word: str) -> Dict[str, Any]:
    """
    Validate a wordfreq response and provide analysis.
    
    Args:
        response_data: The structured response from the LLM
        word: The word that was queried
        
    Returns:
        Dictionary with validation results and analysis
    """
    validation = {
        "word": word,
        "valid": True,
        "errors": [],
        "warnings": [],
        "analysis": {}
    }
    
    # Check basic structure
    if not isinstance(response_data, dict):
        validation["valid"] = False
        validation["errors"].append("Response is not a dictionary")
        return validation
    
    if "definitions" not in response_data:
        validation["valid"] = False
        validation["errors"].append("Missing 'definitions' key")
        return validation
    
    definitions = response_data["definitions"]
    if not isinstance(definitions, list):
        validation["valid"] = False
        validation["errors"].append("'definitions' is not a list")
        return validation
    
    if len(definitions) == 0:
        validation["valid"] = False
        validation["errors"].append("No definitions provided")
        return validation
    
    # Analyze each definition
    validation["analysis"]["definition_count"] = len(definitions)
    validation["analysis"]["pos_types"] = set()
    validation["analysis"]["has_translations"] = {
        "chinese": 0,
        "korean": 0,
        "french": 0,
        "swahili": 0,
        "vietnamese": 0,
        "lithuanian": 0
    }
    validation["analysis"]["has_phonetics"] = 0
    validation["analysis"]["has_ipa"] = 0
    validation["analysis"]["has_examples"] = 0
    
    for i, definition in enumerate(definitions):
        if not isinstance(definition, dict):
            validation["errors"].append(f"Definition {i} is not a dictionary")
            continue
        
        # Check required fields
        required_fields = ["definition", "pos", "lemma"]
        for field in required_fields:
            if field not in definition:
                validation["errors"].append(f"Definition {i} missing required field: {field}")
        
        # Analyze POS
        if "pos" in definition:
            pos = definition["pos"]
            validation["analysis"]["pos_types"].add(pos)
            if pos not in VALID_POS_TYPES:
                validation["warnings"].append(f"Definition {i} has invalid POS: {pos}")
        
        # Check translations
        for lang in validation["analysis"]["has_translations"]:
            if definition.get(f"{lang}_translation"):
                validation["analysis"]["has_translations"][lang] += 1
        
        # Check phonetics and examples
        if definition.get("phonetic_spelling"):
            validation["analysis"]["has_phonetics"] += 1
        if definition.get("ipa_spelling"):
            validation["analysis"]["has_ipa"] += 1
        if definition.get("examples") and len(definition["examples"]) > 0:
            validation["analysis"]["has_examples"] += 1
    
    # Convert set to list for JSON serialization
    validation["analysis"]["pos_types"] = list(validation["analysis"]["pos_types"])
    
    return validation

if __name__ == "__main__":
    # Default execution - run both exemplars with available models
    run_both_exemplars()