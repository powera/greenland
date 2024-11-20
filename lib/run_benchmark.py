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
          sentence_list.append({"sentence": s, "word": word})

  results = []
  for x in sentence_list:
    prompt = f"""
What is the incorrectly-spelled word in this sentence: {x["sentence"]}

When responding, give the incorrect spelling, followed by a hyphen, followed by the correct spelling."""

    response, _ = ollama_client.generate_chat(prompt, model)
    print(response)
