"""Canonical pipeline ordering for Barsukas agents.

This module defines the standard processing order for lemma tasks in the workqueue.
When multiple tasks for the same lemma are enqueued, they should execute in this order
to ensure dependencies are satisfied (e.g., translations before pronunciations).

The pipeline order is synchronized with the UI display in routes/agents_launcher.py.
"""

from __future__ import annotations

from typing import Dict, Optional

# Mapping from task_type to pipeline step number
# Lower numbers execute first. Tasks not in this mapping have no ordering constraint.
TASK_PIPELINE_ORDER: Dict[str, int] = {
    # Step 1: LOKYS - Validate English Lemma (no workqueue task yet)
    # Step 2: VORAS - Generate Translations
    "add_missing_translations": 2,
    # Step 3: VILKAS - Generate Word Forms
    "generate_forms": 3,
    # Step 4: PAPUGA - Generate Pronunciations
    "generate_pronunciations": 4,
    # Step 5: ŠERNAS - Generate Synonyms
    "generate_synonyms": 5,
    # Step 6: LAPE - Generate Grammar Facts
    "generate_grammar_fact": 6,
    # Step 7: BUIVOLAS - Generate Example Sentences (no workqueue task yet)
    # Step 8: ŽVIRBLIS - Translate Sentences
    "translate_sentence": 8,
    # Step 9: VIEVERSYS - Generate Audio
    "generate_audio": 9,
    # Step 10: BEBRAS - Final Integrity Check (no workqueue task yet)
}


def get_pipeline_step(task_type: str) -> Optional[int]:
    """Get the pipeline step number for a task type, or None if not in pipeline."""
    return TASK_PIPELINE_ORDER.get(task_type)


def has_earlier_step(task_type: str, other_task_type: str) -> bool:
    """Check if task_type should execute before other_task_type in the pipeline.

    Returns True if task_type has an earlier step number than other_task_type.
    Returns False if either task is not in the pipeline or has equal/later step.
    """
    step = get_pipeline_step(task_type)
    other_step = get_pipeline_step(other_task_type)

    if step is None or other_step is None:
        return False

    return step < other_step
