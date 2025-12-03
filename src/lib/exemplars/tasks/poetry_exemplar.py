#!/usr/bin/python3

"""
Exemplar task for generating sonnets about daffodils in spring.
"""

from lib.exemplars.base import register_exemplar, ExemplarType, compare_models, generate_report

# Register the sonnet exemplar
register_exemplar(
    id="daffodil_sonnet",
    name="Sonnet about Daffodils in Spring",
    prompt="""
Write a sonnet (14 lines following traditional English sonnet structure) about seeing daffodils in spring.

Your sonnet should:
1. Follow the Shakespearean sonnet form (14 lines with an ABABCDCDEFEFGG rhyme scheme)
2. Use iambic pentameter (10 syllables per line with alternating unstressed and stressed syllables)
3. Include vivid imagery of daffodils and spring landscapes
4. Incorporate themes of renewal, beauty, and the transient nature of spring
5. End with a meaningful couplet that provides a conclusion or emotional turn

Make the language elegant and evocative, while maintaining the technical requirements of a sonnet.
""",
    description="Tests the model's ability to generate structured poetry following formal constraints while conveying specific imagery and themes.",
    type=ExemplarType.CREATIVE,
    tags=["poetry", "sonnet", "creative-writing", "nature"],
    context="You are a skilled poet with expertise in formal verse structures, particularly sonnets in the Shakespearean tradition.",
    temperature=0.7,  # Higher temperature for more creative responses
)


# Function to run this exemplar with multiple models
def run_daffodil_sonnet_exemplar(models=None, num_models=3):
    """
    Run the daffodil sonnet exemplar with specified models.

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

    compare_models("daffodil_sonnet", models)
    report_path = generate_report("daffodil_sonnet")
    print(f"Report generated at: {report_path}")
    return report_path


if __name__ == "__main__":
    run_daffodil_sonnet_exemplar()
