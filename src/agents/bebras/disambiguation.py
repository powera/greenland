#!/usr/bin/env python3
"""
Disambiguation logic for matching words to lemmas.

This module handles the complex task of matching extracted words to the correct
lemmas in the database, especially when there are multiple candidates (polysemes).
"""

import logging
from typing import Optional, List

import util.prompt_loader
from wordfreq.storage.database import Lemma
from clients.unified_client import UnifiedLLMClient
from clients.types import Schema, SchemaProperty

logger = logging.getLogger(__name__)


def find_best_lemma_match(
    session,
    lemma_text: str,
    pos: str,
    disambiguation_hint: Optional[str] = None
) -> Optional[Lemma]:
    """
    Find the best matching lemma for a word.

    Args:
        session: Database session
        lemma_text: The lemma text to match (e.g., "mouse", "eat")
        pos: Part of speech (noun, verb, adjective, adverb)
        disambiguation_hint: Optional hint to help with disambiguation

    Returns:
        Best matching Lemma object, or None if no match found
    """
    # Normalize POS
    pos_normalized = _normalize_pos(pos)

    # Query for exact matches
    query = session.query(Lemma).filter(
        Lemma.lemma_text.ilike(f"%{lemma_text}%"),
        Lemma.pos_type == pos_normalized
    )

    candidates = query.all()

    if not candidates:
        logger.debug(f"No lemma candidates found for '{lemma_text}' (POS: {pos})")
        return None

    if len(candidates) == 1:
        # Easy case: only one match
        logger.debug(f"Single match for '{lemma_text}': {candidates[0].guid}")
        return candidates[0]

    # Multiple candidates - need disambiguation
    logger.info(f"Multiple candidates for '{lemma_text}' (POS: {pos}): {len(candidates)}")

    # Filter by exact match first
    exact_matches = [
        c for c in candidates
        if c.lemma_text.lower() == lemma_text.lower()
    ]

    if exact_matches:
        candidates = exact_matches

    if len(candidates) == 1:
        return candidates[0]

    # Use disambiguation hint if available
    if disambiguation_hint:
        best_match = disambiguate_lemma(
            candidates=candidates,
            lemma_text=lemma_text,
            disambiguation_hint=disambiguation_hint
        )
        if best_match:
            return best_match

    # If still ambiguous, prefer lemmas without disambiguation markers
    no_disambiguation = [c for c in candidates if not c.disambiguation]
    if len(no_disambiguation) == 1:
        logger.info(f"Selected lemma without disambiguation: {no_disambiguation[0].guid}")
        return no_disambiguation[0]

    # Default to first candidate (could be improved)
    logger.warning(f"Ambiguous match for '{lemma_text}', defaulting to first: {candidates[0].guid}")
    return candidates[0]


def disambiguate_lemma(
    candidates: List[Lemma],
    lemma_text: str,
    disambiguation_hint: str,
    model: str = "gpt-5-mini"
) -> Optional[Lemma]:
    """
    Use LLM to disambiguate between multiple lemma candidates.

    Args:
        candidates: List of candidate Lemma objects
        lemma_text: The word being disambiguated
        disambiguation_hint: Context or hint about the intended meaning
        model: LLM model to use

    Returns:
        Best matching Lemma, or None if disambiguation fails
    """
    logger.info(f"Using LLM to disambiguate '{lemma_text}' with hint: {disambiguation_hint}")

    # Build candidate descriptions
    candidate_descriptions = []
    for i, lemma in enumerate(candidates):
        desc = f"{i+1}. {lemma.lemma_text}"
        if lemma.disambiguation:
            desc += f" ({lemma.disambiguation})"
        desc += f": {lemma.definition_text}"
        candidate_descriptions.append(desc)

    # Load prompt templates
    prompt_context = util.prompt_loader.get_context("wordfreq", "word_disambiguation")
    prompt_template = util.prompt_loader.get_prompt("wordfreq", "word_disambiguation")

    # Format the prompt with parameters
    formatted_prompt = prompt_template.format(
        lemma_text=lemma_text,
        disambiguation_hint=disambiguation_hint,
        candidate_descriptions="\n".join(candidate_descriptions),
        num_candidates=len(candidates)
    )

    # Combine context and prompt
    prompt = f"{prompt_context}\n\n{formatted_prompt}"

    # Build schema
    schema = Schema(
        name="Disambiguation",
        description="Select the best matching candidate",
        properties={
            "candidate_number": SchemaProperty(
                type="integer",
                description=f"The number (1-{len(candidates)}) of the best matching candidate"
            ),
            "reasoning": SchemaProperty(
                type="string",
                description="Brief explanation of why this candidate was chosen"
            )
        }
    )

    try:
        llm_client = UnifiedLLMClient()
        response = llm_client.generate_chat(
            prompt=prompt,
            model=model,
            json_schema=schema,
            timeout=30
        )

        if response.structured_data:
            candidate_num = response.structured_data.get("candidate_number", 1)
            reasoning = response.structured_data.get("reasoning", "")

            # Validate candidate number
            if 1 <= candidate_num <= len(candidates):
                selected = candidates[candidate_num - 1]
                logger.info(f"LLM selected candidate {candidate_num}: {selected.guid} - {reasoning}")
                return selected
            else:
                logger.error(f"Invalid candidate number from LLM: {candidate_num}")
                return None
        else:
            logger.error("No structured data from LLM for disambiguation")
            return None

    except Exception as e:
        logger.error(f"Error during LLM disambiguation: {e}", exc_info=True)
        return None


def _normalize_pos(pos: str) -> str:
    """
    Normalize part-of-speech tags to database format.

    Args:
        pos: POS tag (various formats)

    Returns:
        Normalized POS tag
    """
    pos_lower = pos.lower().strip()

    # Map common variations to canonical forms
    pos_map = {
        "n": "noun",
        "noun": "noun",
        "nouns": "noun",
        "v": "verb",
        "verb": "verb",
        "verbs": "verb",
        "adj": "adjective",
        "adjective": "adjective",
        "adjectives": "adjective",
        "adv": "adverb",
        "adverb": "adverb",
        "adverbs": "adverb"
    }

    return pos_map.get(pos_lower, pos_lower)


def interactive_disambiguation(
    candidates: List[Lemma],
    lemma_text: str,
    context: str
) -> Optional[Lemma]:
    """
    Interactively ask the user to disambiguate between candidates.

    Args:
        candidates: List of candidate Lemma objects
        lemma_text: The word being disambiguated
        context: Context about where the word appears

    Returns:
        Selected Lemma, or None if user skips
    """
    print(f"\nMultiple meanings found for '{lemma_text}' in context: {context}")
    print("\nCandidates:")

    for i, lemma in enumerate(candidates, 1):
        disambiguation = f" ({lemma.disambiguation})" if lemma.disambiguation else ""
        print(f"  {i}. {lemma.lemma_text}{disambiguation}")
        print(f"     {lemma.definition_text}")
        print(f"     [GUID: {lemma.guid}, Level: {lemma.difficulty_level}]")

    print(f"  0. Skip (don't link this word)")

    while True:
        try:
            choice = input(f"\nSelect 1-{len(candidates)} (or 0 to skip): ").strip()
            choice_num = int(choice)

            if choice_num == 0:
                return None
            elif 1 <= choice_num <= len(candidates):
                return candidates[choice_num - 1]
            else:
                print(f"Please enter a number between 0 and {len(candidates)}")
        except ValueError:
            print("Please enter a valid number")
        except (EOFError, KeyboardInterrupt):
            print("\nSkipping disambiguation")
            return None
