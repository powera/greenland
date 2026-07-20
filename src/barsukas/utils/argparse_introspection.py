#!/usr/bin/python3
"""
Argparse Introspection Utility

This module provides tools for introspecting argparse parsers from agent CLI modules
to dynamically generate web forms without duplicating flag definitions.
"""

import argparse
import importlib
from pathlib import Path
from typing import Any, Dict, List, Optional, cast


class ArgumentInfo:
    """Structured information about a single command-line argument."""

    def __init__(self, action: argparse.Action) -> None:
        """Initialize from an argparse Action object."""
        self.names = action.option_strings  # e.g., ['--limit'] or ['--yes', '-y']
        self.dest = action.dest  # e.g., 'limit'
        self.help = action.help or ""
        self.default = action.default
        self.required = action.required
        self.choices = getattr(action, "choices", None)
        self.nargs = action.nargs
        self.metavar = action.metavar
        self.type_name = self._infer_type(action)

        # Detect mode/group from help text patterns
        self.mode_hint = self._extract_mode_hint(self.help)

    def _infer_type(self, action: argparse.Action) -> str:
        """Infer the input type from the action."""
        if isinstance(action, argparse._StoreTrueAction):
            return "boolean"
        elif isinstance(action, argparse._StoreFalseAction):
            return "boolean"
        elif action.nargs in ["+", "*"]:
            # List type takes precedence over choices
            return "list"
        elif self.choices:
            return "choice"
        elif action.type == int:
            return "integer"
        elif action.type == float:
            return "float"
        else:
            return "string"

    def _extract_mode_hint(self, help_text: str) -> Optional[str]:
        """Extract mode hints from help text like '[Fix mode]' or '[Stage mode]'."""
        import re

        match = re.search(r"\[([^\]]+)\s+mode\]", help_text, re.IGNORECASE)
        if match:
            return match.group(1).lower()
        return None

    def get_semantic_category(self) -> str:
        """Determine the semantic category of this argument for UI grouping."""
        dest = self.dest.lower()

        # Operation Mode - what operation to perform
        if dest in [
            "mode",
            "check_type",
            "check",
            "fix",
            "stage",
            "form_type",
            "task",
        ]:
            return "operation_mode"

        # Data Source / Scope - what data to process
        if dest in [
            "guid",
            "limit",
            "sample_rate",
            "batch",
            "batch_submit",
            "batch_status",
            "batch_retrieve",
        ]:
            return "data_source"

        # Language Selection
        if dest in ["language", "languages", "target_language"]:
            return "language_selection"

        # LLM Configuration
        if dest in ["model", "throttle", "barsukas_url", "cache_only"]:
            return "llm_config"

        # Backend Configuration
        if dest in ["persona", "backend", "data_dir", "postgres"]:
            return "backend_config"

        # Processing Options
        if dest in ["dry_run", "debug"]:
            return "processing_options"

        # Advanced Options - everything else (thresholds, specific settings, etc.)
        return "advanced_options"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to a dictionary for JSON serialization."""
        return {
            "names": self.names,
            "dest": self.dest,
            "help": self.help,
            "default": self.default,
            "required": self.required,
            "type": self.type_name,
            "choices": self.choices,
            "nargs": self.nargs,
            "metavar": self.metavar,
            "mode_hint": self.mode_hint,
            "semantic_category": self.get_semantic_category(),
        }


def introspect_agent_parser(agent_module_path: str) -> Dict[str, Any]:
    """
    Introspect an agent's argument parser.

    Args:
        agent_module_path: Python module path, e.g., 'agents.voras.cli'

    Returns:
        Dictionary containing:
        - description: Parser description
        - arguments: List of ArgumentInfo dictionaries
        - modes: Detected mode groups
    """
    try:
        # Import the module directly from file to avoid package-level imports
        import importlib.util
        import sys

        # Convert module path to file path
        module_parts = agent_module_path.split(".")
        # Find the greenland/src directory
        src_path = Path(__file__).parent.parent.parent  # barsukas/utils -> barsukas -> src
        file_path = src_path.joinpath(*module_parts).with_suffix(".py")

        if not file_path.exists():
            raise FileNotFoundError(f"Module file not found: {file_path}")

        # Load the module directly from the file
        spec = importlib.util.spec_from_file_location(agent_module_path, file_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Could not load module spec from {file_path}")
        module = importlib.util.module_from_spec(spec)

        # Temporarily add to sys.modules to handle any internal imports
        sys.modules[agent_module_path] = module
        spec.loader.exec_module(module)

        # Get the parser
        if not hasattr(module, "get_argument_parser"):
            raise AttributeError(f"Module {agent_module_path} does not have get_argument_parser()")

        parser = module.get_argument_parser()

        # Extract all arguments
        arguments = []
        modes = set()

        # Arguments that BARSUKAS adds automatically and should not be shown in the form
        # Also hide output since users view results in the web UI, not files
        AUTO_ADDED_ARGS = {"db_path", "yes", "y", "output"}

        for action in parser._actions:
            # Skip positional arguments and help
            if not action.option_strings or action.dest == "help":
                continue

            # Skip arguments that BARSUKAS adds automatically
            if action.dest in AUTO_ADDED_ARGS:
                continue

            # Skip deprecated arguments (marked in help text by common_args);
            # the launcher passes --persona instead
            if (action.help or "").lstrip().upper().startswith("[DEPRECATED]"):
                continue

            arg_info = ArgumentInfo(action)
            arguments.append(arg_info)

            # Collect mode hints
            if arg_info.mode_hint:
                modes.add(arg_info.mode_hint)

        return {
            "description": parser.description,
            "arguments": [arg.to_dict() for arg in arguments],
            "modes": sorted(list(modes)),
        }

    except Exception as e:
        raise RuntimeError(f"Failed to introspect {agent_module_path}: {str(e)}") from e


def group_arguments_by_mode(arguments: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """
    Group arguments by their mode hints.

    Args:
        arguments: List of argument dictionaries

    Returns:
        Dictionary mapping mode names to lists of arguments.
        Arguments with no mode hint are in the 'common' group.
    """
    groups: Dict[str, List[Dict[str, Any]]] = {"common": []}

    for arg in arguments:
        mode_hint = arg.get("mode_hint")
        if mode_hint:
            if mode_hint not in groups:
                groups[mode_hint] = []
            groups[mode_hint].append(arg)
        else:
            groups["common"].append(arg)

    return groups


def group_arguments_by_category(arguments: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """
    Group arguments by their semantic category for improved UI organization.

    Args:
        arguments: List of argument dictionaries

    Returns:
        Dictionary mapping category names to lists of arguments.
        Categories are ordered for display.
    """
    # Define category order and display names
    category_info = {
        "operation_mode": {"label": "Operation Mode", "order": 1},
        "data_source": {"label": "Data Source / Scope", "order": 2},
        "language_selection": {"label": "Language Selection", "order": 3},
        "llm_config": {"label": "LLM Configuration", "order": 4},
        "backend_config": {"label": "Backend Configuration", "order": 5},
        "processing_options": {"label": "Processing Options", "order": 6},
        "advanced_options": {"label": "Advanced Options", "order": 7},
    }

    groups: Dict[str, List[Dict[str, Any]]] = {cat: [] for cat in category_info.keys()}

    for arg in arguments:
        category = arg.get("semantic_category", "advanced_options")
        if category in groups:
            groups[category].append(arg)
        else:
            groups["advanced_options"].append(arg)

    # Remove empty groups and return in order
    return {
        cat: groups[cat]
        for cat in sorted(
            groups.keys(), key=lambda x: cast(int, category_info.get(x, {}).get("order", 99))
        )
        if groups[cat]
    }


def get_category_label(category: str) -> str:
    """Get the display label for a semantic category."""
    category_labels = {
        "operation_mode": "Operation Mode",
        "data_source": "Data Source / Scope",
        "language_selection": "Language Selection",
        "llm_config": "LLM Configuration",
        "backend_config": "Backend Configuration",
        "processing_options": "Processing Options",
        "advanced_options": "Advanced Options",
    }
    return category_labels.get(category, category.replace("_", " ").title())


def get_agent_cli_module_path(agent_script: str) -> str:
    """
    Get the Python module path for an agent's CLI.

    Args:
        agent_script: Script name like 'voras.py' or 'buivolas/cli.py'

    Returns:
        Module path like 'agents.voras.cli' or 'agents.buivolas.cli'
    """
    module_stub = agent_script.replace(".py", "").replace("/", ".")
    agent_name = module_stub.split(".")[0]

    # Auto-detect multi-file agents by checking if agents/{name}/cli.py exists
    src_path = Path(__file__).parent.parent.parent  # barsukas/utils -> barsukas -> src
    cli_path = src_path / "agents" / agent_name / "cli.py"

    if cli_path.exists() and module_stub == agent_name:
        return f"agents.{agent_name}.cli"

    return f"agents.{module_stub}"
