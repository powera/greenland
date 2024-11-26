#!/usr/bin/python3

""" Runs a benchmark against a model. """

import json
import os

import benchmarks.datastore
from clients import ollama_client


def run_0015_spell_check(model):
  # The model string includes a quantization.
  ollama_model = ":".join(model.split(":")[:-1])
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

    response, perf = ollama_client.generate_chat(prompt, ollama_model)
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

  session = benchmarks.datastore.create_database_and_session(
      "/Users/powera/repo/greenland/schema/benchmarks.db")
  benchmarks.datastore.insert_run(session, model, "0015_spell_check:correct_word", has_correct_word)
  benchmarks.datastore.insert_run(session, model, "0015_spell_check:proper_format", has_proper_format)
  benchmarks.datastore.insert_run(session, model, "0015_spell_check:complete", correct_answers)

def run_0030_analyze_paragraph(model):
  DIR = "benchmarks/0030_analyze_paragraph"

  question_list = []
  filename = "bigbench_understanding_fables.jsonl"
  with open(os.path.join(DIR, filename)) as f:
    for line in f:
      question_list.append(json.loads(line))

  total_questions = 0
  correct_answers = 0

  # for debug
  question_list = question_list[::23]

  for x in question_list:
    # These currently are tuned for completion.  TODO: clean dataset
    if x["query"].endswith("\nAnswer: "):
      x["query"] = x["query"][:-9]

    prompt = f"""
What is the answer to this question: {x["query"]}

Respond using JSON; give commentary in a field called "commentary", followed by the letter of the correct answer as "answer".  Do not include any chat or punctuation other than the JSON.
"""

    response_unparsed, perf = ollama_client.generate_chat(prompt, model, structured_json=True)
    total_questions += 1
    try:
      response = json.loads(response_unparsed)
    except json.decoder.JSONDecodeError:
      print(f"""NOT JSON! Question {x["query"]}, Response {response_unparsed}""")
      continue

    correct = x["choices"][x["gold"]]
    if response.get("answer", "") == correct:
      correct_answers += 1
    else:
      print(f"""WRONG! Question {x["query"]}, Correct Answer {correct}, Response {response}""")

  print(f"""
RESULTS 0030_analyze_paragraph
{correct_answers}/{total_questions} responses contained the correct answer.
""")

def run_0040_general_knowledge(model):
  DIR = "benchmarks/0040_general_knowledge"

  question_list = []
  for filename in os.listdir(DIR):
    if filename.endswith(".jsonl"):
      corpus = filename[:-6]
      with open(os.path.join(DIR, filename)) as f:
        for line in f:
          question_list.append(json.loads(line))

  total_questions = 0
  correct_answers = 0

  # for debug
  question_list = question_list[::23]

  for x in question_list:
    prompt = f"""
What is the answer to this question: {x["context"]}

When responding, give only the correct answer; do not form it into a sentence.
"""

    response, perf = ollama_client.generate_chat(prompt, model)
    total_questions += 1
    if x["continuation"] in response:
      correct_answers += 1
    else:
      print(f"""WRONG! Question {x["context"]}, Correct Answer {x["continuation"]}, Response {response}""")

  print(f"""
RESULTS 0040_general_knowledge
{correct_answers}/{total_questions} responses contained the correct answer.
""")
