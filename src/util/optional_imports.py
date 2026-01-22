"""
Utilities for handling optional dependencies.

This module provides helpers for importing optional packages that may not be installed.
It enables graceful degradation - code that doesn't need optional dependencies can run
without them, while code that does need them gets clear error messages.

Usage:
    # Check availability without raising
    if is_available("torch"):
        torch = require_optional("torch")

    # Import with clear error message if missing
    torch = require_optional("torch", feature="audioshoe TTS")

    # For module-level availability flags (like langtools pattern)
    TORCH_AVAILABLE = is_available("torch")
"""

import importlib
import logging
from typing import Any, Dict, Optional, Tuple, Union

logger = logging.getLogger(__name__)

# Cache for import results: module_name -> (module, None) or (None, error_message)
_import_cache: Dict[str, Tuple[Optional[Any], Optional[str]]] = {}

# Feature to dependency group mapping for install instructions
FEATURE_INSTALL_GROUPS: Dict[str, str] = {
    "audioshoe": "audioshoe",
    "audioshoe TTS": "audioshoe",
    "TTS": "audioshoe",
    "text-to-speech": "audioshoe",
    "ML": "ml",
    "machine learning": "ml",
}


def _get_install_hint(feature: Optional[str]) -> str:
    """Get pip install hint for a feature."""
    if feature:
        group = FEATURE_INSTALL_GROUPS.get(feature, feature.lower().replace(" ", "-"))
        return f"pip install greenland[{group}]"
    return "pip install <package-name>"


def require_optional(
    module_name: str,
    feature: Optional[str] = None,
    package_name: Optional[str] = None,
) -> Any:
    """
    Import an optional module, raising ImportError with helpful message if unavailable.

    Args:
        module_name: The module to import (e.g., "torch", "numpy", "scipy.io.wavfile")
        feature: Human-readable feature name for error message (e.g., "audioshoe TTS")
        package_name: PyPI package name if different from module (e.g., "opencv-python" for "cv2")

    Returns:
        The imported module

    Raises:
        ImportError: If module is not available, with installation instructions

    Example:
        # Inside a function that needs torch:
        def process_audio():
            torch = require_optional("torch", "audioshoe TTS")
            numpy = require_optional("numpy", "audioshoe TTS")
            # ... use torch and numpy
    """
    # Check cache first
    if module_name in _import_cache:
        module, error = _import_cache[module_name]
        if module is not None:
            return module
        # Cached failure - raise with appropriate message
        pkg = package_name or module_name.split(".")[0]
        install_hint = _get_install_hint(feature)
        feature_desc = f" for {feature}" if feature else ""
        raise ImportError(
            f"{pkg} is required{feature_desc} but is not installed. "
            f"Install with: {install_hint}"
        )

    # Try to import
    try:
        module = importlib.import_module(module_name)
        _import_cache[module_name] = (module, None)
        return module
    except ImportError as e:
        _import_cache[module_name] = (None, str(e))
        pkg = package_name or module_name.split(".")[0]
        install_hint = _get_install_hint(feature)
        feature_desc = f" for {feature}" if feature else ""
        raise ImportError(
            f"{pkg} is required{feature_desc} but is not installed. "
            f"Install with: {install_hint}"
        ) from e


def is_available(module_name: str) -> bool:
    """
    Check if an optional module is available without raising an error.

    Args:
        module_name: The module to check (e.g., "torch", "numpy")

    Returns:
        True if module can be imported, False otherwise

    Example:
        TORCH_AVAILABLE = is_available("torch")

        def maybe_use_gpu():
            if TORCH_AVAILABLE:
                torch = require_optional("torch")
                return torch.cuda.is_available()
            return False
    """
    # Check cache first
    if module_name in _import_cache:
        module, _ = _import_cache[module_name]
        return module is not None

    # Try to import
    try:
        module = importlib.import_module(module_name)
        _import_cache[module_name] = (module, None)
        return True
    except ImportError as e:
        _import_cache[module_name] = (None, str(e))
        return False


def get_optional(
    module_name: str,
    default: Any = None,
) -> Any:
    """
    Import an optional module, returning default if unavailable.

    This is useful when you want to conditionally use a module without
    raising errors.

    Args:
        module_name: The module to import
        default: Value to return if import fails (default: None)

    Returns:
        The imported module, or default if unavailable

    Example:
        torch = get_optional("torch")
        if torch is not None:
            device = torch.device("mps")
    """
    try:
        return require_optional(module_name)
    except ImportError:
        return default


# Common optional dependency groups for convenience
AUDIOSHOE_DEPS = ["torch", "numpy", "scipy", "librosa", "pydub"]


def check_audioshoe_deps() -> Tuple[bool, list[str]]:
    """
    Check if audioshoe dependencies are available.

    Returns:
        Tuple of (all_available, list of missing packages)
    """
    missing = [dep for dep in AUDIOSHOE_DEPS if not is_available(dep)]
    return (len(missing) == 0, missing)
