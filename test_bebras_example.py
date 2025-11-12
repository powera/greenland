#!/usr/bin/env python3
"""
Example usage of BEBRAS agent for sentence-word link management.

This script demonstrates how to use BEBRAS to:
1. Analyze a sentence to extract vocabulary words
2. Link the sentence to lemmas in the database
3. Add translations for multiple languages
"""

import sys
from pathlib import Path

# Add src directory to path
GREENLAND_SRC_PATH = str(Path(__file__).parent / "src")
sys.path.insert(0, GREENLAND_SRC_PATH)

from wordfreq.agents.bebras import BebrasAgent


def example_single_sentence():
    """Example: Process a single sentence."""
    print("=" * 60)
    print("Example 1: Process a single sentence")
    print("=" * 60)

    # Initialize the agent
    agent = BebrasAgent(model="gpt-5-mini", debug=True)

    # Process a sentence with Chinese and Lithuanian translations
    result = agent.process_sentence(
        sentence_text="I eat a banana",
        source_language="en",
        target_languages=["lt", "zh"],
        context="Simple present tense example",
        verified=False
    )

    if result.get('success'):
        print(f"\n✓ Successfully processed sentence!")
        print(f"  Sentence ID: {result['sentence_id']}")
        print(f"  Linked words: {result['linked_words']}")
        print(f"  Unlinked words: {result['unlinked_words']}")
        print(f"  Minimum level: {result.get('minimum_level', 'N/A')}")

        # Show disambiguation needed
        if result.get('disambiguation_needed'):
            print(f"\n  Words needing disambiguation:")
            for word in result['disambiguation_needed']:
                print(f"    - {word['word']} ({word['pos']}): {word['hint']}")
    else:
        print(f"\n✗ Failed: {result.get('error')}")


def example_batch_processing():
    """Example: Process multiple sentences from a list."""
    print("\n" + "=" * 60)
    print("Example 2: Batch process multiple sentences")
    print("=" * 60)

    agent = BebrasAgent(model="gpt-5-mini")

    sentences = [
        "The cat sleeps on the mat",
        "She reads a book in the library",
        "They play soccer in the park"
    ]

    result = agent.process_sentence_batch(
        sentences=sentences,
        source_language="en",
        target_languages=["lt", "zh"],
        verified=False
    )

    print(f"\nBatch processing complete:")
    print(f"  Total: {result['total']}")
    print(f"  Success: {result['success_count']}")
    print(f"  Failure: {result['failure_count']}")


def example_analysis_only():
    """Example: Just analyze a sentence without storing."""
    print("\n" + "=" * 60)
    print("Example 3: Analyze sentence (without storing)")
    print("=" * 60)

    agent = BebrasAgent()

    result = agent.analyze_sentence(
        sentence_text="The mouse is on the table",
        source_language="en",
        context="Could be a computer mouse or an animal"
    )

    if result.get('success'):
        analysis = result['analysis']
        print(f"\nSentence pattern: {analysis.get('pattern')}")
        print(f"Tense: {analysis.get('tense')}")
        print(f"\nExtracted words:")
        for word in analysis.get('words', []):
            print(f"  - {word['lemma']} ({word['pos']})")
            print(f"    Role: {word['role']}")
            print(f"    Disambiguation: {word.get('disambiguation', 'N/A')}")


def example_cli_usage():
    """Show CLI usage examples."""
    print("\n" + "=" * 60)
    print("Example 4: Command-line usage")
    print("=" * 60)
    print("""
# Process a single sentence
python src/wordfreq/agents/bebras.py \\
    --sentence "I eat a banana" \\
    --languages lt zh

# Process sentences from a file
python src/wordfreq/agents/bebras.py \\
    --file sentences.txt \\
    --languages lt zh \\
    --verified

# With custom model and debug output
python src/wordfreq/agents/bebras.py \\
    --sentence "The cat sleeps" \\
    --languages lt zh \\
    --model gpt-5-mini \\
    --debug

# JSON output for programmatic processing
python src/wordfreq/agents/bebras.py \\
    --sentence "I eat a banana" \\
    --languages lt zh \\
    --json

# Run the old database integrity checker
python src/wordfreq/agents/bebras.py --check-integrity
    """)


if __name__ == '__main__':
    print("\nBEBRAS Agent - Example Usage")
    print("=" * 60)
    print("\nNOTE: These are example calls showing the API.")
    print("To actually run these, ensure all dependencies are installed.")
    print("\n" + "=" * 60)

    # Show the examples (but don't execute them due to missing dependencies)
    example_cli_usage()

    # If you want to test with a real database, uncomment these:
    # example_single_sentence()
    # example_batch_processing()
    # example_analysis_only()
