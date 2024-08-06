#!/usr/bin/python3

""" Anthropic client.  Sample code from their documentation. """

from anthropic import Anthropic

TEST_MODEL = "claude-3-haiku-20240307"
PROD_MODEL = "claude-3-5-sonnet-20240620"

def _load_key():
  with open("./keys/anthropic.key") as f:
    api_key = f.read().strip()
  return api_key

client = Anthropic(
    # This is the default and can be omitted
    api_key=_load_key())

def generate_text(prompt, entry):
  message = client.messages.create(
      max_tokens=1536,
      system="You are a concise assistant.  Answer the following question about the user-provided text: " + prompt,
      messages=[
          {
              "role": "user",
              "content": entry,
          },
      ],
      model="claude-3-haiku-20240307",
  )
  print(message.usage)
  print(f"Estimated cost: {estimate_cost(message.usage)}")
  return message.content[0].text


def estimate_cost(usage):
  cost = 0
  cost += usage.input_tokens * (0.25 / 1000000)
  cost += usage.output_tokens * (1.25 / 1000000)
  return cost
