#!/usr/bin/python3

""" Runs a benchmark against a model. """

import json
import os

import benchmarks.datastore
from clients import ollama_client


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

  run_details = {"correct_word": [], "proper_format": [], "correct_answer": []}

  for row in sentence_list:
    question_info = json.loads(row["question_info_json"])
    prompt = f"""
What is the incorrectly-spelled word in this sentence: {question_info["sentence"]}

When responding, give the incorrect spelling, followed by a space, hyphen, space, and the correct spelling.

Two example response:
  bigg - big
  chainge - change
"""

    response, perf = ollama_client.generate_chat(prompt, ollama_model)
    question_id = row["question_id"]

    log_result(run_details["correct_word"],
               question_id,
               question_info["correct"] in response,
               eval_msec=perf["total_msec"])

    response_parts = response.split()
    is_formatted = len(response_parts) == 3 and response_parts[1] == "-"
    log_result(run_details["proper_format"],
               question_id,
               is_formatted,
               eval_msec=perf["total_msec"])

    is_correct = False
    if is_formatted:
      response_wrong = response.split()[0]
      response_right = response.split()[2]
      is_correct = (question_info["incorrect"] == response_wrong and 
                    question_info["correct"] == response_right)
    log_result(run_details["correct_answer"],
               question_id,
               is_correct,
               eval_msec=perf["total_msec"])

  # Sum of results
  has_correct_word = sum(x["score"] for x in run_details["correct_word"])
  has_proper_format = sum(x["score"] for x in run_details["proper_format"])
  has_correct_answer = sum(x["score"] for x in run_details["correct_answer"])
  total_questions = len(run_details["correct_answer"])

  print(f"""
RESULTS:
{has_correct_word}/{total_questions} responses included the correct word.
{has_proper_format}/{total_questions} responses were correctly formatted.
{has_correct_answer}/{total_questions} responses were completely correct.
        """)

  session = benchmarks.datastore.create_dev_session()
  success, msg = benchmarks.datastore.insert_run(session, model, "0015_spell_check", "correct_word", has_correct_word, run_details=run_details["correct_word"])
  if not success:
    print(msg)
  benchmarks.datastore.insert_run(session, model, "0015_spell_check", "proper_format", has_proper_format, run_details=run_details["proper_format"])
  benchmarks.datastore.insert_run(session, model, "0015_spell_check", "complete", has_correct_answer, run_details=run_details["correct_answer"])


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
