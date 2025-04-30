#!/usr/bin/python3

"""
Exemplar task for generating comprehensive word definitions.
"""

from lib.exemplars.base import (
    register_exemplar, ExemplarType, compare_models, generate_report
)

# Register the word definition exemplar
register_exemplar(
    id="granite_definition",
    name="Comprehensive Definition of 'Granite'",
    prompt="""
Write a comprehensive definition of the word "granite".

Your response should include:
1. All separate definitions/meanings of the word
2. The part of speech for each definition
3. Sample sentences demonstrating usage for each definition
4. Translations of the word in Chinese and Korean

Format your response clearly with appropriate headings and structure.
""",
    description="Tests the model's ability to provide comprehensive word definitions with translations and examples.",
    type=ExemplarType.INSTRUCTION,
    tags=["definition", "linguistics", "translation"],
    context="You are a linguistic assistant with expertise in definitions, etymology, and translations.",
    temperature=0.3  # Lower temperature for more factual responses
)

# Function to run this exemplar with multiple models
def run_granite_definition_exemplar(models=None, num_models=3):
    """
    Run the granite definition exemplar with specified models.
    
    Args:
        models: List of model names to use (if None, uses top models from database)
        num_models: Number of models to use if models parameter is None
    """
    from lib.exemplars import runner
    
    if models is None:
        # Get models from database
        all_models = runner.get_model_names()
        # Use the first num_models models, or all if fewer available
        models = all_models[:min(num_models, len(all_models))]
        if not models:
            print("No models available in database. Using default models.")
            models = ["gpt-4o-mini-2024-07-18", "smollm2:360m"]
        
    compare_models("granite_definition", models)
    report_path = generate_report("granite_definition")
    print(f"Report generated at: {report_path}")
    return report_path

if __name__ == "__main__":
    run_granite_definition_exemplar()
