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
  return completion.choices[0].message.content


def create_summary(input_file):
  with open(input_file) as f:
    user_message = f.read()
  model = TEST_MODEL
  encoder = tiktoken.get_encoding("cl100k_base")
  input_length = len(encoder.encode(user_message))
  if input_length > 12000:
    raise Exception("Input data too long")
  completion = client.chat.completions.create(
      model=model,
      messages=[
          {
              "role": "system",
              "content": "Summarize the following text."
          },
          {
              "role": "user",
              "content": user_message
          },
      ],
      presence_penalty=0.25,  # scale is -2 to 2
      max_tokens=512,
      temperature=0.15,  # scale is 0 to 2
      logprobs=True,
      top_logprobs=3,
  )
  print(completion)
  return completion


def answer_question(user_message, model=TEST_MODEL):
  completion = client.chat.completions.create(
      model=model,
      messages=[
          {
              "role": "system",
              "content": "Answer the following question."
          },
          {
              "role": "user",
              "content": user_message
          },
      ],
      presence_penalty=0.25,  # scale is -2 to 2
      max_tokens=512,
      temperature=0.15,  # scale is 0 to 2
  )
  print(completion)
  return completion


def mapreduce():
  # some constants to move to fnsig later
  file_list = []
  results_list = []

  first_system_prompt = """For the email message provided, give a complete list of the literary and cultural references made, along with a brief description suitable for a reader unfamiliar with the allusion or reference. """

  for fn in file_list:
    completion = client.chat.completions.create(
        model=TEST_MODEL,
        messages=[
            {
                "role": "system",
                "content": first_system_prompt
            },
            {
                "role": "user",
                "content": load_email(fn)
            },
        ],
        presence_penalty=0.25,  # scale is -2 to 2
        max_tokens=4096,
        temperature=0.10,  # scale is 0 to 2
    )
    results_list.append(completion)
    with open(os.path.join("/home/powera/tmp", fn.replace("/", "_")),
              "w") as f:
      f.write(json.dumps(completion.choices[0].message.content, indent=2))

  return results_list
