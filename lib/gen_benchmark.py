#!/usr/bin/python3

""" Generates benchmark questions.  By LLMs, for LLMs. """

import json

import ollama_client

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
