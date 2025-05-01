#!/usr/bin/python3

"""
Exemplar task for writing a historical essay.
"""

from lib.exemplars.base import (
    register_exemplar, ExemplarType, compare_models, generate_report
)

# Register the Wars of the Roses essay exemplar
register_exemplar(
    id="wars_of_roses_essay",
    name="400-Word Essay on the Wars of the Roses",
    prompt="""
Write a 400-word essay on the topic of the Wars of the Roses.

Your essay should:
1. Provide historical context about this conflict
2. Explain the key factions involved
3. Outline major events and turning points
4. Discuss the significance and historical impact

Ensure your essay is well-structured with an introduction, body paragraphs, and conclusion.
Stay as close as possible to 400 words.
""",
    description="Tests the model's ability to write a concise, informative historical essay with proper structure.",
    type=ExemplarType.KNOWLEDGE,
    tags=["history", "essay", "writing"],
    context="You are a history professor writing clear, accurate, and engaging content for students.",
    temperature=0.5,  # Balanced between creativity and factual accuracy
    max_tokens=800  # Allow enough tokens for a 400-word response
)

# Function to run this exemplar with multiple models
def run_wars_of_roses_exemplar(models=None, num_models=3):
    """
    Run the Wars of the Roses essay exemplar with specified models.
    
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
        
    compare_models("wars_of_roses_essay", models)
    report_path = generate_report("wars_of_roses_essay")
    print(f"Report generated at: {report_path}")
    return report_path

if __name__ == "__main__":
    run_wars_of_roses_exemplar()