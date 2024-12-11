#!/usr/bin/python3

""" Runs a benchmark against a model. """

import json
import os

import benchmarks.datastore
from clients import ollama_client


def get_all_model_codenames():
  session = benchmarks.datastore.create_dev_session() 
  models = benchmarks.datastore.list_all_models(session)
  return [x["codename"] for x in models]

def get_all_benchmark_pairs():
  session = benchmarks.datastore.create_dev_session() 
  benchmark_info = benchmarks.datastore.list_all_benchmarks(session)
  return [(x["codename"], x["metric"]) for x in benchmark_info]

def log_result(result_array, question_id, score, eval_msec, debug_json=None):
  """Populates result_array with the information for run_details."""
  result_array.append({"question_id": question_id, "score": score, "eval_msec": eval_msec, "debug_json": debug_json})


def load_benchmark_questions(benchmark):
  session = benchmarks.datastore.create_dev_session() 
  return benchmarks.datastore.load_all_questions_for_benchmark(session, benchmark)


def run_0015_spell_check(model):
  # The model string includes a quantization.
  ollama_model = ":".join(model.split(":")[:-1])
  sentence_list = load_benchmark_questions("0015_spell_check")
  ollama_client.warm_model(ollama_model)

  run_details = {"correct_word": [], "incorrect_word": [], "correct_answer": []}
  response_schema = {
      "type": "object",
      "properties": {
        "incorrect": {"type": "string"},
        "correct": {"type": "string"},
      },
      "required": ["incorrect", "correct"],
  }

  for row in sentence_list:
    question_info = json.loads(row["question_info_json"])
    prompt = f"""
What is the incorrectly-spelled word in this sentence: {question_info["sentence"]}

Respond in JSON, with keys of "incorrect" for the verbatim misspelled word, and "correct" for the correct spelling.
"""

    response_unparsed, perf = ollama_client.generate_chat(prompt, ollama_model, json_schema=response_schema)
    question_id = row["question_id"]

    response = json.loads(response_unparsed)
    log_result(run_details["incorrect_word"],
               question_id,
               question_info["incorrect"] == response["incorrect"],
               eval_msec=perf["total_msec"],
               debug_json=response_unparsed)
    log_result(run_details["correct_word"],
               question_id,
               question_info["correct"] == response["correct"],
               eval_msec=perf["total_msec"],
               debug_json=response_unparsed)

    is_correct = (
        question_info["incorrect"] == response["incorrect"] and
        question_info["correct"] == response["correct"])
    log_result(run_details["correct_answer"],
               question_id,
               is_correct,
               eval_msec=perf["total_msec"],
               debug_json=response_unparsed)

  # Sum of results
  has_correct_word = sum(x["score"] for x in run_details["correct_word"])
  has_incorrect_word = sum(x["score"] for x in run_details["incorrect_word"])
  has_correct_answer = sum(x["score"] for x in run_details["correct_answer"])
  total_questions = len(run_details["correct_answer"])

  print(f"""
0015 RESULTS for {model}:
{has_correct_word}/{total_questions} responses included the correct word.
{has_incorrect_word}/{total_questions} responses included the incorrect word.
{has_correct_answer}/{total_questions} responses were completely correct.
        """)

  session = benchmarks.datastore.create_dev_session()
  success, msg = benchmarks.datastore.insert_run(session, model, "0015_spell_check", "correct_word", has_correct_word, run_details=run_details["correct_word"])
  if not success:
    print(msg)

  success, msg = benchmarks.datastore.insert_run(session, model, "0015_spell_check", "incorrect_word", has_incorrect_word, run_details=run_details["incorrect_word"])
  if not success:
    print(msg)

  success, msg = benchmarks.datastore.insert_run(session, model, "0015_spell_check", "complete", has_correct_answer, run_details=run_details["correct_answer"])
  if not success:
    print(msg)


def run_0020_definitions(model):
  # The model string includes a quantization.
  ollama_model = ":".join(model.split(":")[:-1])
  question_list = load_benchmark_questions("0020_definitions")
  ollama_client.warm_model(ollama_model)

  run_details = {"correct": []}

  for x in question_list:
    question_json = json.loads(x["question_info_json"])
    response, perf = ollama_client.generate_chat(question_json["question"], ollama_model, brief=True)
    is_correct = (response.strip().strip(".").lower() == question_json["correct"])
    log_result(run_details["correct"],
               x["question_id"],
               is_correct,
               eval_msec=perf["total_msec"],
               debug_json=(None if is_correct else response)
               )

  has_correct_answer = sum(x["score"] for x in run_details["correct"])
  total_questions = len(run_details["correct"])
  print(f"""
RESULTS 0020_definitions
{has_correct_answer}/{total_questions} responses contained the correct answer.
""")

  session = benchmarks.datastore.create_dev_session()
  success, msg = benchmarks.datastore.insert_run(session, model, "0020_definitions", "correct", has_correct_answer, run_details=run_details["correct"])
  if not success:
    print(msg)


def run_0030_analyze_paragraph(model):
  # The model string includes a quantization.
  ollama_model = ":".join(model.split(":")[:-1])
  sentence_list = load_benchmark_questions("0030_analyze_paragraph")
  ollama_client.warm_model(ollama_model)

  run_details = {"json_format": [], "correct_answer": []}
  for x in sentence_list:
    question_json = json.loads(x["question_info_json"])
    # These currently are tuned for completion.  TODO: clean dataset
    if question_json["query"].endswith("\nAnswer: "):
      question_json["query"] = question_json["query"][:-9]

    prompt = f"""
What is the answer to this question: {question_json["query"]}

Respond using JSON; give commentary in a field called "commentary", followed by the letter of the correct answer as "answer".  Do not include any chat or punctuation other than the JSON.
"""

    response_unparsed, perf = ollama_client.generate_chat(prompt, ollama_model, structured_json=True)
    try:
      response = json.loads(response_unparsed)
      is_correct = (response.get("answer", "") ==
                    question_json["choices"][question_json["gold"]])
    except json.decoder.JSONDecodeError:
      is_correct = False
      response_unparsed = {"response": response_unparsed}

    log_result(run_details["correct_answer"],
               x["question_id"],
               is_correct,
               eval_msec=perf["total_msec"],
               debug_json=(None if is_correct else response_unparsed)
               )

  has_correct_answer = sum(x["score"] for x in run_details["correct_answer"])
  total_questions = len(run_details["correct_answer"])
  print(f"""
RESULTS 0030_analyze_paragraph
{has_correct_answer}/{total_questions} responses contained the correct answer.
""")

  session = benchmarks.datastore.create_dev_session()
  success, msg = benchmarks.datastore.insert_run(session, model, "0030_analyze_paragraph", "correct_answer", has_correct_answer, run_details=run_details["correct_answer"])
  if not success:
    print(msg)


def run_0040_general_knowledge(model):
  # The model string includes a quantization.
  ollama_model = ":".join(model.split(":")[:-1])
  sentence_list = load_benchmark_questions("0040_general_knowledge")
  ollama_client.warm_model(ollama_model)

  total_questions = 0
  correct_answers = 0

  for x in sentence_list:
    question_json = json.loads(x["question_info_json"])
    prompt = f"""
What is the answer to this question: {question_json["context"]}

When responding, give only the correct answer; do not form it into a sentence.
"""

    response, perf = ollama_client.generate_chat(prompt, ollama_model)
    total_questions += 1
    if question_json["continuation"] in response:
      correct_answers += 1
    else:
      print(f"""WRONG! Question {question_json["context"]}, Correct Answer {question_json["continuation"]}, Response {response}""")

  print(f"""
RESULTS 0040_general_knowledge
{correct_answers}/{total_questions} responses contained the correct answer.
""")
