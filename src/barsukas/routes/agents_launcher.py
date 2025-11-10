#!/usr/bin/python3

"""Routes for listing and launching autonomous agents."""

from flask import Blueprint, render_template, request, jsonify, flash, redirect, url_for, g
import subprocess
import os
from pathlib import Path
from config import Config
from barsukas.utils.argparse_introspection import introspect_agent_parser, get_agent_cli_module_path, group_arguments_by_mode

bp = Blueprint('agents_launcher', __name__, url_prefix='/agents-launcher')

# Define all agents in order from the README
AGENTS = [
    {
        'name': 'PRADZIA',
        'display_name': 'Pradzia',
        'subtitle': 'Database Initialization',
        'description': 'Initializes and maintains the wordfreq database, including corpus configuration synchronization, data loading, and rank calculation.',
        'script': 'pradzia.py',
        'icon': 'bi-play-circle',
        'modes': [
            {'label': 'Check Status', 'args': '--check', 'description': 'Check configuration and database state without making changes'},
            {'label': 'Sync Config', 'args': '--sync-config', 'description': 'Synchronize corpus configurations from config file to database'},
            {'label': 'Load Corpora', 'args': '--load', 'description': 'Load all enabled corpora'},
            {'label': 'Calculate Ranks', 'args': '--calc-ranks', 'description': 'Calculate combined ranks for all words'},
            {'label': 'Full Init', 'args': '--init-full', 'description': 'Perform complete database initialization'},
        ],
        'show_if_empty': True  # Only show if database is empty
    },
    {
        'name': 'LOKYS',
        'display_name': 'Lokys',
        'subtitle': 'English Lemma Validation',
        'description': 'Validates English-language properties including lemma forms, definitions, and POS types.',
        'script': 'lokys.py',
        'icon': 'bi-check-circle',
        'modes': [
            {'label': 'Run Validation', 'args': '', 'description': 'Validate all English lemmas'},
            {'label': 'Sample Check', 'args': '--sample-rate 0.1', 'description': 'Check 10% sample of lemmas'},
        ],
    },
    {
        'name': 'DRAMBLYS',
        'display_name': 'Dramblys',
        'subtitle': 'Missing Words Detector',
        'description': 'Identifies missing words that should be in the dictionary by scanning frequency corpora.',
        'script': 'dramblys.py',
        'icon': 'bi-search',
        'modes': [
            {'label': 'Check All', 'args': '--check all', 'description': 'Run all checks (reporting only)'},
            {'label': 'Check Frequency', 'args': '--check frequency', 'description': 'Find high-frequency words missing from database'},
            {'label': 'Fix Missing', 'args': '--fix', 'description': 'Process high-frequency missing words using LLM'},
        ],
    },
    {
        'name': 'BEBRAS',
        'display_name': 'Bebras',
        'subtitle': 'Database Integrity Checker',
        'description': 'Ensures database structural integrity by identifying orphaned records, missing fields, and constraint violations.',
        'script': 'bebras.py',
        'icon': 'bi-shield-check',
        'modes': [
            {'label': 'Check All', 'args': '--check all', 'description': 'Run all integrity checks'},
            {'label': 'Check Orphaned', 'args': '--check orphaned', 'description': 'Find orphaned records'},
            {'label': 'Check Missing Fields', 'args': '--check missing-fields', 'description': 'Find records with missing required fields'},
        ],
    },
    {
        'name': 'VORAS',
        'display_name': 'Voras',
        'subtitle': 'Translation Validator',
        'description': 'Validates multi-lingual translations for correctness and proper lemma form, reports on coverage.',
        'script': 'voras.py',
        'icon': 'bi-globe',
        'use_dynamic_form': True,  # Use argparse introspection instead of predefined modes
    },
    {
        'name': 'VILKAS',
        'display_name': 'Vilkas',
        'subtitle': 'Word Forms Checker',
        'description': 'Monitors the presence and completeness of word forms across multiple languages.',
        'script': 'vilkas.py',
        'icon': 'bi-pencil-square',
        'modes': [
            {'label': 'Check All', 'args': '--check all', 'description': 'Run all checks and generate report'},
            {'label': 'Fix Forms', 'args': '--fix', 'description': 'Generate missing word forms'},
        ],
    },
    {
        'name': 'PAPUGA',
        'display_name': 'Papuga',
        'subtitle': 'Pronunciation Validator',
        'description': 'Validates and generates pronunciations (IPA and simplified phonetic) for derivative forms.',
        'script': 'papuga.py',
        'icon': 'bi-mic',
        'modes': [
            {'label': 'Check Pronunciations', 'args': '--check', 'description': 'Validate existing pronunciations'},
            {'label': 'Populate Missing', 'args': '--populate', 'description': 'Generate missing pronunciations'},
            {'label': 'Check & Populate', 'args': '--both', 'description': 'Validate and populate pronunciations'},
        ],
    },
    {
        'name': 'ZVIRBLIS',
        'display_name': 'Žvirblis',
        'subtitle': 'Sentence Generator',
        'description': 'Generates example sentences for vocabulary words using LLM, with automatic difficulty calculation.',
        'script': 'zvirblis.py',
        'icon': 'bi-chat-quote',
        'modes': [
            {'label': 'Generate by GUID', 'args': '--guid', 'description': 'Generate sentences for specific word by GUID', 'requires_input': True, 'input_placeholder': 'Enter GUID (e.g., N07_008)'},
            {'label': 'Generate by Level', 'args': '--level', 'description': 'Generate sentences for all nouns at difficulty level', 'requires_input': True, 'input_placeholder': 'Enter level (1-20)'},
        ],
    },
    {
        'name': 'POVAS',
        'display_name': 'Povas',
        'subtitle': 'HTML Generator',
        'description': 'Generates static HTML pages displaying words organized by part-of-speech subtypes.',
        'script': 'povas.py',
        'icon': 'bi-file-earmark-code',
        'modes': [
            {'label': 'Generate All', 'args': '', 'description': 'Generate all POS subtype HTML pages'},
            {'label': 'Index Only', 'args': '--index-only', 'description': 'Generate only the index page'},
        ],
    },
    {
        'name': 'UNGURYS',
        'display_name': 'Ungurys',
        'subtitle': 'WireWord Export',
        'description': 'Exports word data to WireWord API format for external system integration.',
        'script': 'ungurys.py',
        'icon': 'bi-cloud-download',
        'redirect_to': 'wireword.export_page',  # Redirect to existing wireword export page
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


@bp.route('/')
def list_agents():
    """Display the list of available agents."""
    # Check if database is empty to determine PRADZIA visibility
    db_empty = check_database_empty()

    # Filter agents based on database state
    visible_agents = []
    for agent in AGENTS:
        # Show PRADZIA only if database is empty
        if agent.get('show_if_empty'):
            if db_empty:
                visible_agents.append(agent)
        else:
            # Show all other agents only if database is NOT empty
            if not db_empty:
                visible_agents.append(agent)

    return render_template('agents_launcher/list.html',
                         agents=visible_agents,
                         db_empty=db_empty)


@bp.route('/launch/<agent_name>', methods=['GET'])
def launch_form(agent_name):
    """Display the launch form for a specific agent."""
    # Find the agent
    agent = next((a for a in AGENTS if a['name'] == agent_name), None)
    if not agent:
        flash(f'Agent {agent_name} not found', 'error')
        return redirect(url_for('agents_launcher.list_agents'))

    # If agent has redirect_to, redirect there
    if 'redirect_to' in agent:
        return redirect(url_for(agent['redirect_to']))

    # If agent uses dynamic form, introspect its argparse
    parser_info = None
    argument_groups = None
    if agent.get('use_dynamic_form'):
        try:
            module_path = get_agent_cli_module_path(agent['script'])
            parser_info = introspect_agent_parser(module_path)
            argument_groups = group_arguments_by_mode(parser_info['arguments'])
        except Exception as e:
            flash(f'Error introspecting agent arguments: {str(e)}', 'error')
            # Fall back to basic form
            parser_info = None
            argument_groups = None

    return render_template('agents_launcher/launch.html',
                         agent=agent,
                         parser_info=parser_info,
                         argument_groups=argument_groups)


@bp.route('/execute/<agent_name>', methods=['POST'])
def execute_agent(agent_name):
    """Execute an agent with specified parameters (async)."""
    # Find the agent
    agent = next((a for a in AGENTS if a['name'] == agent_name), None)
    if not agent:
        return jsonify({'success': False, 'error': f'Agent {agent_name} not found'}), 404

    # Build command
    agents_dir = Path(Config.DB_PATH).parent.parent / 'agents'
    script_path = agents_dir / agent['script']

    if not script_path.exists():
        return jsonify({'success': False, 'error': f'Script not found: {script_path}'}), 404

    # Build arguments
    args = ['python3', str(script_path)]

    # Handle dynamic form (introspected arguments)
    if agent.get('use_dynamic_form'):
        # Get all form data and convert to command-line arguments
        for key, value in request.form.items():
            if key.startswith('arg_'):
                # Extract argument name (e.g., 'arg_mode' -> 'mode')
                arg_name = key[4:]  # Remove 'arg_' prefix

                # Skip empty values
                if not value or value == '':
                    continue

                # Add the argument
                if value == 'true':
                    # Boolean flag
                    args.append(f'--{arg_name}')
                elif ',' in value:
                    # List argument (comma-separated)
                    args.append(f'--{arg_name}')
                    args.extend(value.split(','))
                else:
                    # Regular argument
                    args.append(f'--{arg_name}')
                    args.append(value)

    else:
        # Handle static form (predefined modes)
        mode = request.form.get('mode', '')
        custom_args = request.form.get('custom_args', '')
        dry_run = request.form.get('dry_run') == 'true'

        # Add mode arguments if provided
        if mode:
            # Find the mode in agent config
            mode_config = next((m for m in agent.get('modes', []) if m['label'] == mode), None)
            if mode_config and mode_config['args']:
                args.extend(mode_config['args'].split())

        # Add custom arguments
        if custom_args:
            args.extend(custom_args.split())

        # Add dry-run flag if requested
        if dry_run:
            args.append('--dry-run')

    # Add database path (always)
    args.extend(['--db-path', Config.DB_PATH])

    try:
        # Execute asynchronously (non-blocking)
        # Note: In production, you'd want to use Celery or similar
        # For now, we'll run in background and return immediately
        process = subprocess.Popen(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

        # For now, wait for completion (in production, make this truly async)
        stdout, stderr = process.communicate(timeout=300)  # 5 min timeout

        success = process.returncode == 0

        return jsonify({
            'success': success,
            'stdout': stdout,
            'stderr': stderr,
            'returncode': process.returncode
        })

    except subprocess.TimeoutExpired:
        process.kill()
        return jsonify({
            'success': False,
            'error': 'Agent execution timed out (5 minutes)',
            'timeout': True
        }), 408
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
