#!/usr/bin/python3

"""
Exemplar task for generating realistic dialogue between two firefighters.
"""

from lib.exemplars.base import register_exemplar, ExemplarType, compare_models, generate_report

# Register the firefighter dialogue exemplar
register_exemplar(
    id="firefighter_conversation",
    name="Firefighter Break Room Dialogue",
    prompt="""
Write a realistic scene of dialogue between two male firefighters (Rodriguez and Chen) who are talking during a quiet moment at the station. They should be discussing their (female) romantic partners and relationships in a way that feels authentic and natural.

Your scene should:
1. Show distinct personalities for both characters through their dialogue and speech patterns
2. Include some firefighter-specific terminology or references
3. Demonstrate a comfortable friendship between colleagues who know each other well
4. Reveal something meaningful about their relationships without being clichéd
5. Feel like a scene from a well-written television drama

The dialogue should be approximately 2-3 minutes if performed, so around 1-2 pages of script.
Format it as a scene with character names before each line of dialogue and minimal stage directions.
""",
    description="Tests the model's ability to create authentic dialogue.",
    type=ExemplarType.CREATIVE,
    tags=["dialogue", "relationships", "workplace", "character-development"],
    context="You are a skilled screenwriter who specializes in creating authentic dialogue between working professionals.",
    temperature=0.7,  # Higher temperature for creative variation
)


# Function to run this exemplar with multiple models
def run_firefighter_dialogue_exemplar(models=None, num_models=3):
    """
    Run the firefighter dialogue exemplar with specified models.

    Args:
        models: List of model names to use (if None, uses top models from database)
        num_models: Number of models to use if models parameter is None
    """
    from lib.exemplars import runner

    if models is None:
        # Get models from database
        all_models = runner.get_model_names()
        # Use the first num_models models, or all if fewer available
        models = all_models[: min(num_models, len(all_models))]
        if not models:
            print("No models available in database. Using default models.")
            models = ["gpt-4o-mini-2024-07-18", "smollm2:360m"]

    compare_models("firefighter_conversation", models)
    report_path = generate_report("firefighter_conversation")
    print(f"Report generated at: {report_path}")
    return report_path


if __name__ == "__main__":
    run_firefighter_dialogue_exemplar()
