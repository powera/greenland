#!/usr/bin/env python3

"""Generate Thai adjective forms using the shared task registry."""

from typing import Any, Dict, List, Optional

from storage.backend.config import DataSourceConfig
from wordfreq.translation.generate_forms_tasks import (
    FORM_GENERATION_TASKS,
    run_form_generation_task,
)

TASK_KEY = "thai_adjectives"
CONFIG = FORM_GENERATION_TASKS[TASK_KEY].config


def get_thai_adjective_lemmas(
    config: DataSourceConfig, limit: Optional[int] = None
) -> List[Dict[str, Any]]:
    return FORM_GENERATION_TASKS[TASK_KEY].lemma_fetcher(config, limit)


def main() -> None:
    run_form_generation_task(TASK_KEY)


if __name__ == "__main__":
    main()
