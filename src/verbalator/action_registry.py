"""Registry for verbalator actions."""

from typing import Dict, List

from verbalator.action_base import ActionBase

ACTIONS: Dict[str, ActionBase] = {}


def register(action: ActionBase) -> None:
    """Register an action instance by name."""
    ACTIONS[action.name] = action


def get_action(name: str) -> ActionBase:
    """Look up a registered action by name.

    Raises:
        KeyError: If the action name is not registered.
    """
    if name not in ACTIONS:
        raise KeyError(f"Unknown action: {name!r}. Available: {list(ACTIONS.keys())}")
    return ACTIONS[name]


def list_actions() -> List[ActionBase]:
    """Return all registered actions, sorted by color group then name."""
    return sorted(ACTIONS.values(), key=lambda a: (a.color_group, a.name))
