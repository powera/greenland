#!/usr/bin/python3

import os

from openai import OpenAI
import tiktoken

import json
import pydantic  # for type signatures
import enum      # for type signatures

TEST_MODEL = "gpt-4o-mini-2024-07-18"
PROD_MODEL = "gpt-4o-2024-08-06"


def _load_key():
  with open("./keys/openai.key") as f:
    api_key = f.read().strip()
  return api_key


client = OpenAI(api_key=_load_key())


def generate_text(prompt, sample):
  model = TEST_MODEL
  encoder = tiktoken.get_encoding("cl100k_base")
  input_length = len(sample)
  if input_length > 12000:
    raise Exception("Input data too long")
  completion = client.chat.completions.create(
      model=model,
      messages=[
          {
              "role": "system",
              "content": "You are a concise assistant, answering this question about the user-provided text: " + prompt,
          },
          {
              "role": "user",
              "content": sample,
          },
      ],
      presence_penalty=0.25,  # scale is -2 to 2
      max_tokens=1536,
      temperature=0.15,  # scale is 0 to 2
  )
  print(completion.usage)
  return completion.choices[0].message.content, parse_usage(completion.usage)


PERSONAS = {
    "normal": "You are a helpful assistant.",
    "fifth_grader": """
This LLM responds like an educated but ordinary fifth grader. It expresses ideas clearly and uses simple, everyday language, avoiding advanced vocabulary or concepts. When explaining things, it breaks down concepts step by step, often comparing new ideas to familiar objects or experiences. It’s curious and enthusiastic, asking questions when unsure and occasionally sharing personal thoughts or feelings, as many kids do. The tone is friendly, casual, and sincere—like talking to a peer or a favorite teacher.""",
    }

def answer_question(prompt, persona="normal"):
  model = TEST_MODEL
  encoder = tiktoken.get_encoding("cl100k_base")
  input_length = len(prompt)
  if input_length > 12000:
    raise Exception("Input data too long")
  completion = client.chat.completions.create(
      model=model,
      messages=[
          {
              "role": "system",
              "content": PERSONAS[persona],
          },
          {
              "role": "user",
              "content": prompt,
          },
      ],
      max_tokens=1536,
      temperature=0.45,  # scale is 0 to 2
  )
  print(completion.usage)
  return completion.choices[0].message.content, parse_usage(completion.usage)


class QualityRating(enum.Enum):
  BAD = "Bad"
  MEDIOCRE = "Mediocre"
  GOOD = "Good"
  VERY_GOOD = "Very good"
  EXCELLENT = "Excellent"

  def __str__(self):
    return self.value

class ResponseSchema(pydantic.BaseModel):
  is_refusal: bool
  overall_quality: QualityRating
  factual_errors: str
  verbosity: str
  repetition: str
  unwarranted_assumptions: str

def evaluate_response(original_prompt, original_response):
  model = TEST_MODEL
  #encoder = tiktoken.get_encoding("cl100k_base")
  input_length = len(original_prompt) + len(original_response)
  if input_length > 12000:
    raise Exception("Input data too long")
  completion = client.beta.chat.completions.parse(
      model=model,
      messages=[
          {
              "role": "system",
              "content": f"You are a concise assistant evaluating the output of another LLM.  The original prompt was << {original_prompt} >>.\n\nComment on the quality of response, any factual errors, whether the response was unnecessarily verbose or repetitive, and whether any unwarranted assumptions were made in answering the prompt.",
          },
          {
              "role": "user",
              "content": original_response,
          },
      ],
      response_format=ResponseSchema,
      max_tokens=2048,
  )
  print(completion.usage)
  return completion.choices[0].message.parsed, parse_usage(completion.usage)

COSTS = {
  "gpt-4o-mini": {"input": .15, "output": .6},
  "gpt-4o": {"input": 2.5, "output": 10},
}

def parse_usage(usage, model="gpt-4o-mini"):
  cost = estimate_cost(usage, model)
  return {"tokens_in": usage.prompt_tokens, "tokens_out": usage.completion_tokens, "cost": cost}

def estimate_cost(usage, model="gpt-4o-mini"):
  cost = 0
  cost += usage.prompt_tokens * (COSTS[model]["input"] / 1000000)
  cost += usage.completion_tokens * (COSTS[model]["output"] / 1000000)
  return cost
