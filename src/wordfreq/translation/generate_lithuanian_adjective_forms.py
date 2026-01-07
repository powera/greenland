#!/usr/bin/env python3

"""Generate Lithuanian adjective forms using the shared task registry."""
from typing import Optional

from wordfreq.storage.backend.config import DataSourceConfig
from wordfreq.translation.generate_forms_tasks import (
    FORM_GENERATION_TASKS,
    run_form_generation_task,
)

TASK_KEY = "lithuanian_adjectives"
CONFIG = FORM_GENERATION_TASKS[TASK_KEY].config


def get_lithuanian_adjective_lemmas(config: DataSourceConfig, limit: Optional[int] = None):
    return FORM_GENERATION_TASKS[TASK_KEY].lemma_fetcher(config, limit)


def main():
    run_form_generation_task(TASK_KEY)


if __name__ == "__main__":
    main()
