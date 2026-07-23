#!/usr/bin/env python3
"""
Lape - Grammar Facts Generator Agent

⚠️  IMPORTANT: This agent has a custom Barsukas API in src/barsukas/routes/agents.py
    If you modify the public interface of this agent, you MUST update:
    - /agents/generate-grammar-fact/<lemma_id> endpoint
    Keep the API contract in sync to prevent runtime errors!

This agent generates language-specific grammatical facts for lemmas using LLM queries.
It supports various types of grammar facts that can be specified via command line parameters.

Supported fact types:

Noun facts:
- measure_words (Chinese): Generate appropriate measure words/classifiers for nouns
- grammatical_gender (French, Spanish, German, etc.): Determine noun gender (masculine, feminine, neuter)
- countability (English): Classify nouns as countable, uncountable, or both
- declension_class (Lithuanian): Determine which declension class (1-5) a noun follows
- animacy (English): Classify nouns as animate or inanimate (affects grammar in some languages)
- fanciful_collective (English): Ornamental animal collective nouns (a murder of crows);
  most animals have none, and no term is a valid result

Verb facts:
- verb_transitivity (English): Classify as transitive, intransitive, ditransitive, or ambitransitive
- verb_reflexivity (French, Spanish, German, Lithuanian, Italian): Identify reflexive verbs
- auxiliary_verb (French, German, Italian): Which auxiliary verb is used in compound tenses

Note: number_type (plurale_tantum/singulare_tantum) is auto-detected during form generation by Vilkas.

"Lape" means "fox" in Lithuanian - clever and precise in analyzing grammar!
"""

import logging
import sys
from pathlib import Path

# Add src directory to path
GREENLAND_SRC_PATH = str(Path(__file__).parent.parent)
if GREENLAND_SRC_PATH not in sys.path:
    sys.path.insert(0, GREENLAND_SRC_PATH)

# Import from modular structure
from agents.lape.agent import LapeAgent
from agents.lape.cli import main

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

# Re-export for backward compatibility with Barsukas API
__all__ = ["LapeAgent", "main"]

if __name__ == "__main__":
    main()
