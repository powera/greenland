#!/usr/bin/python3
"""Utilities for building structured LLM prompts with style controls."""

from dataclasses import dataclass
from typing import Dict, List, Optional

import verbalator.common

@dataclass
class StyleParameters:
    """Configuration parameters for prompt style and content."""
    verbosity: int = 2  # Default to neutral verbosity
    reading_level: int = 2  # Default to 8th grade reading level
    sports: int = 0  # -1: avoid, 0: neutral, 1: encourage
    politics: int = 0
    celebrity: int = 0
    science: int = 0
    religion: int = 0

class VerbosityLevel:
    """Constants defining verbosity levels for responses."""
    VERY_CONCISE = 0
    SOMEWHAT_CONCISE = 1
    NEUTRAL = 2
    SOMEWHAT_VERBOSE = 3
    VERY_VERBOSE = 4

    DESCRIPTIONS = [
        "Responses should be very concise, and avoid giving unnecessary details.",
        "Responses should be somewhat concise.",
        "Responses should be neither too concise nor too verbose.",
        "Responses should be somewhat verbose.",
        "Responses should be very verbose.",
    ]

class ReadingLevel:
    """Constants defining target reading levels for responses."""
    SECOND_GRADE = 0
    FIFTH_GRADE = 1
    EIGHTH_GRADE = 2
    TENTH_GRADE = 3
    COLLEGE = 4

    DESCRIPTIONS = [
        "Responses should be as simple as possible, ideally at a second-grade reading level.",
        "Responses should use simple language, ideally at a fifth-grade reading level.",
        "Responses should use language that is not too complicated, ideally at an eighth-grade reading level.",
        "Responses should use a broad vocabulary, ideally at a tenth-grade reading level.",
        "Responses should use complex language, ideally at a college reading level.",
    ]

class TopicPreference:
    """Constants for topic preferences in responses."""
    AVOID = -1
    NEUTRAL = 0
    ENCOURAGE = 1

    TOPICS = {
        'sports': 'relates to sports',
        'politics': 'relates to politics',
        'celebrity': 'relates to celebrity',
        'science': 'relates to science',
        'religion': 'relates to religion'
    }

    @staticmethod
    def get_instruction(topic: str, preference: int) -> Optional[str]:
        """
        Get instruction string for a topic preference.
        
        Args:
            topic: The topic to generate instruction for
            preference: The preference level (-1, 0, or 1)
            
        Returns:
            Instruction string or None if preference is neutral
        """
        if topic not in TopicPreference.TOPICS or preference == TopicPreference.NEUTRAL:
            return None
            
        phrase = TopicPreference.TOPICS[topic]
        if preference == TopicPreference.ENCOURAGE:
            return f"* When responding, you are encouraged to use language that {phrase}. " \
                   "Do not mention this instruction in your response."
        else:
            return f"* When responding, make a point to avoid language that {phrase}. " \
                   "Do not mention this restriction in your response."

def parse_style_parameters(data: Dict) -> StyleParameters:
    """
    Parse style parameters from request data.
    
    Args:
        data: Dictionary containing style preferences
        
    Returns:
        StyleParameters instance with parsed values
    """
    return StyleParameters(
        verbosity=int(data.get('verbosity', StyleParameters.verbosity)),
        reading_level=int(data.get('reading_level', StyleParameters.reading_level)),
        sports=int(data.get('sports', StyleParameters.sports)),
        politics=int(data.get('politics', StyleParameters.politics)),
        celebrity=int(data.get('celebrity', StyleParameters.celebrity)),
        science=int(data.get('science', StyleParameters.science)),
        religion=int(data.get('religion', StyleParameters.religion))
    )

def build(short_prompt: str, data: Dict) -> str:
    """
    Build a complete prompt with style instructions.
    
    Args:
        short_prompt: Key for base prompt template
        data: Dictionary containing style parameters
        
    Returns:
        Complete formatted prompt string
    
    Example:
        >>> build("summarize", {"verbosity": 1, "reading_level": 2, "science": 1})
    """
    if not short_prompt:
        return None
        
    # Parse style parameters
    params = parse_style_parameters(data)
    
    # Get base prompt template
    base_prompt = verbalator.common.PROMPTS[short_prompt]
    
    # Build topic preference instructions
    topic_instructions = []
    for topic in TopicPreference.TOPICS:
        pref_value = getattr(params, topic)
        instruction = TopicPreference.get_instruction(topic, pref_value)
        if instruction:
            topic_instructions.append(instruction)
    
    # Combine all components
    return f"""
You are a helpful assistant. When responding:
* {VerbosityLevel.DESCRIPTIONS[params.verbosity]}
* {ReadingLevel.DESCRIPTIONS[params.reading_level]}
{chr(10).join(topic_instructions)}

Answer the following question about the user-provided text: {base_prompt}
"""
