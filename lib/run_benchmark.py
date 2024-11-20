#!/usr/bin/python3

""" Runs a benchmark against a model. """

import json
import os

import ollama_client

def run_0015_spell_check(model):
  DIR = "benchmarks/0015_spell_check"

  sentence_list = []
  for filename in os.listdir(DIR):
    if filename.endswith(".json"):
      word = filename[:-5]
      with open(os.path.join(DIR, filename)) as f:
        sentences_raw = json.load(f)
        for s in sentences_raw:
          sentence_list.append(s)

      results = []

  total_questions = 0
  has_correct_word = 0
  has_proper_format = 0
  correct_answers = 0
  for x in sentence_list:
    prompt = f"""
What is the incorrectly-spelled word in this sentence: {x["sentence"]}

When responding, give the incorrect spelling, followed by a space, hyphen, space, and the correct spelling.

Two example response:
  bigg - big
  chainge - change
"""

    response, _ = ollama_client.generate_chat(prompt, model)
    total_questions += 1
    if x["correct"] in response:
      has_correct_word += 1
    response_parts = response.split()
    if len(response_parts) == 3 and response_parts[1] == "-":
      has_proper_format += 1
      response_wrong = response.split()[0]
      response_right = response.split()[2]
      if x["incorrect"] == response_wrong and x["correct"] == response_right:
        correct_answers += 1
        continue

  print(f"""
RESULTS:
{has_correct_word}/{total_questions} responses included the correct word.
{has_proper_format}/{total_questions} responses were correctly formatted.
{correct_answers}/{total_questions} responses were completely correct.
        """)
