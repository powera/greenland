#!/usr/bin/python3

"""Verbalator routes - custom LLM query interface."""

import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from flask import Blueprint, render_template, request, jsonify

# Add src to path if not already present
if str(Path(__file__).parent.parent.parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

import util.flesch_kincaid as fk
from benchmarks.verbalator import common, prompt_builder, samples
from clients import anthropic_client, ollama_client, openai_client

bp = Blueprint(
    "verbalator",
    __name__,
    url_prefix="/verbalator",
    template_folder="../../verbalator/templates",
)


class GenerationHandler:
    """Handles text generation requests using different LLM clients."""

    @staticmethod
    def generate_text(
        prompt: str, entry: Optional[str], model: str = "phi3:3.8b"
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Generate text using specified model and track usage.

        Args:
            prompt: The generation prompt
            entry: Optional additional context
            model: Model identifier to use

        Returns:
            Tuple of (generated_text, usage_info)
        """
        if model == "gpt4o-mini":
            return openai_client.generate_text(prompt, entry)
        elif model == "claude3-haiku":
            return anthropic_client.generate_text(prompt, entry)
        else:
            # Use Ollama client with combined prompt
            full_prompt = f"{prompt}\n\n{entry}" if entry else prompt
            response, usage = ollama_client.generate_text(full_prompt, model)
            return response, asdict(usage)


@bp.route("/")
def index():
    """Show the verbalator query interface."""
    return render_template("index.html", prompts=common.PROMPTS, samples=samples.ALL_SAMPLES)


@bp.route("/query", methods=["POST"])
def query():
    """Handle text generation requests."""
    try:
        # Parse request data
        data = request.get_json()

        # Extract parameters
        prompt = prompt_builder.build(data.get("prompt"), data)
        if not prompt:
            return jsonify({"error": "No prompt provided"}), 400

        # Generate response
        response, usage = GenerationHandler.generate_text(
            prompt=prompt, entry=data.get("entry"), model=data.get("model", "phi3:3.8b")
        )

        # Calculate reading level
        reading_level = fk.flesch_kincaid_grade(response)

        # Send response
        return jsonify({"response": response, "usage": usage, "reading_level": reading_level})

    except (ValueError, KeyError) as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500
