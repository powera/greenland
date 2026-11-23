"""The workqueue registry must not import agent modules.

``workqueue/__init__`` loads the registry, so an agent module that imports
``workqueue`` while the registry imports it back is a circular import whenever
the agent module happens to load first -- a test file run on its own, or
``python -m agents.<name>``.  The full suite hides it, because an earlier test
has already loaded ``workqueue``.  Jobs live under ``workqueue/handlers/``;
agents import them, never the other way round.
"""

import ast
from pathlib import Path

import workqueue.registry


def test_registry_imports_nothing_from_agents() -> None:
    tree = ast.parse(Path(workqueue.registry.__file__).read_text())
    imported = [
        node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    ] + [
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    ]
    assert [name for name in imported if name.split(".")[0] == "agents"] == []
