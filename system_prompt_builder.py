#!/usr/bin/python3

import verbalator.common

VERBOSITY_LEVELS = [
    "Responses should be very concise, and avoid giving unnecessary details.",
    "Responses should be somewhat concise.",
    "Responses should be neither too concise nor too verbose.",
    "Responses should be somewhat verbose.",
    "Responses should be very verbose.",
]

READING_LEVELS = [
    "Responses should be as simple as possible, ideally at a second-grade reading level.",
    "Responses should use simple language, ideally at a fifth-grade reading level.",
    "Responses should use language that is not too complicated, ideally at an eighth-grade reading level.",
    "Responses should use a broad vocabulary, ideally at a tenth-grade reading level.",
    "Responses should use complex language, ideally at a college reading level.",
]

def build_system_prompt(short_prompt):
  base_prompt = verbalator.common.PROMPTS[short_prompt]

"""
You are a helpful assistant.  When responding:
* {verbosity}
* {reading_level}

Answer the following question about the user-provided text: {prompt}
"""

