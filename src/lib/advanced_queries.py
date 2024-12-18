#!/usr/bin/python3

"""Advanced query functions for generating explanations and analyzing text."""

import logging
from enum import Enum
from typing import Tuple, Dict, List, Union, Callable, Optional
from dataclasses import dataclass

from clients import unified_client
from telemetry import LLMUsage

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gemma2:9b"

@dataclass
class ResponseConfig:
    """Configuration for a response type."""
    context_template: str
    prompt_template: str
    description: str

class ResponseType(Enum):
    """Available response types for different kinds of topics."""
    HISTORICAL = "historical"    # Historical events, contexts, developments
    SCIENTIFIC = "scientific"    # Natural phenomena and scientific concepts
    TECHNICAL = "technical"      # Engineering and technology topics
    BIOGRAPHICAL = "biographical"  # Living or recently deceased people
    ANALYTICAL = "analytical"    # Critical analysis and evaluation
    LITERARY = "literary"        # Plot summaries and narrative descriptions
    CULTURAL = "cultural"        # Broader cultural movements and traditions

# Response type configurations
RESPONSE_CONFIGS = {
    ResponseType.HISTORICAL: ResponseConfig(
        context_template="""You are explaining historical topics to an educated general audience. Your response should be:
- Approximately {length} words in length
- Well-structured with clear chronology
- Include specific dates, key figures, and locations
- Focus on both what happened and why it matters
- Written in an engaging, narrative style
Avoid editorializing or modern political comparisons.""",
        prompt_template="Provide a {length}-word explanation of {topic}.",
        description="Historical events, contexts, and developments"
    ),
    
    ResponseType.SCIENTIFIC: ResponseConfig(
        context_template="""You are explaining scientific concepts to an educated general audience. Your response should be:
- Approximately {length} words in length
- Start with fundamental principles
- Use precise scientific terminology with clear explanations
- Include real-world examples and applications
- Build from basic to more complex aspects
- Incorporate relevant mathematical concepts when appropriate
Avoid oversimplification while maintaining accessibility.""",
        prompt_template="Provide a {length}-word scientific explanation of {topic}.",
        description="Natural phenomena and scientific concepts"
    ),
    
    ResponseType.TECHNICAL: ResponseConfig(
        context_template="""You are explaining technical concepts for an educated general audience. Your response should be:
- Approximately {length} words in length
- Begin with a high-level overview
- Break down complex concepts into understandable parts
- Include practical applications or examples
- Use technical terms with clear explanations
- Address both how it works and why it matters
- Include relevant diagrams or code examples if requested
Avoid oversimplification while maintaining clarity.""",
        prompt_template="Provide a {length}-word technical explanation of {topic}.",
        description="Engineering, technology, programming, and systems"
    ),
    
    ResponseType.BIOGRAPHICAL: ResponseConfig(
        context_template="""You are writing biographical descriptions for an educated general audience. Your response should be:
- Approximately {length} words in length
- Lead with the person's most significant contributions or role
- Include key life events and their impact
- Mention current activities or legacy if applicable
- Maintain a neutral, factual tone
- Focus on verified information
- Include relevant dates and locations
Avoid speculation and unsubstantiated claims.""",
        prompt_template="Provide a {length}-word biographical description of {topic}.",
        description="Living or recently deceased people"
    ),
    
    ResponseType.ANALYTICAL: ResponseConfig(
        context_template="""You are providing critical analysis for an educated general audience. Your response should be:
- Approximately {length} words in length
- Present a clear analytical framework
- Support claims with specific evidence
- Consider multiple interpretations where relevant
- Connect to broader themes or patterns
- Develop a cohesive argument
- Include relevant theoretical frameworks
Balance depth of analysis with clarity of expression.""",
        prompt_template="Provide a {length}-word analytical response about {topic}.",
        description="Critical analysis and evaluation"
    ),
    
    ResponseType.LITERARY: ResponseConfig(
        context_template="""You are providing plot summaries and narrative descriptions for an educated general audience. Your response should be:
- Approximately {length} words in length
- Begin with a brief introduction of the work
- Present the plot chronologically
- Focus on key events and character developments
- Include major plot points and resolution
- Mention genre and style where relevant
- Avoid detailed analysis or interpretation
Maintain narrative flow while being concise.""",
        prompt_template="Provide a {length}-word plot summary of {topic}.",
        description="Plot summaries and narrative descriptions"
    ),
    
    ResponseType.CULTURAL: ResponseConfig(
        context_template="""You are explaining cultural phenomena for an educated general audience. Your response should be:
- Approximately {length} words in length
- Provide relevant historical context
- Explain cultural significance and impact
- Include key trends and developments
- Address broader societal implications
- Recognize diverse perspectives
- Consider cross-cultural influences
- Acknowledge regional variations
Maintain cultural sensitivity while being informative.""",
        prompt_template="Provide a {length}-word explanation of this cultural topic: {topic}.",
        description="Broader cultural movements and traditions"
    )
}

def _calculate_timeout(target_length: int) -> int:
    """Calculate timeout based on response length.
    
    :param target_length: Target response length in words
    :return: Timeout in seconds
    """
    return 20 + (target_length // 5)

def _generate_response(
    topic: str,
    target_length: int,
    config: ResponseConfig,
    model: str = DEFAULT_MODEL
) -> Tuple[str, LLMUsage]:
    """Generate a response using the specified configuration.
    
    Args:
        topic: Topic to explain
        target_length: Desired length in words
        config: ResponseConfig containing templates and settings
        model: Model to use for generation
        
    Returns:
        Tuple containing (response_text, usage_metrics)
    """
    _validate_target_length(target_length)
    
    context = config.context_template.format(length=target_length)
    prompt = config.prompt_template.format(length=target_length, topic=topic)
    
    # Calculate timeout based on target length
    timeout = _calculate_timeout(target_length)
    
    response, _, usage = unified_client.generate_chat(
        prompt=prompt,
        model=model,
        context=context,
        timeout=timeout  # Pass timeout to unified client
    )
    
    return response.strip(), usage

def generate_smart_response(
    topic: str,
    target_length: int,
    model: str = DEFAULT_MODEL
) -> Tuple[str, LLMUsage, ResponseType]:
    """Generate an appropriate response based on topic categorization.
    
    Args:
        topic: Topic to explain
        target_length: Desired length in words
        model: Model to use for generation
        
    Returns:
        Tuple containing (response_text, usage_metrics, response_type)
    """
    # First categorize the topic
    categorization, cat_usage = categorize_topic(topic, model)
    response_type = ResponseType(categorization["response_type"])
    
    # Get the appropriate config
    config = RESPONSE_CONFIGS[response_type]
    
    # Generate the response
    response, gen_usage = _generate_response(topic, target_length, config, model)
    
    # Combine usage metrics from both operations
    total_usage = cat_usage.combine(gen_usage)
    
    return response, total_usage, response_type

def generate_response(
    topic: str,
    target_length: int,
    response_type: Union[str, ResponseType],
    model: str = DEFAULT_MODEL
) -> Tuple[str, LLMUsage]:
    """Generate a response for a given topic and response type.
    
    Args:
        topic: Topic to explain
        target_length: Desired length in words
        response_type: Type of response (can be string or ResponseType enum)
        model: Model to use for generation
        
    Returns:
        Tuple containing (response_text, usage_metrics)
        
    Raises:
        ValueError: If response_type is not valid
    """
    # Convert string to enum if needed
    if isinstance(response_type, str):
        try:
            response_type = ResponseType(response_type.lower())
        except ValueError:
            valid_types = [rt.value for rt in ResponseType]
            raise ValueError(f"Invalid response type. Must be one of: {', '.join(valid_types)}")
    
    # Get the configuration for this response type
    if response_type not in RESPONSE_CONFIGS:
        raise ValueError(f"No configuration found for response type: {response_type}")
    
    config = RESPONSE_CONFIGS[response_type]
    
    # Generate the response using the existing helper
    return _generate_response(topic, target_length, config, model)

def categorize_topic(topic: str, model: str = DEFAULT_MODEL) -> Tuple[Dict, LLMUsage]:
    """Determine appropriate response type for a given topic."""
    context = """You are categorizing topics to determine the most appropriate response type.
Consider these response types and their use cases:"""

    # Add descriptions for each response type
    for resp_type in ResponseType:
        context += f"\n- {resp_type.value}: {RESPONSE_CONFIGS[resp_type].description}"

    schema = {
        "type": "object",
        "properties": {
            "response_type": {
                "type": "string",
                "enum": [rt.value for rt in ResponseType]
            },
            "explanation": {"type": "string"},
            "secondary_aspects": {
                "type": "array",
                "items": {
                    "type": "string",
                    "enum": [rt.value for rt in ResponseType]
                }
            }
        },
        "required": ["response_type", "explanation", "secondary_aspects"]
    }

    prompt = f"Analyze this topic and determine the most appropriate response type: {topic}"
    
    _, response, usage = unified_client.generate_chat(
        prompt=prompt,
        model=model,
        json_schema=schema,
        context=context
    )
    
    return response, usage

# Analysis functions
def analyze_quotes(essay: str, model: str = DEFAULT_MODEL) -> Tuple[str, LLMUsage]:
    """Analyze quotes and cultural references in an essay."""
    _validate_input(essay)
    
    context = """You are analyzing text for an academic audience. For each quote or cultural reference, present your findings in this structure:
1. The exact quote or reference with preserved formatting
2. The source or cultural context
3. A 1-3 sentence explanation of its meaning
4. How it functions within the text's broader argument

List findings in order of appearance in the text."""

    prompt = f"""Identify and analyze all direct quotes and cultural references in this text:

{essay}"""
    
    response, _, usage = unified_client.generate_chat(
        prompt=prompt,
        model=model,
        context=context
    )
    
    return response.strip(), usage

def analyze_logic(essay: str, model: str = DEFAULT_MODEL) -> Tuple[str, LLMUsage]:
    """Analyze logical arguments in an essay."""
    _validate_input(essay)
    
    context = """You are conducting logical analysis for an academic audience. For each major argument, present your analysis in this structure:
1. The main conclusion being argued for
2. Both explicit and implicit premises
3. Evaluation of premise accuracy using available evidence
4. Assessment of the argument's logical validity
5. Identification of any logical fallacies or weaknesses

Focus on argument structure and logical relationships."""

    prompt = f"""Analyze the logical structure and validity of the arguments in this text:

{essay}"""
    
    response, _, usage = unified_client.generate_chat(
        prompt=prompt,
        model=model,
        context=context
    )
    
    return response.strip(), usage

# Validation functions
def _validate_input(text: str, min_length: int = 10) -> None:
    """Validate input text meets minimum requirements."""
    if not text or len(text.strip()) < min_length:
        raise ValueError(f"Input text must be at least {min_length} characters long")

def _validate_target_length(length: int, min_length: int = 50, max_length: int = 2000) -> None:
    """Validate target length is within reasonable bounds."""
    if not min_length <= length <= max_length:
        raise ValueError(f"Target length must be between {min_length} and {max_length} words")
