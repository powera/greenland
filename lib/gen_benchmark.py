#!/usr/bin/python3

""" Generates benchmark questions.  By LLMs, for LLMs. """

import json
import os
import random

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


def gen_0020_question(model="gemma2:9b"):
  words = []
  with open("benchmarks/0020_definitions/wordlist.txt") as f:
    for line in f:
      words.append(line.strip().lower())
  choices = random.sample(words, 10)
  correct = choices[0]  # We alpha-sort the choices later

  prompt = f"""Write a one-sentence definition of the word f{correct}.

Do not use the word f{correct} in the response; just provide the definition.

Respond in JSON, with the definition in "definition" and an (optional) explanation in "explanation"."""
  response_schema = {
      "type": "object",
      "properties": {
        "definition": {"type": "string"},
        "explanation": {"type": "string"},
      },
      "required": ["sentence"]
  }
  response_unparsed, _ = ollama_client.generate_chat(prompt, model, json_schema=response_schema)
  response = json.loads(response_unparsed)
  definition = response["definition"]

  # TODO: Validate definition.

  choices.sort()
  question = f"""Which of the following ten words has this definition: {definition}

Just give the single correct word, do not give a long explanation.

The choices are: {" ".join(choices)}"""
  return {"question": question, "correct": correct, "choices": choices}


def load_0020_definitions_to_sqlite():
  import benchmarks.datastore
  session = benchmarks.datastore.create_dev_session()
  for idx in range(100):
    question = gen_0020_question()
    benchmarks.datastore.insert_question(
        session, f"0020:{question['correct']}:{idx}",
        "0020_definitions",
        json.dumps(question))


def load_0030_analyze_paragraph_to_sqlite():
  import benchmarks.datastore

  DIR = "benchmarks/0030_analyze_paragraph"
  filename = "bigbench_understanding_fables.jsonl"

  sentence_list = []
  with open(os.path.join(DIR, filename)) as f:
    for line in f:
      sentence_list.append(json.loads(line))

  session = benchmarks.datastore.create_dev_session()
  idx = 0
  for sentence in sentence_list[2::7]:
    idx += 1
    if sentence["query"].endswith("\nAnswer: "):  # clean trailing "Answer: "
      sentence["query"] = sentence["query"][:-9]
    benchmarks.datastore.insert_question(
        session, f"0030:fable:{idx}",
        "0030_analyze_paragraph",
        json.dumps(sentence))
    if idx >= 10:
      break



def gen_0035_simple_haystack_sentence(name, action, location):
    prompt = f"""Write a simple sentence with the following elements:
    - Name: {name}
    - Action: {action}
    - Location: {location}

    Only reply with the single sentence, do not include any other text or punctuation."""

    response, _ = ollama_client.generate_chat(prompt, "gemma2:9b")
    return response.strip()

def gen_0035_simple_haystack_question(names, actions, locations):
    """Generates a question consisting of 6 simple sentences."""
    sentences = []
    for _ in range(6):
        """Generates a simple sentence."""
        # TODO: generate the six tuples such that there cannot be repetition.
        name = random.choice(names)
        action = random.choice(actions)
        location = random.choice(locations)
        sentences.append(gen_0035_simple_haystack_sentence(name, action, location))
    correct = {"sentence": sentences[-1], "name": name, "action": action, "location": location}  # CLEANUP
    return {"sentences": sentences, "correct": correct}

def load_0035_simple_haystack_to_sqlite():
    import benchmarks.datastore

    names = []
    with open("benchmarks/0035_simple_haystack/names.txt") as f:
        for line in f:
            names.append(line.strip())

    actions = []
    with open("benchmarks/0035_simple_haystack/actions.txt") as f:
        for line in f:
            actions.append(line.strip())

    locations = []
    with open("benchmarks/0035_simple_haystack/locations.txt") as f:
        for line in f:
            locations.append(line.strip())

    session = benchmarks.datastore.create_dev_session()
    for idx in range(10):
        question = gen_0035_simple_haystack_question(names, actions, locations)
        benchmarks.datastore.insert_question(
            session, f"0035:haystack:{idx}",
            "0035_simple_haystack",
            json.dumps(question))


def load_0040_general_knowledge_to_sqlite():
  import benchmarks.datastore

  DIR = "benchmarks/0040_general_knowledge"

  sentence_list = []
  files = os.listdir(DIR)
  files.sort()
  for filename in files:
    if filename.endswith(".jsonl"):
      with open(os.path.join(DIR, filename)) as f:
        for line in f:
          sentence_list.append(json.loads(line))

  session = benchmarks.datastore.create_dev_session()
  idx = 0
  for sentence in sentence_list[::17]:  # Only load 100 for now
    idx += 1
    benchmarks.datastore.insert_question(
        session, f"0040:{sentence['category']}:{idx}",
        "0040_general_knowledge",
        json.dumps(sentence))
    if idx >= 100:
      break
