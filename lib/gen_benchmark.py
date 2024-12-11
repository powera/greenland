#!/usr/bin/python3

""" Generates benchmark questions."""

import json
import os
import random

from clients import ollama_client

def gen_0015_spell_check_sentence(start_word):
    """Generates 1 sentence that uses start_word but spells it incorrectly."""
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
        sentence = gen_0015_spell_check_sentence(start_word)
        sentences.append({"sentence": sentence, "incorrect": "", "correct": start_word})

    with open(f"benchmarks/0015_spell_check/{start_word}.json", "w") as f:
        json.dump(sentences, f, indent=2)


def load_0015_spell_check_to_sqlite():
    import benchmarks.datastore

    DIR = "benchmarks/0015_spell_check"

    session = benchmarks.datastore.create_dev_session()

    files = os.listdir(DIR)
    files.sort()

    for idx, filename in enumerate(files):
        if filename.endswith(".json"):
            with open(os.path.join(DIR, filename)) as f:
                sentences = json.load(f)
                for sentence in sentences:
                    benchmarks.datastore.insert_question(
                        session,
                        f"0015:{sentence['correct']}:{idx}",
                        "0015_spell_check",
                        json.dumps(sentence),
                    )


def gen_0020_question(model="gemma2:9b"):
    with open("benchmarks/0020_definitions/wordlist.txt") as f:
        words = [line.strip().lower() for line in f]

    choices = random.sample(words, 10)
    correct = choices[0]  # We alpha-sort the choices later

    prompt = f"""Write a one-sentence definition of the word "{correct}".

Do not use the word "{correct}" in the response; just provide the definition.

Respond in JSON, with the definition in "definition" and an (optional) explanation in "explanation"."""

    response_schema = {
        "type": "object",
        "properties": {
            "definition": {"type": "string"},
            "explanation": {"type": "string"},
        },
        "required": ["definition"],
    }

    response_unparsed, _ = ollama_client.generate_chat(
        prompt, model, json_schema=response_schema
    )
    response = json.loads(response_unparsed)
    definition = response["definition"]

    # TODO: Validate definition.

    choices.sort()
    question = f'Which of the following ten words has this definition: {definition}\n\nJust give the single correct word, do not give a long explanation.\n\nThe choices are: {", ".join(choices)}'
    return {"question": question, "correct": correct, "choices": choices}


def load_0020_definitions_to_sqlite():
    import benchmarks.datastore

    session = benchmarks.datastore.create_dev_session()
    for idx in range(100):
        question = gen_0020_question()
        benchmarks.datastore.insert_question(
            session,
            f"0020:{question['correct']}:{idx}",
            "0020_definitions",
            json.dumps(question),
        )


def load_0030_analyze_paragraph_to_sqlite():
    import benchmarks.datastore

    DIR = "benchmarks/0030_analyze_paragraph"
    filename = "bigbench_understanding_fables.jsonl"

    session = benchmarks.datastore.create_dev_session()

    with open(os.path.join(DIR, filename)) as f:
        for idx, line in enumerate(f):
            sentence = json.loads(line)
            if idx % 7 != 2:
                continue
            if sentence["query"].endswith("\nAnswer: "):
                sentence["query"] = sentence["query"][:-9]  # clean trailing "Answer: "
            benchmarks.datastore.insert_question(
                session,
                f"0030:fable:{idx // 7 + 1}",
                "0030_analyze_paragraph",
                json.dumps(sentence),
            )
            if idx // 7 + 1 >= 10:
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
    count = 6
    selected_names = random.sample(names, count)
    selected_actions = random.sample(actions, count)
    selected_locations = random.sample(locations, count)
    for x in range(count):
      sentence = gen_0035_simple_haystack_sentence(selected_names[x], selected_actions[x], selected_locations[x])
      sentences.append(sentence)

    correct = {
        "sentence": sentences[-1],
        "name": selected_names[-1],
        "action": selected_actions[-1],
        "location": selected_locations[-1],
    }
    return {"sentences": sentences, "correct": correct}


def load_0035_simple_haystack_to_sqlite():
    import benchmarks.datastore

    with open("benchmarks/0035_simple_haystack/names.txt") as f:
        names = [line.strip() for line in f]

    with open("benchmarks/0035_simple_haystack/actions.txt") as f:
        actions = [line.strip() for line in f]

    with open("benchmarks/0035_simple_haystack/locations.txt") as f:
        locations = [line.strip() for line in f]

    session = benchmarks.datastore.create_dev_session()
    for idx in range(10):
        question = gen_0035_simple_haystack_question(names, actions, locations)
        benchmarks.datastore.insert_question(
            session,
            f"0035:haystack:{idx}",
            "0035_simple_haystack",
            json.dumps(question),
        )


def load_0040_general_knowledge_to_sqlite():
    import benchmarks.datastore

    DIR = "benchmarks/0040_general_knowledge"

    session = benchmarks.datastore.create_dev_session()

    files = os.listdir(DIR)
    files.sort()

    idx = 0
    for filename in files:
        if filename.endswith(".jsonl"):
            with open(os.path.join(DIR, filename)) as f:
                for line in f:
                    if idx % 17 == 0:
                        sentence = json.loads(line)
                        benchmarks.datastore.insert_question(
                            session,
                            f"0040:{sentence['category']}:{idx // 17 + 1}",
                            "0040_general_knowledge",
                            json.dumps(sentence),
                        )
                    idx += 1
                    if idx // 17 + 1 > 100:
                        break
        if idx // 17 + 1 > 100:
            break
