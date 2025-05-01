#!/usr/bin/python3

"""
Exemplar task for solving a logical reasoning puzzle involving multiple interconnected statements.
"""

from lib.exemplars.base import (
    register_exemplar, ExemplarType, compare_models, generate_report
)

# The solution (for reference)
SOLUTION = """
* Position 1: Engineer, white house, water, rabbit
* Position 2: Writer, green house, tea, cat
* Position 3: Accountant, yellow house, milk, FISH
* Position 4: Doctor, red house, beer, horse
* Position 5: Lawyer, blue house, juice, dog
"""

# Register the neighborhood puzzle exemplar
register_exemplar(
    id="neighborhood_puzzle",
    name="Neighborhood Logic Puzzle",
    prompt="""
Five people live in different colored houses in a row on Puzzle Lane. Each person has a different profession, preferred beverage, and pet. Using only the clues below, determine who owns the fish.

1. The person in the red house is a doctor.
2. The engineer drinks water.
3. The house with the green roof is immediately to the right of the white house.
4. The accountant lives in the yellow house.
5. The person in the center house drinks milk.
6. The lawyer lives in the rightmost house.
7. The person who has a cat drinks tea.
8. The person with a dog lives in the blue house.
9. The writer has a cat.
10. The person in the leftmost house is an engineer.
11. The person with a horse lives next to the lawyer.
12. The person with a rabbit lives in the leftmost house.
13. The lawyer's neighbor drinks beer.
14. The person who drinks juice owns a dog.
15. The person who owns a cat lives next to the person who drinks milk.
16. The doctor does not own a rabbit.
17. The person who drinks beer lives next to the person who owns a dog.

Please show your reasoning step by step, and present your final answer in a clear format.
""",
    description="Tests the model's ability to solve a complex logic puzzle by tracking multiple constraints and making deductions.",
    type=ExemplarType.REASONING,
    tags=["logic puzzle", "deduction", "constraint satisfaction"],
    context="You are a logical reasoning assistant tasked with solving complex puzzles by tracking constraints and making valid inferences.",
    temperature=0.2  # Lower temperature for more logical responses
)

# Function to run this exemplar with multiple models
def run_neighborhood_puzzle_exemplar(models=None, num_models=3):
    """
    Run the neighborhood puzzle exemplar with specified models.
    
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
            models = ["gpt-4o-mini-2024-07-18", "gemma2:9b"]
        
    compare_models("neighborhood_puzzle", models)
    report_path = generate_report("neighborhood_puzzle")
    print(f"Report generated at: {report_path}")
    return report_path

if __name__ == "__main__":
    run_neighborhood_puzzle_exemplar()