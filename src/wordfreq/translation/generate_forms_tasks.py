"""Registry of form generation tasks using shared base logic.

This module centralizes language/part-of-speech configuration so callers
can invoke a single entry point instead of a proliferation of thin
scripts.
"""

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

from langtools.form_registry import FORM_SPECS, LANG_NAMES
from storage.backend.config import DataSourceConfig
from wordfreq.translation.client import LinguisticClient
from wordfreq.translation.generate_forms_base import (
    FormGenerationConfig,
    get_lemmas_needing_forms,
    get_lemmas_with_translation,
    process_lemma_forms,
    run_form_generation,
)


@dataclass
class FormGenerationTask:
    """Describe a form generation workflow."""

    config: FormGenerationConfig
    lemma_fetcher: Callable[[DataSourceConfig, Optional[int]], List[Dict[str, Any]]]


def _translation_task(
    config: FormGenerationConfig,
) -> FormGenerationTask:
    def fetcher(data_config: DataSourceConfig, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        return get_lemmas_with_translation(data_config, config, limit)

    return FormGenerationTask(config=config, lemma_fetcher=fetcher)


def _needs_forms_task(
    config: FormGenerationConfig,
) -> FormGenerationTask:
    def fetcher(data_config: DataSourceConfig, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        return get_lemmas_needing_forms(data_config, config, limit)

    return FormGenerationTask(config=config, lemma_fetcher=fetcher)


# ---------------------------------------------------------------------------
# Override table: only fields that differ from auto-computed defaults.
#
# Keys: (language_code, pos_type)
# Values: dict with any of:
#   "fetcher"        – "translation" or "needs_forms" (default: "needs_forms")
#   "threshold"      – min_forms_threshold override
#   "base_form"      – base_form_identifier override
#   "gender"         – extract_gender (default: False)
#   "client_method"  – client_method_name override (default: "query_language_forms")
# ---------------------------------------------------------------------------

_TASK_OVERRIDES: Dict[Tuple[str, str], Dict[str, Any]] = {
    # English — source language, needs_forms fetcher, named client methods
    ("en", "noun"): {
        "threshold": 1,
        "client_method": "query_english_noun_forms",
    },
    ("en", "verb"): {
        "threshold": 5,
        "base_form": "infinitive",
        "client_method": "query_english_verb_forms",
    },
    ("en", "adjective"): {
        "threshold": 2,
        "client_method": "query_english_adjective_forms",
    },
    ("en", "adverb"): {
        "threshold": 2,
        "client_method": "query_english_adverb_forms",
    },
    # French — translation fetcher, named client methods, gender on nouns
    ("fr", "noun"): {
        "fetcher": "translation",
        "threshold": 2,
        "gender": True,
        "client_method": "query_french_noun_forms",
    },
    ("fr", "verb"): {
        "fetcher": "translation",
        "threshold": 25,
        "client_method": "query_french_verb_conjugations",
    },
    # German — translation fetcher, gender on nouns
    ("de", "noun"): {
        "fetcher": "translation",
        "threshold": 3,
        "gender": True,
    },
    ("de", "verb"): {
        "fetcher": "translation",
        "threshold": 10,
    },
    # Lithuanian — translation fetcher, named client methods
    ("lt", "noun"): {
        "fetcher": "translation",
        "client_method": "query_lithuanian_noun_declensions",
    },
    ("lt", "verb"): {
        "fetcher": "translation",
        "threshold": 6,
        "client_method": "query_lithuanian_verb_conjugations",
    },
    ("lt", "adjective"): {
        "fetcher": "translation",
        "threshold": 4,
        "client_method": "query_lithuanian_adjective_declensions",
    },
    ("lt", "adverb"): {
        "fetcher": "translation",
        "client_method": "query_lithuanian_adverb_forms",
    },
    # Latvian — translation fetcher
    ("lv", "noun"): {"fetcher": "translation", "threshold": 3},
    ("lv", "verb"): {"fetcher": "translation", "threshold": 6},
    ("lv", "adjective"): {"fetcher": "translation", "threshold": 4},
    ("lv", "adverb"): {"fetcher": "translation"},
    # Ukrainian — translation fetcher
    ("uk", "noun"): {"fetcher": "translation", "threshold": 3},
    ("uk", "verb"): {"fetcher": "translation", "threshold": 6},
    ("uk", "adjective"): {"fetcher": "translation", "threshold": 4},
    ("uk", "adverb"): {"fetcher": "translation"},
    # Spanish — translation fetcher, named client methods, gender on nouns
    ("es", "noun"): {
        "fetcher": "translation",
        "threshold": 2,
        "gender": True,
        "client_method": "query_spanish_noun_forms",
    },
    ("es", "verb"): {
        "fetcher": "translation",
        "threshold": 10,
        "client_method": "query_spanish_verb_conjugations",
    },
    # Italian — translation fetcher, gender on nouns
    ("it", "noun"): {"fetcher": "translation", "threshold": 2, "gender": True},
    ("it", "verb"): {"fetcher": "translation", "threshold": 10},
    ("it", "adjective"): {
        "fetcher": "translation",
        "threshold": 4,
        "client_method": "query_italian_adjective_forms",
    },
    # Swedish — translation fetcher
    ("sv", "noun"): {"fetcher": "translation", "threshold": 2},
    ("sv", "verb"): {"fetcher": "translation", "threshold": 2},
    # Dutch — translation fetcher, gender on nouns
    ("nl", "noun"): {"fetcher": "translation", "threshold": 2, "gender": True},
    ("nl", "verb"): {"fetcher": "translation", "threshold": 10},
    # Portuguese — translation fetcher, gender on nouns
    ("pt", "noun"): {"fetcher": "translation", "threshold": 2, "gender": True},
    ("pt", "verb"): {"fetcher": "translation", "threshold": 10},
    ("pt", "adjective"): {
        "fetcher": "translation",
        "threshold": 4,
        "client_method": "query_portuguese_adjective_forms",
    },
    # Chinese — named client methods
    ("zh", "noun"): {"client_method": "query_chinese_noun_forms"},
    ("zh", "verb"): {"threshold": 3, "client_method": "query_chinese_verb_forms"},
    # Japanese — named client methods
    ("ja", "noun"): {"client_method": "query_japanese_noun_forms"},
    ("ja", "verb"): {"threshold": 3, "client_method": "query_japanese_verb_conjugations"},
    # Korean — named client methods
    ("ko", "noun"): {"client_method": "query_korean_noun_forms"},
    ("ko", "verb"): {"threshold": 2, "client_method": "query_korean_verb_conjugations"},
}


def _compute_base_form(spec_fields: List[str]) -> str:
    """Derive base_form_identifier from the spec's form_fields."""
    if spec_fields[0] == "base":
        return "base"
    for candidate in [
        "singular",
        "nominative_singular",
        "1s_present",
        "present",
        "polite_present",
        "masu",
        "positive",
    ]:
        if candidate in spec_fields:
            return candidate
    return spec_fields[0]


def _compute_threshold(num_fields: int) -> int:
    """Compute a reasonable default min_forms_threshold from field count."""
    if num_fields <= 3:
        return 1
    elif num_fields <= 8:
        return 2
    else:
        return 3


def _build_all_tasks() -> Dict[str, FormGenerationTask]:
    """Build every task from FORM_SPECS + overrides table."""
    tasks: Dict[str, FormGenerationTask] = {}

    for (lang_code, pos_type), spec in sorted(FORM_SPECS.items()):
        lang_name = LANG_NAMES.get(lang_code, spec.language_name)
        task_key = f"{lang_name.lower()}_{pos_type}s"

        overrides = _TASK_OVERRIDES.get((lang_code, pos_type), {})

        base_form = overrides.get("base_form", _compute_base_form(spec.form_fields))
        threshold = overrides.get("threshold", _compute_threshold(len(spec.form_fields)))
        client_method = overrides.get("client_method", "query_language_forms")
        extract_gender = overrides.get("gender", False)
        fetcher_type = overrides.get("fetcher", "needs_forms")

        config = FormGenerationConfig(
            language_code=lang_code,
            language_name=lang_name,
            pos_type=pos_type,
            form_mapping=spec.form_mapping,
            client_method_name=client_method,
            min_forms_threshold=threshold,
            base_form_identifier=base_form,
            use_legacy_translation=False,
            translation_field_name=None,
            extract_gender=extract_gender,
        )

        if fetcher_type == "translation":
            tasks[task_key] = _translation_task(config)
        else:
            tasks[task_key] = _needs_forms_task(config)

    return tasks


FORM_GENERATION_TASKS: Dict[str, FormGenerationTask] = _build_all_tasks()


def run_form_generation_task(task_key: str) -> None:
    """Run a registered task by key."""
    if task_key not in FORM_GENERATION_TASKS:
        raise KeyError(f"Unknown form generation task: {task_key}")

    task = FORM_GENERATION_TASKS[task_key]
    run_form_generation(task.config, task.lemma_fetcher)


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
) -> bool:
    """Process a single lemma for a registered task."""

    if task_key not in FORM_GENERATION_TASKS:
        raise KeyError(f"Unknown form generation task: {task_key}")

    task = FORM_GENERATION_TASKS[task_key]
    client = client or LinguisticClient(config=data_config)
    return process_lemma_forms(client, lemma_id, data_config, task.config)
