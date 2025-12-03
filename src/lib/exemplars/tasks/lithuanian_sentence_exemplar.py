#!/usr/bin/python3

"""
Lithuanian Sentence Generation Exemplar

Demonstrates the core sentence generation functionality using Lithuanian as the target language.
Shows how to generate multi-word phrases from word matrices and use LLM to create
properly structured sentences with correct grammar.

This exemplar provides a single demonstration of the sentence generation system.
"""

import json
from typing import Dict, List, Optional, Any

from lib.exemplars.base import register_exemplar, ExemplarType
from lib.sentence_generation import SentenceGenerator
from clients.unified_client import UnifiedLLMClient
from clients.types import Schema, SchemaProperty

# Sample word matrices for demonstration
SAMPLE_WORD_MATRICES = {
    "subjects": {
        "I": {"english": "I", "lithuanian": "aš", "guid": "PRON_001"},
        "he": {"english": "he", "lithuanian": "jis", "guid": "PRON_003"},
        "teacher": {"english": "teacher", "lithuanian": "mokytojas", "guid": "H01_001"},
    },
    "verbs": {
        "eat": {
            "english": "eat",
            "lithuanian": "valgyti",
            "compatible_subjects": ["subjects"],
            "compatible_objects": ["foods"],
            "present": {"I": "valgau", "he": "valgo", "teacher": "valgo"},
            "past": {"I": "valgiau", "he": "valgė", "teacher": "valgė"},
            "future": {"I": "valgysiu", "he": "valgys", "teacher": "valgys"},
        },
        "buy": {
            "english": "buy",
            "lithuanian": "pirkti",
            "compatible_subjects": ["subjects"],
            "compatible_objects": ["foods", "objects"],
            "present": {"I": "perku", "he": "perka", "teacher": "perka"},
            "past": {"I": "pirkau", "he": "pirko", "teacher": "pirko"},
            "future": {"I": "pirksiu", "he": "pirks", "teacher": "pirks"},
        },
    },
    "foods": {
        "apple": {"english": "apple", "lithuanian": "obuolys", "guid": "F01_001"},
        "bread": {"english": "bread", "lithuanian": "duona", "guid": "F01_002"},
        "banana": {"english": "banana", "lithuanian": "bananas", "guid": "F01_003"},
    },
    "objects": {
        "book": {"english": "book", "lithuanian": "knyga", "guid": "O01_001"},
        "car": {"english": "car", "lithuanian": "automobilis", "guid": "O01_002"},
    },
    "colors": {
        "red": {"english": "red", "lithuanian": "raudonas", "guid": "C01_001"},
        "blue": {"english": "blue", "lithuanian": "mėlynas", "guid": "C01_002"},
        "green": {"english": "green", "lithuanian": "žalias", "guid": "C01_003"},
    },
}

# Sample Lithuanian grammar rules
LITHUANIAN_GRAMMAR_RULES = {
    "lt": {
        "cases": {
            "accusative": {
                "endings": {
                    "masculine_as": "ą",
                    "masculine_is": "į",
                    "feminine_a": "ą",
                    "default": "ą",
                }
            }
        },
        "verb_conjugation": {
            "present": {"default": ""},
            "past": {"default": ""},
            "future": {"default": ""},
        },
    }
}


def create_sentence_generation_schema() -> Schema:
    """Create schema for sentence generation task."""
    return Schema(
        name="LithuanianSentenceGeneration",
        description="Generate a Lithuanian sentence with proper grammar from English components",
        properties={
            "analysis": SchemaProperty(
                type="object",
                description="Analysis of the sentence components",
                properties={
                    "subject": SchemaProperty("string", "The subject of the sentence"),
                    "verb": SchemaProperty("string", "The verb in infinitive form"),
                    "object": SchemaProperty("string", "The object of the sentence"),
                    "tense": SchemaProperty("string", "The requested tense"),
                    "makes_sense": SchemaProperty(
                        "boolean", "Whether this combination makes logical sense"
                    ),
                },
            ),
            "sentences": SchemaProperty(
                type="object",
                description="Generated sentences in both languages",
                properties={
                    "english": SchemaProperty("string", "Natural English sentence"),
                    "lithuanian": SchemaProperty(
                        "string", "Grammatically correct Lithuanian sentence with proper cases"
                    ),
                },
            ),
        },
    )


def create_sentence_prompt(subject: str, verb: str, obj: str, tense: str) -> str:
    """Create prompt for sentence generation."""
    return f"""
    Generate a Lithuanian sentence using these components:
    
    Subject: "{subject}"
    Verb: "{verb}" 
    Object: "{obj}"
    Tense: {tense}
    
    Requirements:
    1. Create a natural, grammatically correct Lithuanian sentence
    2. Use proper Lithuanian cases (nominative for subject, accusative for object)
    3. Conjugate the verb correctly for the subject and tense
    4. Provide both English and Lithuanian versions
    
    If this combination doesn't make logical sense, indicate that in your analysis.
   """


# Register the exemplar
register_exemplar(
    id="lithuanian_sentence_generation",
    name="Lithuanian Sentence Generation",
    prompt=create_sentence_prompt("he", "eat", "banana", "future"),
    description="Demonstrates generating properly structured Lithuanian sentences from English components using LLM with grammar awareness.",
    type=ExemplarType.LINGUISTIC,
    tags=["sentence_generation", "lithuanian", "grammar", "translation", "structured_output"],
    temperature=0.3,
    structured_output=create_sentence_generation_schema(),
)


def run_sentence_generation_demo(models: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    Run a demonstration of the sentence generation system.

    Args:
        models: List of model names to test with

    Returns:
        Dictionary with demonstration results
    """
    print("Lithuanian Sentence Generation Demonstration")
    print("=" * 50)

    # Initialize the sentence generator
    try:
        llm_client = UnifiedLLMClient()
    except Exception as e:
        print(f"Warning: Could not initialize LLM client: {e}")
        llm_client = None

    generator = SentenceGenerator(
        word_matrices=SAMPLE_WORD_MATRICES,
        grammar_rules=LITHUANIAN_GRAMMAR_RULES,
        llm_client=llm_client,
    )

    results = {
        "pattern_based_generation": [],
        "llm_enhanced_generation": [],
        "demonstration_complete": False,
    }

    print("\n1. Pattern-based Generation:")
    print("-" * 30)

    # Generate 3 pattern-based sentences
    for i in range(3):
        pattern = generator.create_sentence_pattern("SVO")
        if pattern:
            sentences = generator.pattern_to_sentences(pattern, ["en", "lt"])

            result = {"pattern": pattern, "sentences": sentences, "method": "pattern_based"}
            results["pattern_based_generation"].append(result)

            print(f"Pattern {i+1}:")
            print(
                f"  Components: {pattern['subject']['key']} + {pattern['verb']['key']} + {pattern['object']['key']} ({pattern['tense']})"
            )
            print(f"  English: {sentences.get('en', 'N/A')}")
            print(f"  Lithuanian: {sentences.get('lt', 'N/A')}")
            print()

    if llm_client:
        print("2. LLM-Enhanced Generation:")
        print("-" * 30)

        # Test specific combinations with LLM
        test_cases = [
            {"subject": "he", "verb": "eat", "object": "banana", "tense": "future"},
            {"subject": "I", "verb": "buy", "object": "book", "tense": "past"},
        ]

        for i, test_case in enumerate(test_cases):
            # Create a pattern manually for testing
            pattern = {
                "subject": {
                    "key": test_case["subject"],
                    "data": SAMPLE_WORD_MATRICES["subjects"][test_case["subject"]],
                },
                "verb": {
                    "key": test_case["verb"],
                    "data": SAMPLE_WORD_MATRICES["verbs"][test_case["verb"]],
                },
                "object": {
                    "key": test_case["object"],
                    "data": SAMPLE_WORD_MATRICES["foods"].get(test_case["object"])
                    or SAMPLE_WORD_MATRICES["objects"].get(test_case["object"]),
                },
                "tense": test_case["tense"],
            }

            llm_result = generator.generate_with_llm(pattern, "lt")

            if llm_result:
                results["llm_enhanced_generation"].append(llm_result)

                print(f"LLM Test {i+1}:")
                print(
                    f"  Components: {test_case['subject']} + {test_case['verb']} + {test_case['object']} ({test_case['tense']})"
                )
                print(f"  English: {llm_result['english']}")
                print(f"  Lithuanian: {llm_result['target_sentence']}")
                if llm_result.get("adjective_used"):
                    print(f"  Adjective added: {llm_result['adjective_used']}")
                print()
            else:
                print(f"LLM Test {i+1}: Failed to generate")
                print()
    else:
        print("2. LLM-Enhanced Generation: Skipped (no LLM client available)")
        print()

    results["demonstration_complete"] = True

    print("Demonstration completed!")
    print(f"Pattern-based sentences: {len(results['pattern_based_generation'])}")
    print(f"LLM-enhanced sentences: {len(results['llm_enhanced_generation'])}")

    return results


def validate_sentence_structure(sentence_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate the structure of a generated sentence.

    Args:
        sentence_data: Generated sentence data from LLM

    Returns:
        Validation results
    """
    validation = {"valid": True, "errors": [], "warnings": [], "analysis": {}}

    # Check required fields
    required_fields = ["analysis", "sentences"]
    for field in required_fields:
        if field not in sentence_data:
            validation["valid"] = False
            validation["errors"].append(f"Missing required field: {field}")

    if "sentences" in sentence_data:
        sentences = sentence_data["sentences"]
        if not isinstance(sentences, dict):
            validation["valid"] = False
            validation["errors"].append("'sentences' must be a dictionary")
        else:
            # Check for both language versions
            if "english" not in sentences:
                validation["warnings"].append("Missing English sentence")
            if "lithuanian" not in sentences:
                validation["warnings"].append("Missing Lithuanian sentence")

            # Basic length checks
            if sentences.get("english") and len(sentences["english"]) < 5:
                validation["warnings"].append("English sentence seems too short")
            if sentences.get("lithuanian") and len(sentences["lithuanian"]) < 5:
                validation["warnings"].append("Lithuanian sentence seems too short")

    if "analysis" in sentence_data:
        analysis = sentence_data["analysis"]
        if analysis.get("makes_sense") is False:
            validation["warnings"].append("LLM indicated the sentence doesn't make logical sense")

    return validation


if __name__ == "__main__":
    # Run the demonstration
    run_sentence_generation_demo()
