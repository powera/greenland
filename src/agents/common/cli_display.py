"""Common CLI display utilities for agents.

This module provides reusable functions for displaying results, progress,
and errors in agent command-line interfaces.
"""

from typing import Any, Dict, Optional


def display_result_summary(results: Dict[str, Any], prefix: str = "") -> None:
    """Display a summary of processing results.

    Args:
        results: Dictionary containing processing results with keys:
                 - processed: Number of items processed
                 - successful: Number of successful operations
                 - failed: Number of failed operations
                 (other keys are ignored)
        prefix: Optional prefix to add to each line (for indentation)

    Example:
        results = {"processed": 100, "successful": 95, "failed": 5}
        display_result_summary(results)
        # Output:
        # Processed: 100
        # Successful: 95
        # Failed: 5
    """
    if "processed" in results:
        print(f"{prefix}Processed: {results['processed']}")
    if "successful" in results:
        print(f"{prefix}Successful: {results['successful']}")
    if "failed" in results:
        print(f"{prefix}Failed: {results['failed']}")


def display_progress(current: int, total: int, item_name: str = "items") -> None:
    """Display progress indicator.

    Args:
        current: Current item number (1-indexed)
        total: Total number of items
        item_name: Name of items being processed (e.g., "lemmas", "forms")

    Example:
        display_progress(5, 100, "lemmas")
        # Output: [5/100] Processing lemmas...
    """
    print(f"[{current}/{total}] Processing {item_name}...")


def format_error_message(error: Any) -> str:
    """Format an error for display.

    Args:
        error: Error object (can be string, dict with 'error' key, or Exception)

    Returns:
        Formatted error string

    Example:
        msg = format_error_message({"error": "Database connection failed"})
        print(msg)  # Output: ✗ Error: Database connection failed
    """
    if isinstance(error, dict) and "error" in error:
        return f"✗ Error: {error['error']}"
    elif isinstance(error, str):
        return f"✗ Error: {error}"
    else:
        return f"✗ Error: {str(error)}"


def display_error(error: Any) -> None:
    """Display an error message.

    Args:
        error: Error object (can be string, dict with 'error' key, or Exception)

    Example:
        display_error("Connection timeout")
        # Output: ✗ Error: Connection timeout
    """
    print(format_error_message(error))


def display_language_header(language_code: str, current: int, total: int) -> None:
    """Display a header for language processing.

    Args:
        language_code: Language code (e.g., 'en', 'fr')
        current: Current language number (1-indexed)
        total: Total number of languages

    Example:
        display_language_header('fr', 2, 5)
        # Output:
        # ============================================================
        # Language [2/5]: FR
        # ============================================================
    """
    print(f"\n{'='*60}")
    print(f"Language [{current}/{total}]: {language_code.upper()}")
    print(f"{'='*60}")
