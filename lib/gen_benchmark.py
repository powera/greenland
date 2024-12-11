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


def validate_definition(definition: str, expected_word: str, 
                       validator_models=("granite3-dense:8b:Q4_K_M", "qwen2.5:7b:Q4_K_M")):
    """
    Validates that a generated definition actually defines the expected word by checking 
    with two validator models.
    
    Args:
        definition: The definition to validate
        expected_word: The word that should be defined
        validator_models: Tuple of model names to use for validation
        
    Returns:
        dict with validation results and metrics
    """
    validation_results = []
    
    # Schema for validator responses
    response_schema = {
        "type": "object",
        "properties": {
            "matches_word": {"type": "boolean"},
            "likely_word": {"type": "string"},
            "confidence": {"type": "integer", "minimum": 0, "maximum": 100},
            "explanation": {"type": "string"}
        },
        "required": ["matches_word", "likely_word"]
    }
    
    for model in validator_models:
        # Strip quantization suffix for Ollama
        ollama_model = ":".join(model.split(":")[:-1])
        
        prompt = f"""Given this definition: "{definition}"

Does this definition accurately describe the word "{expected_word}"?

Respond in JSON format with these fields:
- matches_word: boolean indicating if the definition matches the word
- likely_word: what word you think this actually defines (can be same as expected if it matches)
- confidence: 0-100 score of your confidence in this assessment
- explanation: brief reason for your decision

Only respond with valid JSON, no additional text."""

        response_unparsed, _ = ollama_client.generate_chat(
            prompt, 
            ollama_model,
            json_schema=response_schema,
            structured_json=True
        )
        
        try:
            result = json.loads(response_unparsed)
            validation_results.append({
                "validator_model": model,
                **result
            })
        except json.JSONDecodeError:
            # If we get invalid JSON, treat it as a failed validation
            validation_results.append({
                "validator_model": model,
                "matches_word": False,
                "likely_word": "INVALID_RESPONSE",
                "confidence": 0,
                "explanation": "Failed to parse validator response"
            })
    
    # Analyze the validation results
    valid_count = sum(1 for r in validation_results if r["matches_word"])
    avg_confidence = sum(r.get("confidence", 0) for r in validation_results) / len(validation_results)
    
    # Return consolidated results
    return {
        "is_valid": valid_count >= len(validator_models) / 2,  # majority must agree
        "validation_score": avg_confidence,
        "validator_results": validation_results,
        "definition": definition,
        "expected_word": expected_word
    }


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

    choices.sort()
    question = f'Which of the following ten words has this definition: {definition}\n\nJust give the single correct word, do not give a long explanation.\n\nThe choices are: {", ".join(choices)}'
    return {"question": question, "definition": definition, "correct": correct, "choices": choices}


def gen_0020_question_with_validation(model="gemma2:9b"):
    """
    Enhanced version of gen_0020_question that includes definition validation.
    """
    max_attempts = 3
    for attempt in range(max_attempts):
        question = gen_0020_question(model)
        validation = validate_definition(
            question["definition"],
            question["correct"]
        )
        
        if validation["is_valid"]:
            return question
        
        print(f"Attempt {attempt + 1} failed validation:")
        print(json.dumps(validation, indent=2))
    
    raise ValueError(f"Failed to generate valid definition after {max_attempts} attempts")

def load_0020_definitions_to_sqlite():
    import benchmarks.datastore

    session = benchmarks.datastore.create_dev_session()
    for idx in range(100):
        question = gen_0020_question_with_validation()
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
