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

def style_avoid(phrase):
  return f"* When responding, make a point to avoid language that {phrase}.  Do not mention this restriction in your response."

def style_encourage(phrase):
  return f"* When responding, you are encouraged to use language that {phrase}.  Do not mention this instruction in your response."

def build(short_prompt, data):
  verbosity = int(data.get('verbosity', 2))
  reading_level = int(data.get('reading_level', 2))

  # "Optional" prompts; -1 to discourage or +1 to encourage
  optional = []
  sports = int(data.get('sports', 0))
  if sports == 1:
    optional.append(style_encourage("relates to sports"))
  if sports == -1:
    optional.append(style_avoid("relates to sports"))

  politics = int(data.get('politics', 0))
  if politics == 1:
    optional.append(style_encourage("relates to politics"))
  if politics == -1:
    optional.append(style_avoid("relates to politics"))

  celebrity = int(data.get('celebrity', 0))
  if celebrity == 1:
    optional.append(style_encourage("relates to celebrity"))
  if celebrity == -1:
    optional.append(style_avoid("relates to celebrity"))

  science = int(data.get('science', 0))
  if science == 1:
    optional.append(style_encourage("relates to science"))
  if science == -1:
    optional.append(style_avoid("relates to science"))

  religion = int(data.get('religion', 0))
  if religion == 1:
    optional.append(style_encourage("relates to religion"))
  if religion == -1:
    optional.append(style_avoid("relates to religion"))

  base_prompt = verbalator.common.PROMPTS[short_prompt]

  return f"""
You are a helpful assistant.  When responding:
* {VERBOSITY_LEVELS[verbosity]}
* {READING_LEVELS[reading_level]}
{chr(10).join(optional)}

Answer the following question about the user-provided text: {base_prompt}
"""

