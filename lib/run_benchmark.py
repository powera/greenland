#!/usr/bin/python3

""" Runs a benchmark against a model. """

import json
import os

import benchmarks.datastore
from clients import ollama_client
import lib.score_table


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

def update_scoretable(model, benchmark, metric):
  lib.score_table.generate_run_detail(model, benchmark, metric)

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
  update_scoretable(model, "0015_spell_check", "correct")


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

  update_scoretable(model, "0020_definitions", "correct")

def run_0030_analyze_paragraph(model):
    """
    Runs the paragraph analysis benchmark against a specified model.
    
    This benchmark presents the model with paragraphs (often fables) followed by
    multiple choice questions. The model must analyze the text and select the
    correct answer from the provided choices.
    
    Args:
        model (str): Model identifier string (e.g., "gemma2:7b:Q4_K_M")
        
    The function executes these steps:
    1. Loads benchmark questions from the database
    2. For each question, generates a structured JSON response
    3. Validates the response against expected format
    4. Scores the response against the correct answer
    5. Logs detailed results and performance metrics
    6. Saves the run results to the database
    """
    # Strip quantization suffix for Ollama compatibility
    ollama_model = ":".join(model.split(":")[:-1])
    
    # Define expected response format
    response_schema = {
        "type": "object",
        "properties": {
            "commentary": {"type": "string"},
            "answer": {"type": "string", "minLength": 1, "maxLength": 1}
        },
        "required": ["commentary", "answer"]
    }
    
    # Load questions and warm up model
    sentence_list = load_benchmark_questions("0030_analyze_paragraph")
    ollama_client.warm_model(ollama_model)
    
    # Initialize results tracking
    run_details = {
        "correct": [],  # Tracks completely correct responses
    }
    
    # Process each question
    for question_row in sentence_list:
        question_json = json.loads(question_row["question_info_json"])
        question_id = question_row["question_id"]
       
        clean_query = question_json["query"]  # TODO: clean query
        # Construct prompt with clear instructions
        prompt = f"""
Analyze this passage and question carefully: {clean_query}

Respond using JSON with these fields:
- "commentary": Your analysis of why you chose this answer
- "answer": The single letter (A-D) representing your chosen answer

The response should be valid JSON with no additional text or punctuation."""

        # Generate and validate response
        response_unparsed, perf = ollama_client.generate_chat(
            prompt, 
            ollama_model, 
            json_schema=response_schema,
            structured_json=True
        )
        
        try:
            # Attempt to parse response
            response = json.loads(response_unparsed)
            
            # Check if answer matches the correct choice
            correct_letter = question_json["choices"][question_json["gold"]]
            is_correct = (response.get("answer", "").upper() == correct_letter)
            
            # Log the result with debug info for incorrect answers
            debug_info = {
                "response": response,
                "correct_answer": correct_letter,
                "question": clean_query
            }
            
            log_result(
                run_details["correct"],
                question_id,
                is_correct,
                eval_msec=perf["total_msec"],
                debug_json=json.dumps(debug_info) if debug_info else None
            )
            
        except json.decoder.JSONDecodeError:
            # Log invalid JSON responses
            log_result(
                run_details["correct"],
                question_id,
                0,  # Score of 0 for invalid format
                eval_msec=perf["total_msec"],
                debug_json=response_unparsed
            )
    
    # Calculate summary statistics
    total_questions = len(sentence_list)
    correct_answers = sum(x["score"] for x in run_details["correct"])
    
    # Print detailed results summary
    print(f"""
RESULTS for {model} on 0030_analyze_paragraph:
Correct answers: {correct_answers}/{total_questions} ({correct_answers/total_questions*100:.1f}%)
""")

    # Save results to database
    session = benchmarks.datastore.create_dev_session()
    success, msg = benchmarks.datastore.insert_run(
        session,
        model,
        "0030_analyze_paragraph",
        "correct_answer",
        correct_answers,
        run_details=run_details["correct"]
    )
    
    update_scoretable(model, "0030_analysis_paragraph", "correct")
    if not success:
        print(f"Error saving results: {msg}")
    
    return correct_answers, total_questions


def run_0035_simple_haystack(model):
    # The model string includes a quantization.
    ollama_model = ":".join(model.split(":")[:-1])
    question_list = load_benchmark_questions("0035_simple_haystack")
    ollama_client.warm_model(ollama_model)

    run_details = {"correct": []}

    br = "\\n"
    for x in question_list:
        question_json = json.loads(x["question_info_json"])
        sentences = question_json["sentences"]

        # Randomly select a sentence to query
        import random
        query_sentence = random.choice(sentences)

        # Create the prompt
        prompt = f"""
Given the following sentences:
{''.join(f'{i+1}. {s}{{br}}' for i, s in enumerate(sentences))}

What is the subject for the sentence where the location is {{location}}?

Respond in JSON.
"""

        TODO: fix this section.
        response, perf = ollama_client.generate_chat(prompt, ollama_model, brief=True)
        is_correct = response["subject"] == correct["subject"] 
        
        log_result(
            run_details["correct"],
            x["question_id"],
            is_correct,
            eval_msec=perf["total_msec"],
            debug_json=response,
        )

    num_correct = sum(x["score"] for x in run_details["correct"])
    total_questions = len(run_details["correct"])
    
    print(f"""
RESULTS 0035_simple_haystack
{num_correct}/{total_questions} responses were correct.
""")

    session = benchmarks.datastore.create_dev_session()
    success, msg = benchmarks.datastore.insert_run(
        session, model, "0035_simple_haystack", "correct", 
        num_correct, run_details=run_details["correct"])
    if not success:
        print(msg)
    update_scoretable(model, "0035_simple_haystack", "correct")


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
  update_scoretable(model, "0040_general_knowledge", "correct")
