#!/usr/bin/python3

"""Tools to run a barrage of models/prompts via script."""

import json
import os
import re
from typing import Dict, List

from clients import ollama_client, openai_client
import constants
import lib.validation

# Directory aliases for easy updating if paths change in constants.py
CACHE_DIR = os.path.join(constants.DATA_DIR, "responses")
OUTPUT_DIR = constants.OUTPUT_DIR

# Model groups
SMALL_OLLAMA_MODELS = [
    "llama3:latest",  # old, 4.7G
    "qwen:4b",        # old, 2.3G
    "smollm:1.7b",    # 990M
    "smollm2:360m",   # 725MB,
]

OLLAMA_MODELS = [
    "phi3.5:3.8b",     # 2.2G
    "llama3.1:8b",     # 4.7G
    "qwen2.5:7b",      # 4.7G
    "gemma2:9b",       # 5.4G
    "mistral-nemo:12b", # 7.1G,
]

def multi_cross_run_to_json(slug_dict: Dict[str, str]) -> Dict:
    """Run multiple prompts across all models, saving results by slug."""
    # Initialize results structure
    result = {
        slug: {
            "prompt": prompt,
            "results": []
        }
        for slug, prompt in slug_dict.items()
    }

    # Run each model against all prompts before moving to next model
    for model in OLLAMA_MODELS:
        for slug, prompt in slug_dict.items():
            try:
                # Use new ollama_client interface
                response, _, usage = ollama_client.generate_chat(prompt, model)
                result[slug]["results"].append({
                    "model": model,
                    "response": response,
                    "usage": usage
                })
            except Exception as e:
                print(f"Error with model {model} on {slug}: {e}")

    # Save results and generate HTML
    os.makedirs(CACHE_DIR, exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    for slug in slug_dict:
        cache_file = os.path.join(CACHE_DIR, f"{slug}.json")
        output_file = os.path.join(OUTPUT_DIR, f"{slug}.html")
        
        with open(cache_file, "w") as f:
            json.dump(result[slug], f, indent=2, sort_keys=True)
        json_to_html(cache_file, output_file)
        
    return result

def add_model_for_slug(slug: str, model: str = "gpt-4o-mini", persona: str = "") -> Dict:
    """Add results for a new model to existing results for a slug."""
    cache_file = os.path.join(CACHE_DIR, f"{slug}.json")
    
    with open(cache_file, "r") as f:
        result = json.load(f)
        
    prompt = result["prompt"]
    existing_models = [x["model"] for x in result["results"]]
    
    if model == "gpt-4o-mini":
        if persona:
            response, usage = openai_client.answer_question(prompt, persona=persona)
            model_name = f"gpt-4o-mini/{persona}"
        else:
            if model not in existing_models:
                response, usage = openai_client.answer_question(prompt)
                model_name = "gpt-4o-mini"
            else:
                return add_critique(slug)
    elif model in OLLAMA_MODELS:
        response, _, usage = ollama_client.generate_chat(prompt, model)
        model_name = model
    else:
        raise ValueError(f"Unknown model: {model}")

    result["results"].append({
        "model": model_name,
        "response": response,
        "usage": usage
    })

    with open(cache_file, "w") as f:
        json.dump(result, f, indent=2, sort_keys=True)

    return add_critique(slug)

def add_critique(slug: str) -> Dict:
    """Add critique information to results for a slug."""
    cache_file = os.path.join(CACHE_DIR, f"{slug}.json")
    
    with open(cache_file, "r") as f:
        doc = json.load(f)
        
    for result in doc["results"]:
        if "critique" not in result:
            evaluation, _ = lib.validation.evaluate_response(doc["prompt"], result["response"])
            result["critique"] = evaluation.dict()
            result["critique"]["overall_quality"] = str(result["critique"]["overall_quality"])
            
    with open(cache_file, "w") as f:
        json.dump(doc, f, indent=2, sort_keys=True)
        
    slug_json_to_html(slug)
    return doc

def slug_json_to_html(slug: str) -> None:
    """Convert JSON results for a slug to HTML."""
    cache_file = os.path.join(CACHE_DIR, f"{slug}.json")
    output_file = os.path.join(OUTPUT_DIR, f"{slug}.html")
    json_to_html(cache_file, output_file)

def json_to_html(json_file: str, output_html: str) -> None:
    """Convert JSON results file to HTML report."""
    with open(json_file, 'r') as f:
        data = json.load(f)

    # HTML template [keeping existing template exactly as is]
    html_content = '''
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>LLM Outputs</title>
        <style>
            .collapsible {
                background-color: #f1f1f1;
                color: #444;
                cursor: pointer;
                padding: 10px;
                width: 100%;
                border: none;
                text-align: left;
                outline: none;
                font-size: 14px;
            }


            .response-critique {
                display: flex;
                justify-content: space-between;
            }


            .response-column {
                width: 60%; /* 60% width for response */
            }

            .critique-column {
                width: 40%; /* 40% width for critique */
                font-size: 12px;
            }
            .active, .collapsible:hover {
                background-color: #ccc;
            }

            .content {
                padding: 0 18px;
                display: none;
                overflow: hidden;
                background-color: #f9f9f9;
                margin-bottom: 10px;
            }
        </style>
    </head>
    <body>
    '''

    # Add prompt
    html_content += f'<h2>Prompt: {data["prompt"]}</h2>\n'

    # Add each result in a collapsible div
    for result in data['results']:
        response = result.get('response', '')
        response = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', response)
        response = response.replace('\n', '<br>')

        critique = result.get('critique', '')
        if isinstance(critique, dict):
            critique = f'''
<b>Was this a refusal?</b> {critique["is_refusal"]}<br />
<b>What was the overall quality?</b> {critique["overall_quality"]}<br />
<b>Were there factual errors?</b> {critique["factual_errors"]}<br />
<b>Was there excessive repetition?</b> {critique["repetition"]}<br />
<b>Was there excessive verbosity?</b> {critique["verbosity"]}<br />
<b>Were there unwarranted assumptions?</b> {critique["unwarranted_assumptions"]}'''
        critique = critique.replace('\n', '<br>')

        html_content += f'''
        <button class="collapsible">Model: {result['model']} (Cost: {result['usage']['cost']:.6f}, Response Tokens: {result['usage']['tokens_out']})</button>
        <div class="content">
            <div class="response-critique">
                <div class="column response-column">
                    <div class="column-header">Response:</div>
                    <p>{response}</p>
                </div>
                <div class="column critique-column">
                    <div class="column-header">Critique:</div>
                    <p>{critique}</p>
                </div>
            </div>
        </div>
        '''

    # Add JavaScript [keeping existing exactly as is]
    html_content += '''
    <script>
        var coll = document.getElementsByClassName("collapsible");
        for (var i = 0; i < coll.length; i++) {
            coll[i].addEventListener("click", function() {
                this.classList.toggle("active");
                var content = this.nextElementSibling;
                if (content.style.display === "block") {
                    content.style.display = "none";
                } else {
                    content.style.display = "block";
                }
            });
        }
    </script>
    </body>
    </html>
    '''

    with open(output_html, 'w') as f:
        f.write(html_content)
