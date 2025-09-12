
#!/usr/bin/env python3
"""
Data models and structures for trakaido utilities.

Defines dataclasses and structures used throughout the trakaido system.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class WordData:
    """Data structure for word information from LLM."""
    english: str
    lithuanian: str
    pos_type: str
    pos_subtype: str
    definition: str
    confidence: float
    alternatives: Dict[str, List[str]]
    notes: str
    # Additional translation fields
    chinese_translation: Optional[str] = None
    korean_translation: Optional[str] = None
    french_translation: Optional[str] = None
    swahili_translation: Optional[str] = None
    vietnamese_translation: Optional[str] = None


@dataclass
class ReviewResult:
    """Result of user review process."""
    approved: bool
    modifications: Dict[str, Any]
    notes: str


@dataclass
class ExportStats:
    """Statistics for export operations."""
    total_entries: int
    entries_with_guids: int
    pos_distribution: Dict[str, int]
    level_distribution: Dict[str, int]
    skipped_entries: int = 0
    export_time: Optional[str] = None


@dataclass
class BulkOperationResult:
    """Result of bulk operations on words."""
    total_processed: int
    successful_updates: int
    failed_updates: int
    skipped_items: int
    error_messages: List[str]
    operation_time: Optional[str] = None
    
    @property
    def success_rate(self) -> float:
        """Calculate success rate as percentage."""
        if self.total_processed == 0:
            return 0.0
        return (self.successful_updates / self.total_processed) * 100


@dataclass
class WordFormGenerationResult:
    """Result of noun form generation operations."""
    lemma_id: int
    lemma_text: str
    forms_generated: int
    forms_requested: List[str]
    forms_successful: List[str]
    forms_failed: List[str]
    error_message: Optional[str] = None
    generation_time: Optional[str] = None


@dataclass
class ValidationResult:
    """Result of data validation operations."""
    is_valid: bool
    errors: List[str]
    warnings: List[str]
    suggestions: List[str]
    validation_time: Optional[str] = None


def create_default_word_data(english: str, lithuanian: str = "") -> WordData:
    """
    Create a WordData object with default values.
    
    Args:
        english: English word
        lithuanian: Lithuanian translation (optional)
        
    Returns:
        WordData object with defaults
    """
    return WordData(
        english=english,
        lithuanian=lithuanian,
        pos_type="noun",
        pos_subtype="other",
        definition="",
        confidence=0.5,
        alternatives={"english": [], "lithuanian": []},
        notes=""
    )


def create_export_stats(data: List[Dict[str, Any]]) -> ExportStats:
    """
    Create ExportStats from export data.
    
    Args:
        data: List of export entries
        
    Returns:
        ExportStats object with calculated statistics
    """
    pos_counts = {}
    level_counts = {}
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
        export_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )


def create_bulk_operation_result(total: int, successful: int, failed: int, 
                                errors: List[str] = None) -> BulkOperationResult:
    """
    Create BulkOperationResult with calculated values.
    
    Args:
        total: Total items processed
        successful: Number of successful operations
        failed: Number of failed operations
        errors: List of error messages (optional)
        
    Returns:
        BulkOperationResult object
    """
    return BulkOperationResult(
        total_processed=total,
        successful_updates=successful,
        failed_updates=failed,
        skipped_items=max(0, total - successful - failed),
        error_messages=errors or [],
        operation_time=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )
