"""Registry of form generation tasks using shared base logic.

This module centralizes language/part-of-speech configuration so callers
can invoke a single entry point instead of a proliferation of thin
scripts.
"""

from dataclasses import dataclass
from typing import Dict, Optional

from langtools.form_registry import FORM_SPECS, LANG_NAMES
from langtools.form_tasks import (
    compute_default_base_form,
    get_generator_name,
    get_task_settings,
)
from storage.backend.config import DataSourceConfig
from words.linguistic_client import LinguisticClient
from words.forms.config import FormGenerationConfig, FormsOutcome
from words.forms.generation import process_lemma_forms


@dataclass
class FormGenerationTask:
    """Describe a form generation workflow."""

    config: FormGenerationConfig


def _compute_threshold(num_fields: int) -> int:
    """Compute a reasonable default min_forms_threshold from field count."""
    if num_fields <= 3:
        return 1
    elif num_fields <= 8:
        return 2
    else:
        return 3


def _build_all_tasks() -> Dict[str, FormGenerationTask]:
    """Build every task from FORM_SPECS plus each language's FORM_TASK_SETTINGS.

    The per-language settings live in ``langtools/<lang>/forms_config.py``;
    see :mod:`langtools.form_tasks` for what each key means.
    """
    tasks: Dict[str, FormGenerationTask] = {}

    for (lang_code, pos_type), spec in sorted(FORM_SPECS.items()):
        lang_name = LANG_NAMES.get(lang_code, spec.language_name)
        task_key = f"{lang_name.lower()}_{pos_type}s"

        settings = get_task_settings(lang_code, pos_type)

        base_form = settings.get("base_form", compute_default_base_form(spec.form_fields))
        threshold = settings.get("threshold", _compute_threshold(len(spec.form_fields)))
        extract_gender = settings.get("extract_gender", False)

        config = FormGenerationConfig(
            language_code=lang_code,
            language_name=lang_name,
            pos_type=pos_type,
            form_mapping=spec.form_mapping,
            generator_name=get_generator_name(lang_code, pos_type),
            min_forms_threshold=threshold,
            base_form_identifier=base_form,
            extract_gender=extract_gender,
        )

        tasks[task_key] = FormGenerationTask(config=config)

    return tasks


FORM_GENERATION_TASKS: Dict[str, FormGenerationTask] = _build_all_tasks()


def get_task_key(language_code: str, pos_type: str) -> str:
    """Resolve a task key for a language/POS combination."""

    for key, task in FORM_GENERATION_TASKS.items():
        if task.config.language_code == language_code and task.config.pos_type == pos_type:
            return key

    raise KeyError(f"No task registered for {language_code} {pos_type}")


def process_lemma_for_task(
    task_key: str,
    lemma_id: int,
    data_config: DataSourceConfig,
    client: Optional[LinguisticClient] = None,
    retry_uncertain: bool = False,
) -> FormsOutcome:
    """Process a single lemma for a registered task.

    A lemma whose forms a model was uncertain of is skipped
    (FormsOutcome.SKIPPED_UNCERTAIN, falsy) unless ``retry_uncertain``.
    """

    if task_key not in FORM_GENERATION_TASKS:
        raise KeyError(f"Unknown form generation task: {task_key}")

    task = FORM_GENERATION_TASKS[task_key]
    client = client or LinguisticClient(config=data_config)
    return process_lemma_forms(client, lemma_id, data_config, task.config, retry_uncertain)
