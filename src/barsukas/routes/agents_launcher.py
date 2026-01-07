#!/usr/bin/python3

"""Routes for listing and launching autonomous agents."""

import os
import subprocess
import threading
import time
import uuid
from pathlib import Path

from config import Config
from flask import (
    Blueprint,
    Response,
    flash,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)

import constants
from barsukas.helpers.flash_helpers import flash_and_log
from barsukas.utils.argparse_introspection import (
    get_agent_cli_module_path,
    get_category_label,
    group_arguments_by_category,
    group_arguments_by_mode,
    introspect_agent_parser,
)

bp = Blueprint("agents_launcher", __name__, url_prefix="/agents-launcher")

# Global dictionary to track running agent processes
# Format: {task_id: {"process": Popen, "output": [], "complete": bool, "returncode": int}}
running_tasks = {}

# Define all agents in order from the README
AGENTS = [
    {
        "name": "PRADZIA",
        "display_name": "Pradzia",
        "subtitle": "Database Initialization",
        "description": "Initializes and maintains the wordfreq database, including corpus configuration synchronization, data loading, and rank calculation.",
        "script": "pradzia.py",
        "icon": "bi-play-circle",
        "use_dynamic_form": True,
        "show_if_empty": True,  # Only show if database is empty
    },
    {
        "name": "LOKYS",
        "display_name": "Lokys",
        "subtitle": "English Lemma Validation",
        "description": "Validates English-language properties including lemma forms, definitions, and POS types.",
        "script": "lokys.py",
        "icon": "bi-check-circle",
        "use_dynamic_form": True,
    },
    {
        "name": "DRAMBLYS",
        "display_name": "Dramblys",
        "subtitle": "Missing Words Detector",
        "description": "Identifies missing words that should be in the dictionary by scanning frequency corpora.",
        "script": "dramblys.py",
        "icon": "bi-search",
        "use_dynamic_form": True,
    },
    {
        "name": "BEBRAS",
        "display_name": "Bebras",
        "subtitle": "Database Integrity Checker",
        "description": "Ensures database structural integrity by identifying orphaned records, missing fields, and constraint violations.",
        "script": "bebras.py",
        "icon": "bi-shield-check",
        "use_dynamic_form": True,
    },
    {
        "name": "VORAS",
        "display_name": "Voras",
        "subtitle": "Translation Validator",
        "description": "Validates multi-lingual translations for correctness and proper lemma form, reports on coverage.",
        "script": "voras.py",
        "icon": "bi-globe",
        "use_dynamic_form": True,  # Use argparse introspection instead of predefined modes
    },
    {
        "name": "VILKAS",
        "display_name": "Vilkas",
        "subtitle": "Word Forms Checker",
        "description": "Monitors the presence and completeness of word forms across multiple languages.",
        "script": "vilkas.py",
        "icon": "bi-pencil-square",
        "use_dynamic_form": True,
    },
    {
        "name": "SERNAS",
        "display_name": "Šernas",
        "subtitle": "Synonym Generator",
        "description": "Generates synonyms and alternative forms for vocabulary words across all supported languages.",
        "script": "sernas.py",
        "icon": "bi-shuffle",
        "use_dynamic_form": True,
    },
    {
        "name": "PAPUGA",
        "display_name": "Papuga",
        "subtitle": "Pronunciation Validator",
        "description": "Validates and generates pronunciations (IPA and simplified phonetic) for derivative forms.",
        "script": "papuga.py",
        "icon": "bi-mic",
        "use_dynamic_form": True,
    },
    {
        "name": "ZVIRBLIS",
        "display_name": "Žvirblis",
        "subtitle": "Sentence Translator",
        "description": "Translates existing sentences linked to vocabulary words into target languages.",
        "script": "zvirblis.py",
        "icon": "bi-grid-3x3",
        "use_dynamic_form": True,
    },
    {
        "name": "BUIVOLAS",
        "display_name": "Buivolas",
        "subtitle": "Pattern Sentence Generator",
        "description": "Generates English-only pattern or LLM sentences for language learning.",
        "script": "buivolas/cli.py",
        "icon": "bi-grid-3x3",
        "use_dynamic_form": True,
        "redirect_to": "pattern_sentences.index",
    },
    {
        "name": "LAPE",
        "display_name": "Lape",
        "subtitle": "Grammar Facts Generator",
        "description": "Generates language-specific grammar facts (measure words, gender, etc.) for lemmas.",
        "script": "lape.py",
        "icon": "bi-tag",
        "use_dynamic_form": True,
    },
    {
        "name": "VIEVERSYS",
        "display_name": "Vieversys",
        "subtitle": "OpenAI Audio Generation",
        "description": "Generates high-quality audio files for lemmas using OpenAI TTS API.",
        "script": "vieversys.py",
        "icon": "bi-volume-up",
        "use_dynamic_form": True,
    },
    {
        "name": "STRAZDAS",
        "display_name": "Strazdas",
        "subtitle": "eSpeak-NG Audio Generation",
        "description": "Generates audio files for lemmas using eSpeak-NG TTS (free, local generation).",
        "script": "strazdas.py",
        "icon": "bi-soundwave",
        "use_dynamic_form": True,
    },
    {
        "name": "UNGURYS",
        "display_name": "Ungurys",
        "subtitle": "WireWord Export",
        "description": "Exports word data to WireWord API format for external applications.",
        "script": "ungurys.py",
        "icon": "bi-box-arrow-right",
        "use_dynamic_form": True,
    },
    {
        "name": "ELNIAS",
        "display_name": "Elnias",
        "subtitle": "Bootstrap Export",
        "description": "Exports word data in minimal bootstrap format (word, GUID, categorization, level).",
        "script": "elnias.py",
        "icon": "bi-file-earmark-arrow-down",
        "use_dynamic_form": True,
    },
    {
        "name": "POVAS",
        "display_name": "Povas",
        "subtitle": "HTML Generation",
        "description": "Generates static HTML pages for POS subtypes with comprehensive linguistic information.",
        "script": "povas.py",
        "icon": "bi-file-earmark-code",
        "use_dynamic_form": True,
    },
]

# Define the standard pipeline for populating a word from English lemma+definition to fully populated
PIPELINE = [
    {
        "step": 1,
        "agent_name": "LOKYS",
        "display_name": "Validate English Lemma",
        "description": "Validate the English lemma form, definition, and part of speech",
        "icon": "bi-check-circle",
        "typical_args": "--mode validate-definitions",
    },
    {
        "step": 2,
        "agent_name": "VORAS",
        "display_name": "Generate Translations",
        "description": "Generate and validate translations to all target languages",
        "icon": "bi-globe",
        "typical_args": "--mode add-missing-translations",
    },
    {
        "step": 3,
        "agent_name": "VILKAS",
        "display_name": "Generate Word Forms",
        "description": "Generate derivative word forms (plurals, conjugations, etc.)",
        "icon": "bi-pencil-square",
        "typical_args": "--mode generate-missing-forms",
    },
    {
        "step": 4,
        "agent_name": "PAPUGA",
        "display_name": "Generate Pronunciations",
        "description": "Generate IPA and phonetic pronunciations for all word forms",
        "icon": "bi-mic",
        "typical_args": "--mode generate-missing-pronunciations",
    },
    {
        "step": 5,
        "agent_name": "SERNAS",
        "display_name": "Generate Synonyms",
        "description": "Generate synonyms and alternative forms",
        "icon": "bi-shuffle",
        "typical_args": "--mode generate-synonyms",
    },
    {
        "step": 6,
        "agent_name": "LAPE",
        "display_name": "Generate Grammar Facts",
        "description": "Generate language-specific grammar facts (measure words, gender, etc.)",
        "icon": "bi-tag",
        "typical_args": "--fact-type measure_words --language zh",
    },
    {
        "step": 7,
        "agent_name": "BUIVOLAS",
        "display_name": "Generate Example Sentences",
        "description": "Generate example sentences for vocabulary words",
        "icon": "bi-grid-3x3",
        "typical_args": "generate-sentences --mode llm",
    },
    {
        "step": 8,
        "agent_name": "ZVIRBLIS",
        "display_name": "Translate Sentences",
        "description": "Translate sentences linked to lemmas into target languages",
        "icon": "bi-chat-quote",
        "typical_args": "--guid N06_001 --languages lt zh",
    },
    {
        "step": 9,
        "agent_name": "VIEVERSYS",
        "display_name": "Generate Audio (OpenAI)",
        "description": "Generate high-quality audio files using OpenAI TTS",
        "icon": "bi-volume-up",
        "typical_args": "--mode populate-only --language lt",
    },
    {
        "step": 10,
        "agent_name": "BEBRAS",
        "display_name": "Final Integrity Check",
        "description": "Verify all data is properly structured and complete",
        "icon": "bi-shield-check",
        "typical_args": "--mode check-completeness",
    },
]


def check_database_empty():
    """Check if the database is empty or if key tables are empty."""
    from wordfreq.storage.models.schema import Lemma, WordToken

    try:
        # Check if we have any lemmas or word tokens
        lemma_count = g.db.query(Lemma).count()
        token_count = g.db.query(WordToken).count()

        return lemma_count == 0 or token_count == 0
    except Exception as e:
        # If we can't query, assume database needs initialization
        return True


@bp.route("/")
def list_agents():
    """Display the list of available agents."""
    # Check if database is empty to determine PRADZIA visibility
    db_empty = check_database_empty()

    # Filter agents based on database state
    visible_agents = []
    for agent in AGENTS:
        # Show PRADZIA only if database is empty
        if agent.get("show_if_empty"):
            if db_empty:
                visible_agents.append(agent)
        else:
            # Show all other agents only if database is NOT empty
            if not db_empty:
                visible_agents.append(agent)

    return render_template(
        "agents_launcher/list.html", agents=visible_agents, pipeline=PIPELINE, db_empty=db_empty
    )


@bp.route("/launch/<agent_name>", methods=["GET"])
def launch_form(agent_name):
    """Display the launch form for a specific agent."""
    # Find the agent
    agent = next((a for a in AGENTS if a["name"] == agent_name), None)
    if not agent:
        flash_and_log(f"Agent {agent_name} not found", "error")
        return redirect(url_for("agents_launcher.list_agents"))

    # If agent has redirect_to, redirect there
    if "redirect_to" in agent:
        return redirect(url_for(agent["redirect_to"]))

    # If agent uses dynamic form, introspect its argparse
    parser_info = None
    argument_groups = None
    if agent.get("use_dynamic_form"):
        try:
            module_path = get_agent_cli_module_path(agent["script"])
            parser_info = introspect_agent_parser(module_path)
            # Use semantic category grouping instead of mode-based grouping
            argument_groups = group_arguments_by_category(parser_info["arguments"])
        except Exception as e:
            flash_and_log(f"Error introspecting agent arguments: {str(e)}", "error")
            # Fall back to basic form
            parser_info = None
            argument_groups = None

    return render_template(
        "agents_launcher/launch.html",
        agent=agent,
        parser_info=parser_info,
        argument_groups=argument_groups,
        get_category_label=get_category_label,
    )


@bp.route("/execute/<agent_name>", methods=["POST"])
def execute_agent(agent_name):
    """Execute an agent with specified parameters (async)."""
    # Find the agent
    agent = next((a for a in AGENTS if a["name"] == agent_name), None)
    if not agent:
        flash_and_log(f"Agent {agent_name} not found", "error")
        return redirect(url_for("agents_launcher.list_agents"))

    # Build command
    script_path = Path(constants.AGENTS_DIR) / agent["script"]

    if not script_path.exists():
        flash_and_log(f"Script not found: {script_path}", "error")
        return redirect(url_for("agents_launcher.launch_form", agent_name=agent_name))

    # Build arguments
    args = ["python3", str(script_path)]

    # Handle dynamic form (introspected arguments)
    if agent.get("use_dynamic_form"):
        # Get all form data and convert to command-line arguments
        for key, value in request.form.items():
            if key.startswith("arg_"):
                # Extract argument name (e.g., 'arg_mode' -> 'mode')
                arg_name = key[4:]  # Remove 'arg_' prefix

                # Convert underscores to hyphens for command-line (argparse convention)
                arg_name = arg_name.replace("_", "-")

                # Skip empty values
                if not value or value == "":
                    continue

                # Add the argument
                if value == "true":
                    # Boolean flag
                    args.append(f"--{arg_name}")
                elif "," in value:
                    # List argument (comma-separated)
                    args.append(f"--{arg_name}")
                    args.extend(value.split(","))
                else:
                    # Regular argument
                    args.append(f"--{arg_name}")
                    args.append(value)

    else:
        # Handle static form (predefined modes)
        mode = request.form.get("mode", "")
        custom_args = request.form.get("custom_args", "")
        dry_run = request.form.get("dry_run") == "true"

        # Add mode arguments if provided
        if mode:
            # Find the mode in agent config
            mode_config = next((m for m in agent.get("modes", []) if m["label"] == mode), None)
            if mode_config and mode_config["args"]:
                args.extend(mode_config["args"].split())

        # Add custom arguments
        if custom_args:
            args.extend(custom_args.split())

        # Add dry-run flag if requested
        if dry_run:
            args.append("--dry-run")

    # Add database path (always)
    args.extend(["--db-path", Config.DB_PATH])

    # Add --yes flag for background execution (skip confirmation prompts)
    args.append("--yes")

    try:
        # Generate unique task ID
        task_id = str(uuid.uuid4())

        # Start the process
        process = subprocess.Popen(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,  # Combine stderr into stdout for unified streaming
            text=True,
            bufsize=1,  # Line buffered
            universal_newlines=True,
        )

        # Store task info
        running_tasks[task_id] = {
            "process": process,
            "output": [],
            "complete": False,
            "returncode": None,
            "agent_name": agent_name,
            "agent_display_name": agent["display_name"],
            "cmdline": " ".join(args),
        }

        # Start background thread to read output
        def read_output():
            try:
                for line in process.stdout:
                    running_tasks[task_id]["output"].append(line)
                process.wait()
                running_tasks[task_id]["complete"] = True
                running_tasks[task_id]["returncode"] = process.returncode
            except Exception as e:
                running_tasks[task_id]["output"].append(f"Error reading output: {str(e)}\n")
                running_tasks[task_id]["complete"] = True
                running_tasks[task_id]["returncode"] = -1

        thread = threading.Thread(target=read_output, daemon=True)
        thread.start()

        # Redirect to output page
        return redirect(url_for("agents_launcher.view_output", task_id=task_id))

    except Exception as e:
        flash_and_log(f"Error starting agent: {str(e)}", "error")
        return redirect(url_for("agents_launcher.launch_form", agent_name=agent_name))


@bp.route("/output/<task_id>")
def view_output(task_id):
    """Display the output page for a running/completed agent task."""
    if task_id not in running_tasks:
        flash_and_log("Task not found or expired", "error")
        return redirect(url_for("agents_launcher.list_agents"))

    task = running_tasks[task_id]
    return render_template(
        "agents_launcher/output.html",
        task_id=task_id,
        agent_name=task.get("agent_name", "Unknown"),
        agent_display_name=task.get("agent_display_name", "Agent"),
        cmdline=task.get("cmdline", ""),
    )


@bp.route("/stream/<task_id>")
def stream_output(task_id):
    """Stream the output of a running agent task using Server-Sent Events."""
    if task_id not in running_tasks:
        return jsonify({"success": False, "error": "Task not found"}), 404

    def generate():
        """Generator function to stream output line by line."""
        import json

        task = running_tasks[task_id]
        last_line_sent = 0

        while True:
            # Send any new output lines
            current_output_length = len(task["output"])
            if current_output_length > last_line_sent:
                for i in range(last_line_sent, current_output_length):
                    line_data = json.dumps({"type": "output", "line": task["output"][i]})
                    yield f"data: {line_data}\n\n"
                last_line_sent = current_output_length

            # Check if process is complete
            if task["complete"]:
                complete_data = json.dumps({"type": "complete", "returncode": task["returncode"]})
                yield f"data: {complete_data}\n\n"
                # Clean up old task after a delay (keep for a bit in case of reconnects)
                break

            # Brief sleep to avoid busy-waiting
            time.sleep(0.1)

    return Response(generate(), mimetype="text/event-stream")
