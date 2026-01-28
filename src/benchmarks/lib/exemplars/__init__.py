#!/usr/bin/python3

"""
Exemplars package for comparing responses from different AI models to specific prompts.
"""

from benchmarks.lib.exemplars import base, registry

# Export module-level instances from base.py for convenient access
from benchmarks.lib.exemplars.base import (
    runner,
    storage,
    registry as _base_registry,
)

# Version information
__version__ = "1.0.0"
