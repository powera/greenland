"""Registry of form generation tasks using shared base logic.

This module centralizes language/part-of-speech configuration so callers
can invoke a single entry point instead of a proliferation of thin
scripts.
"""
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

from wordfreq.translation.client import LinguisticClient
from wordfreq.translation.generate_forms_base import process_lemma_forms
from wordfreq.storage.backend.config import DataSourceConfig
from wordfreq.translation.generate_forms_base import (
    FormGenerationConfig,
    get_lemmas_needing_forms,
    get_lemmas_with_translation,
    run_form_generation,
)
from wordfreq.translation.language_forms.english import (
    ADJECTIVE_FORM_MAPPING as EN_ADJECTIVE_FORM_MAPPING,
    ADVERB_FORM_MAPPING as EN_ADVERB_FORM_MAPPING,
    NOUN_FORM_MAPPING as EN_NOUN_FORM_MAPPING,
    VERB_FORM_MAPPING as EN_VERB_FORM_MAPPING,
)
from wordfreq.translation.language_forms.french import (
    NOUN_FORM_MAPPING as FR_NOUN_FORM_MAPPING,
    VERB_FORM_MAPPING as FR_VERB_FORM_MAPPING,
)
from wordfreq.translation.language_forms.german import (
    NOUN_FORM_MAPPING as DE_NOUN_FORM_MAPPING,
    VERB_FORM_MAPPING as DE_VERB_FORM_MAPPING,
)
from wordfreq.translation.language_forms.lithuanian import (
    ADJECTIVE_FORM_MAPPING as LT_ADJECTIVE_FORM_MAPPING,
    ADVERB_FORM_MAPPING as LT_ADVERB_FORM_MAPPING,
    NOUN_FORM_MAPPING as LT_NOUN_FORM_MAPPING,
    VERB_FORM_MAPPING as LT_VERB_FORM_MAPPING,
)
from wordfreq.translation.language_forms.portuguese import (
    NOUN_FORM_MAPPING as PT_NOUN_FORM_MAPPING,
    VERB_FORM_MAPPING as PT_VERB_FORM_MAPPING,
)
from wordfreq.translation.language_forms.spanish import (
    NOUN_FORM_MAPPING as ES_NOUN_FORM_MAPPING,
    VERB_FORM_MAPPING as ES_VERB_FORM_MAPPING,
)


@dataclass
class FormGenerationTask:
    """Describe a form generation workflow."""

    config: FormGenerationConfig
    lemma_fetcher: Callable[[DataSourceConfig, Optional[int]], List[Dict]]


def _translation_task(
    config: FormGenerationConfig,
) -> FormGenerationTask:
    return FormGenerationTask(
        config=config,
        lemma_fetcher=lambda data_config, limit=None: get_lemmas_with_translation(
            data_config, config, limit
        ),
    )


def _needs_forms_task(
    config: FormGenerationConfig,
) -> FormGenerationTask:
    return FormGenerationTask(
        config=config,
        lemma_fetcher=lambda data_config, limit=None: get_lemmas_needing_forms(
            data_config, config, limit
        ),
    )


FORM_GENERATION_TASKS: Dict[str, FormGenerationTask] = {
    # English
    "english_nouns": _needs_forms_task(
        FormGenerationConfig(
            language_code="en",
            language_name="English",
            pos_type="noun",
            form_mapping=EN_NOUN_FORM_MAPPING,
            client_method_name="query_english_noun_forms",
            min_forms_threshold=1,
            base_form_identifier="singular",
            use_legacy_translation=False,
            translation_field_name=None,
            extract_gender=False,
        )
    ),
    "english_verbs": _needs_forms_task(
        FormGenerationConfig(
            language_code="en",
            language_name="English",
            pos_type="verb",
            form_mapping=EN_VERB_FORM_MAPPING,
            client_method_name="query_english_verb_forms",
            min_forms_threshold=5,
            base_form_identifier="infinitive",
            use_legacy_translation=False,
            translation_field_name=None,
            extract_gender=False,
        )
    ),
    "english_adjectives": _needs_forms_task(
        FormGenerationConfig(
            language_code="en",
            language_name="English",
            pos_type="adjective",
            form_mapping=EN_ADJECTIVE_FORM_MAPPING,
            client_method_name="query_english_adjective_forms",
            min_forms_threshold=2,
            base_form_identifier="positive",
            use_legacy_translation=False,
            translation_field_name=None,
            extract_gender=False,
        )
    ),
    "english_adverbs": _needs_forms_task(
        FormGenerationConfig(
            language_code="en",
            language_name="English",
            pos_type="adverb",
            form_mapping=EN_ADVERB_FORM_MAPPING,
            client_method_name="query_english_adverb_forms",
            min_forms_threshold=2,
            base_form_identifier="positive",
            use_legacy_translation=False,
            translation_field_name=None,
            extract_gender=False,
        )
    ),
    # French
    "french_verbs": _translation_task(
        FormGenerationConfig(
            language_code="fr",
            language_name="French",
            pos_type="verb",
            form_mapping=FR_VERB_FORM_MAPPING,
            client_method_name="query_french_verb_conjugations",
            min_forms_threshold=25,
            base_form_identifier="1s_pres",
            use_legacy_translation=True,
            translation_field_name="french_translation",
        )
    ),
    "french_nouns": _translation_task(
        FormGenerationConfig(
            language_code="fr",
            language_name="French",
            pos_type="noun",
            form_mapping=FR_NOUN_FORM_MAPPING,
            client_method_name="query_french_noun_forms",
            min_forms_threshold=3,
            base_form_identifier="singular",
            use_legacy_translation=True,
            translation_field_name="french_translation",
            extract_gender=True,
        )
    ),
    # German
    "german_verbs": _translation_task(
        FormGenerationConfig(
            language_code="de",
            language_name="German",
            pos_type="verb",
            form_mapping=DE_VERB_FORM_MAPPING,
            client_method_name="query_german_verb_conjugations",
            min_forms_threshold=10,
            base_form_identifier="1s_pres",
            use_legacy_translation=True,
            translation_field_name="german_translation",
        )
    ),
    "german_nouns": _translation_task(
        FormGenerationConfig(
            language_code="de",
            language_name="German",
            pos_type="noun",
            form_mapping=DE_NOUN_FORM_MAPPING,
            client_method_name="query_german_noun_forms",
            min_forms_threshold=3,
            base_form_identifier="singular",
            use_legacy_translation=True,
            translation_field_name="german_translation",
            extract_gender=True,
        )
    ),
    # Lithuanian
    "lithuanian_verbs": _translation_task(
        FormGenerationConfig(
            language_code="lt",
            language_name="Lithuanian",
            pos_type="verb",
            form_mapping=LT_VERB_FORM_MAPPING,
            client_method_name="query_lithuanian_verb_conjugations",
            min_forms_threshold=6,
            base_form_identifier="1s_pres",
            use_legacy_translation=True,
            translation_field_name="lithuanian_translation",
        )
    ),
    "lithuanian_nouns": _translation_task(
        FormGenerationConfig(
            language_code="lt",
            language_name="Lithuanian",
            pos_type="noun",
            form_mapping=LT_NOUN_FORM_MAPPING,
            client_method_name="query_lithuanian_noun_declensions",
            min_forms_threshold=3,
            base_form_identifier="nominative_singular",
            use_legacy_translation=True,
            translation_field_name="lithuanian_translation",
        )
    ),
    "lithuanian_adjectives": _translation_task(
        FormGenerationConfig(
            language_code="lt",
            language_name="Lithuanian",
            pos_type="adjective",
            form_mapping=LT_ADJECTIVE_FORM_MAPPING,
            client_method_name="query_lithuanian_adjective_declensions",
            min_forms_threshold=4,
            base_form_identifier="nominative_singular_m",
            use_legacy_translation=True,
            translation_field_name="lithuanian_translation",
        )
    ),
    "lithuanian_adverbs": _translation_task(
        FormGenerationConfig(
            language_code="lt",
            language_name="Lithuanian",
            pos_type="adverb",
            form_mapping=LT_ADVERB_FORM_MAPPING,
            client_method_name="query_lithuanian_adverb_forms",
            min_forms_threshold=1,
            base_form_identifier="positive",
            use_legacy_translation=True,
            translation_field_name="lithuanian_translation",
        )
    ),
    # Portuguese
    "portuguese_verbs": _translation_task(
        FormGenerationConfig(
            language_code="pt",
            language_name="Portuguese",
            pos_type="verb",
            form_mapping=PT_VERB_FORM_MAPPING,
            client_method_name="query_portuguese_verb_conjugations",
            min_forms_threshold=10,
            base_form_identifier="1s_pres",
            use_legacy_translation=True,
            translation_field_name="portuguese_translation",
        )
    ),
    "portuguese_nouns": _translation_task(
        FormGenerationConfig(
            language_code="pt",
            language_name="Portuguese",
            pos_type="noun",
            form_mapping=PT_NOUN_FORM_MAPPING,
            client_method_name="query_portuguese_noun_forms",
            min_forms_threshold=3,
            base_form_identifier="singular",
            use_legacy_translation=True,
            translation_field_name="portuguese_translation",
            extract_gender=True,
        )
    ),
    # Spanish
    "spanish_verbs": _translation_task(
        FormGenerationConfig(
            language_code="es",
            language_name="Spanish",
            pos_type="verb",
            form_mapping=ES_VERB_FORM_MAPPING,
            client_method_name="query_spanish_verb_conjugations",
            min_forms_threshold=10,
            base_form_identifier="1s_pres",
            use_legacy_translation=True,
            translation_field_name="spanish_translation",
        )
    ),
    "spanish_nouns": _translation_task(
        FormGenerationConfig(
            language_code="es",
            language_name="Spanish",
            pos_type="noun",
            form_mapping=ES_NOUN_FORM_MAPPING,
            client_method_name="query_spanish_noun_forms",
            min_forms_threshold=3,
            base_form_identifier="singular",
            use_legacy_translation=True,
            translation_field_name="spanish_translation",
            extract_gender=True,
        )
    ),
}


def run_form_generation_task(task_key: str) -> None:
    """Run a registered task by key."""
    if task_key not in FORM_GENERATION_TASKS:
        raise KeyError(f"Unknown form generation task: {task_key}")

    task = FORM_GENERATION_TASKS[task_key]
    run_form_generation(task.config, task.lemma_fetcher)


def get_task_key(language_code: str, pos_type: str) -> str:
    """Resolve a task key for a language/POS combination."""

    for key, task in FORM_GENERATION_TASKS.items():
        if (
            task.config.language_code == language_code
            and task.config.pos_type == pos_type
        ):
            return key

    raise KeyError(f"No task registered for {language_code} {pos_type}")


def process_lemma_for_task(
    task_key: str, lemma_id: int, data_config: DataSourceConfig, client: LinguisticClient = None
) -> bool:
    """Process a single lemma for a registered task."""

    if task_key not in FORM_GENERATION_TASKS:
        raise KeyError(f"Unknown form generation task: {task_key}")

    task = FORM_GENERATION_TASKS[task_key]
    client = client or LinguisticClient(config=data_config)
    return process_lemma_forms(client, lemma_id, data_config, task.config)
