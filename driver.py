#!/usr/bin/python3

""" Tools to run a barrage of models/prompts via script. """

import asyncio
import json
import os

import local_client, ollama_client, openai_client, anthropic_client

import util.flesch_kincaid as fk

OLLAMA_MODELS = [
    "smollm:135m",  #  91M
    "smollm:360m",  # 229M
    "qwen2.5:0.5b", # 397M
    "qwen2.5:1.5b", # 986M
    "gemma2:2b",    # 1.6G
    "phi3:3.8b",    # 2.2G
    "llama3.1:8b",  # 4.7G
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
      k["critique"], _ = openai_client.evaluate_response(doc["prompt"], k["response"])
      break
  with open(f"cache/{slug}.json", "w") as f:
    f.write(json.dumps(doc, indent=2, sort_keys=True))


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
        <title>JSON to HTML</title>
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
                font-size: 15px;
            }


            .response-critique {
                display: flex;
                justify-content: space-between;
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
        html_content += f'''
        <button class="collapsible">Model: {result['model']} (Usage: {result['usage']})</button>
        <div class="content">
            <div class="response-critique">
                <div class="column">
                    <div class="column-header">Response:</div>
                    <p>{result['response'].replace(line_break, '<br>')}</p>
                </div>
                <div class="column">
                    <div class="column-header">Critique:</div>
                    <p>{result.get('critique', '').replace(line_break, '<br>')}</p>
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

