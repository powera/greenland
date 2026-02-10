#!/usr/bin/env python3

"""Generate French noun forms using the shared task registry."""
from typing import Any, Dict, List, Optional

from storage.backend.config import DataSourceConfig
from wordfreq.translation.generate_forms_tasks import (
    FORM_GENERATION_TASKS,
    run_form_generation_task,
)

TASK_KEY = "french_nouns"
CONFIG = FORM_GENERATION_TASKS[TASK_KEY].config


def get_french_noun_lemmas(
    config: DataSourceConfig, limit: Optional[int] = None
) -> List[Dict[str, Any]]:
    return FORM_GENERATION_TASKS[TASK_KEY].lemma_fetcher(config, limit)


def main() -> None:
    run_form_generation_task(TASK_KEY)


if __name__ == "__main__":
    main()
