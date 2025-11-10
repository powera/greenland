#!/usr/bin/python3
"""
Argparse Introspection Utility

This module provides tools for introspecting argparse parsers from agent CLI modules
to dynamically generate web forms without duplicating flag definitions.
"""

import importlib
import argparse
from typing import Dict, List, Any, Optional
from pathlib import Path


class ArgumentInfo:
    """Structured information about a single command-line argument."""

    def __init__(self, action):
        """Initialize from an argparse Action object."""
        self.names = action.option_strings  # e.g., ['--limit'] or ['--yes', '-y']
        self.dest = action.dest  # e.g., 'limit'
        self.help = action.help or ""
        self.default = action.default
        self.required = action.required
        self.choices = getattr(action, 'choices', None)
        self.nargs = action.nargs
        self.metavar = action.metavar
        self.type_name = self._infer_type(action)

        # Detect mode/group from help text patterns
        self.mode_hint = self._extract_mode_hint(self.help)

    def _infer_type(self, action) -> str:
        """Infer the input type from the action."""
        if isinstance(action, argparse._StoreTrueAction):
            return 'boolean'
        elif isinstance(action, argparse._StoreFalseAction):
            return 'boolean'
        elif action.nargs in ['+', '*']:
            # List type takes precedence over choices
            return 'list'
        elif self.choices:
            return 'choice'
        elif action.type == int:
            return 'integer'
        elif action.type == float:
            return 'float'
        else:
            return 'string'

    def _extract_mode_hint(self, help_text: str) -> Optional[str]:
        """Extract mode hints from help text like '[Fix mode]' or '[Stage mode]'."""
        import re
        match = re.search(r'\[([^\]]+)\s+mode\]', help_text, re.IGNORECASE)
        if match:
            return match.group(1).lower()
        return None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to a dictionary for JSON serialization."""
        return {
            'names': self.names,
            'dest': self.dest,
            'help': self.help,
            'default': self.default,
            'required': self.required,
            'type': self.type_name,
            'choices': self.choices,
            'nargs': self.nargs,
            'metavar': self.metavar,
            'mode_hint': self.mode_hint
        }


def introspect_agent_parser(agent_module_path: str) -> Dict[str, Any]:
    """
    Introspect an agent's argument parser.

    Args:
        agent_module_path: Python module path, e.g., 'wordfreq.agents.voras.cli'

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
        module_parts = agent_module_path.split('.')
        # Find the greenland/src directory
        src_path = Path(__file__).parent.parent.parent  # barsukas/utils -> barsukas -> src
        file_path = src_path.joinpath(*module_parts).with_suffix('.py')

        if not file_path.exists():
            raise FileNotFoundError(f"Module file not found: {file_path}")

        # Load the module directly from the file
        spec = importlib.util.spec_from_file_location(agent_module_path, file_path)
        module = importlib.util.module_from_spec(spec)

        # Temporarily add to sys.modules to handle any internal imports
        sys.modules[agent_module_path] = module
        spec.loader.exec_module(module)

        # Get the parser
        if not hasattr(module, 'get_argument_parser'):
            raise AttributeError(f"Module {agent_module_path} does not have get_argument_parser()")

        parser = module.get_argument_parser()

        # Extract all arguments
        arguments = []
        modes = set()

        for action in parser._actions:
            # Skip positional arguments and help
            if not action.option_strings or action.dest == 'help':
                continue

            arg_info = ArgumentInfo(action)
            arguments.append(arg_info)

            # Collect mode hints
            if arg_info.mode_hint:
                modes.add(arg_info.mode_hint)

        return {
            'description': parser.description,
            'arguments': [arg.to_dict() for arg in arguments],
            'modes': sorted(list(modes))
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
    groups = {'common': []}

    for arg in arguments:
        mode_hint = arg.get('mode_hint')
        if mode_hint:
            if mode_hint not in groups:
                groups[mode_hint] = []
            groups[mode_hint].append(arg)
        else:
            groups['common'].append(arg)

    return groups


def get_agent_cli_module_path(agent_script: str) -> str:
    """
    Get the Python module path for an agent's CLI.

    Args:
        agent_script: Script name like 'voras.py' or 'bebras.py'

    Returns:
        Module path like 'wordfreq.agents.voras.cli' or 'wordfreq.agents.bebras'
    """
    agent_name = agent_script.replace('.py', '')

    # Check if it's a multi-file agent (has a directory)
    multi_file_agents = ['voras', 'vilkas', 'dramblys']

    if agent_name in multi_file_agents:
        return f'wordfreq.agents.{agent_name}.cli'
    else:
        return f'wordfreq.agents.{agent_name}'
