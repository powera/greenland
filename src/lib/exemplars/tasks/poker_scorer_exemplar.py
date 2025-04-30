#!/usr/bin/python3

"""
Exemplar task for generating and scoring poker hands.
"""

from lib.exemplars.base import (
    register_exemplar, ExemplarType, compare_models, generate_report
)

# Register the poker hand generator exemplar
register_exemplar(
    id="poker_hand_scorer",
    name="Generate and Score Poker Hands",
    prompt="""
Write a comprehensive Python function that:

1. Generates a random 5-card poker hand
2. Evaluates and scores the hand based on standard poker hand rankings
3. Returns both the hand and its score/type (e.g., Royal Flush, Straight, Two Pair, etc.)

Your solution should:
- Use standard playing card notation (e.g., '2H' for 2 of Hearts, 'KS' for King of Spades)
- Handle all possible poker hand types (Royal Flush, Straight Flush, Four of a Kind, Full House, Flush, Straight, Three of a Kind, Two Pair, One Pair, High Card)
- Include proper validation and error handling
- Be well-documented with comments explaining the logic
- Include a few example runs demonstrating the functionality

Format your code with clean structure and readability in mind.
""",
    description="Tests the model's ability to create a complex algorithm involving card games, randomization, and pattern recognition.",
    type=ExemplarType.CODING,
    tags=["python", "algorithms", "card games", "probability"],
    context="You are a programming assistant with expertise in game algorithms, probability, and software development.",
    temperature=0.5  # Balanced temperature for creative yet accurate coding
)

# Function to run this exemplar with multiple models
def run_poker_hand_exemplar(models=None, num_models=3):
    """
    Run the poker hand generator exemplar with specified models.
    
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
        
    compare_models("poker_hand_scorer", models)
    report_path = generate_report("poker_hand_scorer")
    print(f"Report generated at: {report_path}")
    return report_path

if __name__ == "__main__":
    run_poker_hand_exemplar()