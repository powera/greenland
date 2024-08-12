#!/usr/bin/python3

import os

from openai import OpenAI

import json
import tiktoken

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
