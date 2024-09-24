#!/usr/bin/python3

""" Tools to run a barrage of models/prompts via script. """

import asyncio
import json
import os
import re

import local_client, ollama_client, openai_client, anthropic_client

import util.flesch_kincaid as fk

OLLAMA_MODELS = [
    "llama3:latest",  # old, 4.7G
    "qwen:4b",      # old, 2.3G
    "smollm:1.7b",  # 990M
    "phi3.5:3.8b",    # 2.2G
    "llama3.1:8b",  # 4.7G
    "qwen2.5:7b",   # 4.7G
    "gemma2:9b",    # 5.4G
    "mistral-nemo:12b",  # 7.1G
]


def multi_cross_run_to_json(slug_dict):
  # Runs 10 models for the prompt, and outputs to an HTML page with a slug.
  result = {}
  for slug in slug_dict:
    result[slug] = {}
    result[slug]["prompt"] = slug_dict[slug]
    result[slug]["results"] = []
  for model in OLLAMA_MODELS:
    for slug in slug_dict:
      response, usage = ollama_client.generate_text(slug_dict[slug], model)
      result[slug]["results"].append({"model": model, "response": response, "usage": usage})

  for slug in slug_dict:
    with open(f"cache/{slug}.json", "w") as f:
      f.write(json.dumps(result[slug], indent=2, sort_keys=True))
    json_to_html(f"cache/{slug}.json", f"output/{slug}.html")
  return result


def add_critique(slug):
  with open(f"cache/{slug}.json", "r") as f:
    doc = json.loads(f.read())
  for k in doc["results"]:
    if "critique" not in k:
      critique_tuple, _ = openai_client.evaluate_response(doc["prompt"], k["response"])
      k["critique"] = critique_tuple.dict()
  with open(f"cache/{slug}.json", "w") as f:
    f.write(json.dumps(doc, indent=2, sort_keys=True))
  slug_json_to_html(slug)


def slug_json_to_html(slug):
    json_to_html(f"cache/{slug}.json", f"output/{slug}.html")

def json_to_html(json_file, output_html):
    # Load JSON data
    with open(json_file, 'r') as file:
        data = json.load(file)

    # HTML header
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

    line_break = "\n"  # for f-string

    # Add each result in a collapsible div
    for idx, result in enumerate(data['results']):
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

    # Add JavaScript for collapsible functionality
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
    '''

    # HTML footer
    html_content += '''
    </body>
    </html>
    '''

    # Write the HTML content to file
    with open(output_html, 'w') as file:
        file.write(html_content)

