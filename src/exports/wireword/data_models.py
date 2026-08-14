#!/usr/bin/env python3
"""
Data models for export operations.

Defines dataclasses used by the wireword export system.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class ExportStats:
    """Statistics for export operations."""

    total_entries: int
    entries_with_guids: int
    pos_distribution: Dict[str, int]
    level_distribution: Dict[str, int]
    skipped_entries: int = 0
    export_time: Optional[str] = None


def create_export_stats(data: List[Dict[str, Any]]) -> ExportStats:
    """
    Create ExportStats from export data.

    Args:
        data: List of export entries

    Returns:
        ExportStats object with calculated statistics
    """
    pos_counts: Dict[str, int] = {}
    level_counts: Dict[str, int] = {}
    guid_count = 0

    for entry in data:
        pos = entry.get("POS", "unknown")
        level = entry.get("trakaido_level", "unknown")

        pos_counts[pos] = pos_counts.get(pos, 0) + 1
        level_counts[level] = level_counts.get(level, 0) + 1

        if entry.get("GUID"):
            guid_count += 1

    return ExportStats(
        total_entries=len(data),
        entries_with_guids=guid_count,
        pos_distribution=dict(sorted(pos_counts.items())),
        level_distribution=dict(sorted(level_counts.items())),
        export_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )
