#!/usr/bin/python3

""" Generates benchmark questions.  By LLMs, for LLMs. """

import json
import os

from clients import ollama_client

def gen_0015_spell_check_sentence(start_word):
  """Generates 1 sentences that use start_word but spell it incorrectly."""
  prompt = f"""
Write a sentence using the word {start_word}, but spelling it incorrectly.

Reply with only the single sentence, do not include additional conversation.

The sentence should be at about an 8th grade reading level."""

  response, _ = ollama_client.generate_chat(prompt, "gemma2:9b")
  return response.strip()


def gen_0015_spell_check(start_word):
  """Generates 10 sentences that use start_word but spell it incorrectly."""
  sentences = []
  for _ in range(10):
    sentences.append(gen_0015_spell_check_sentence(start_word))

  with open(f"benchmarks/0015_spell_check/{start_word}.json", "w") as f:
    json.dump(sentences, f, indent=2)


def load_0015_spell_check_to_sqlite():
  import benchmarks.datastore

  DIR = "benchmarks/0015_spell_check"

  sentence_list = []
  files = os.listdir(DIR)
  files.sort()
  for filename in files:
    if filename.endswith(".json"):
      word = filename[:-5]
      with open(os.path.join(DIR, filename)) as f:
        sentences_raw = json.load(f)
        for s in sentences_raw:
          sentence_list.append(s)

  session = benchmarks.datastore.create_dev_session()
  idx = 0
  for sentence in sentence_list:
    idx += 1
    benchmarks.datastore.insert_question(
        session, f"0015:{sentence['correct']}:{idx}",
        "0015_spell_check",
        json.dumps(sentence))
