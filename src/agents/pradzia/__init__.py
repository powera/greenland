#!/usr/bin/env python3
"""
Pradzia - Database Initialization Agent

This agent runs autonomously to initialize and maintain the wordfreq database,
including corpus configuration synchronization, data loading, and rank calculation.

"Pradzia" means "beginning" in Lithuanian - the starting point for all data!
"""

from .agent import PradziaAgent

__all__ = ["PradziaAgent"]
