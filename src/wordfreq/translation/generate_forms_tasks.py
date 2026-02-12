"""Registry of form generation tasks using shared base logic.

This module centralizes language/part-of-speech configuration so callers
can invoke a single entry point instead of a proliferation of thin
scripts.
"""

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from storage.backend.config import DataSourceConfig
from wordfreq.translation.client import LinguisticClient
from wordfreq.translation.generate_forms_base import (
    FormGenerationConfig,
    get_lemmas_needing_forms,
    get_lemmas_with_translation,
    process_lemma_forms,
    run_form_generation,
)
from langtools.en.llm_forms import (
    ADJECTIVE_FORM_MAPPING as EN_ADJECTIVE_FORM_MAPPING,
)
from langtools.en.llm_forms import (
    ADVERB_FORM_MAPPING as EN_ADVERB_FORM_MAPPING,
)
from langtools.en.llm_forms import NOUN_FORM_MAPPING as EN_NOUN_FORM_MAPPING
from langtools.en.llm_forms import VERB_FORM_MAPPING as EN_VERB_FORM_MAPPING
from langtools.fr.llm_forms import NOUN_FORM_MAPPING as FR_NOUN_FORM_MAPPING
from langtools.fr.llm_forms import VERB_FORM_MAPPING as FR_VERB_FORM_MAPPING
from langtools.de.llm_forms import NOUN_FORM_MAPPING as DE_NOUN_FORM_MAPPING
from langtools.de.llm_forms import VERB_FORM_MAPPING as DE_VERB_FORM_MAPPING
from langtools.lt.llm_forms import (
    ADJECTIVE_FORM_MAPPING as LT_ADJECTIVE_FORM_MAPPING,
)
from langtools.lt.llm_forms import (
    ADVERB_FORM_MAPPING as LT_ADVERB_FORM_MAPPING,
)
from langtools.lt.llm_forms import NOUN_FORM_MAPPING as LT_NOUN_FORM_MAPPING
from langtools.lt.llm_forms import VERB_FORM_MAPPING as LT_VERB_FORM_MAPPING
from langtools.pt.llm_forms import NOUN_FORM_MAPPING as PT_NOUN_FORM_MAPPING
from langtools.pt.llm_forms import VERB_FORM_MAPPING as PT_VERB_FORM_MAPPING
from langtools.nl.llm_forms import NOUN_FORM_MAPPING as NL_NOUN_FORM_MAPPING
from langtools.nl.llm_forms import VERB_FORM_MAPPING as NL_VERB_FORM_MAPPING
from langtools.it.llm_forms import NOUN_FORM_MAPPING as IT_NOUN_FORM_MAPPING
from langtools.it.llm_forms import VERB_FORM_MAPPING as IT_VERB_FORM_MAPPING
from langtools.es.llm_forms import NOUN_FORM_MAPPING as ES_NOUN_FORM_MAPPING
from langtools.es.llm_forms import VERB_FORM_MAPPING as ES_VERB_FORM_MAPPING
from langtools.sv.llm_forms import NOUN_FORM_MAPPING as SV_NOUN_FORM_MAPPING
from langtools.sv.llm_forms import VERB_FORM_MAPPING as SV_VERB_FORM_MAPPING
from langtools.zh.llm_forms import NOUN_FORM_MAPPING as ZH_NOUN_FORM_MAPPING
from langtools.zh.llm_forms import VERB_FORM_MAPPING as ZH_VERB_FORM_MAPPING
from langtools.ja.llm_forms import NOUN_FORM_MAPPING as JA_NOUN_FORM_MAPPING
from langtools.ja.llm_forms import VERB_FORM_MAPPING as JA_VERB_FORM_MAPPING
from langtools.ko.llm_forms import NOUN_FORM_MAPPING as KO_NOUN_FORM_MAPPING
from langtools.ko.llm_forms import VERB_FORM_MAPPING as KO_VERB_FORM_MAPPING
from langtools.vi.llm_forms import NOUN_FORM_MAPPING as VI_NOUN_FORM_MAPPING
from langtools.vi.llm_forms import VERB_FORM_MAPPING as VI_VERB_FORM_MAPPING


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
            base_form_identifier="1s_present",
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
            min_forms_threshold=2,
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
            base_form_identifier="1s_present",
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
            base_form_identifier="1s_present",
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
            base_form_identifier="1s_present",
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
            min_forms_threshold=2,
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
            base_form_identifier="1s_present",
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
            min_forms_threshold=2,
            base_form_identifier="singular",
            use_legacy_translation=True,
            translation_field_name="spanish_translation",
            extract_gender=True,
        )
    ),
    # Italian
    "italian_verbs": _translation_task(
        FormGenerationConfig(
            language_code="it",
            language_name="Italian",
            pos_type="verb",
            form_mapping=IT_VERB_FORM_MAPPING,
            client_method_name="query_italian_verb_conjugations",
            min_forms_threshold=10,
            base_form_identifier="1s_present",
            use_legacy_translation=False,
        )
    ),
    "italian_nouns": _translation_task(
        FormGenerationConfig(
            language_code="it",
            language_name="Italian",
            pos_type="noun",
            form_mapping=IT_NOUN_FORM_MAPPING,
            client_method_name="query_italian_noun_forms",
            min_forms_threshold=2,
            base_form_identifier="singular",
            use_legacy_translation=False,
            extract_gender=True,
        )
    ),
    # Swedish
    "swedish_verbs": _translation_task(
        FormGenerationConfig(
            language_code="sv",
            language_name="Swedish",
            pos_type="verb",
            form_mapping=SV_VERB_FORM_MAPPING,
            client_method_name="query_swedish_verb_conjugations",
            min_forms_threshold=2,
            base_form_identifier="present",
            use_legacy_translation=False,
        )
    ),
    "swedish_nouns": _translation_task(
        FormGenerationConfig(
            language_code="sv",
            language_name="Swedish",
            pos_type="noun",
            form_mapping=SV_NOUN_FORM_MAPPING,
            client_method_name="query_swedish_noun_forms",
            min_forms_threshold=2,
            base_form_identifier="singular",
            use_legacy_translation=False,
        )
    ),
    # Dutch
    "dutch_verbs": _translation_task(
        FormGenerationConfig(
            language_code="nl",
            language_name="Dutch",
            pos_type="verb",
            form_mapping=NL_VERB_FORM_MAPPING,
            client_method_name="query_dutch_verb_conjugations",
            min_forms_threshold=10,
            base_form_identifier="1s_present",
            use_legacy_translation=False,
        )
    ),
    "dutch_nouns": _translation_task(
        FormGenerationConfig(
            language_code="nl",
            language_name="Dutch",
            pos_type="noun",
            form_mapping=NL_NOUN_FORM_MAPPING,
            client_method_name="query_dutch_noun_forms",
            min_forms_threshold=2,
            base_form_identifier="singular",
            use_legacy_translation=False,
            extract_gender=True,
        )
    ),
    # Chinese (isolating - base form only)
    "chinese_nouns": _needs_forms_task(
        FormGenerationConfig(
            language_code="zh",
            language_name="Chinese",
            pos_type="noun",
            form_mapping=ZH_NOUN_FORM_MAPPING,
            client_method_name="query_chinese_noun_forms",
            min_forms_threshold=1,
            base_form_identifier="base",
            use_legacy_translation=False,
        )
    ),
    "chinese_verbs": _needs_forms_task(
        FormGenerationConfig(
            language_code="zh",
            language_name="Chinese",
            pos_type="verb",
            form_mapping=ZH_VERB_FORM_MAPPING,
            client_method_name="query_chinese_verb_forms",
            min_forms_threshold=3,
            base_form_identifier="base",
            use_legacy_translation=False,
        )
    ),
    # Japanese (nouns: base only; verbs: genuine conjugation)
    "japanese_nouns": _needs_forms_task(
        FormGenerationConfig(
            language_code="ja",
            language_name="Japanese",
            pos_type="noun",
            form_mapping=JA_NOUN_FORM_MAPPING,
            client_method_name="query_japanese_noun_forms",
            min_forms_threshold=1,
            base_form_identifier="base",
            use_legacy_translation=False,
        )
    ),
    "japanese_verbs": _needs_forms_task(
        FormGenerationConfig(
            language_code="ja",
            language_name="Japanese",
            pos_type="verb",
            form_mapping=JA_VERB_FORM_MAPPING,
            client_method_name="query_japanese_verb_conjugations",
            min_forms_threshold=3,
            base_form_identifier="masu_form",
            use_legacy_translation=False,
        )
    ),
    # Korean (nouns: base only; verbs: genuine conjugation)
    "korean_nouns": _needs_forms_task(
        FormGenerationConfig(
            language_code="ko",
            language_name="Korean",
            pos_type="noun",
            form_mapping=KO_NOUN_FORM_MAPPING,
            client_method_name="query_korean_noun_forms",
            min_forms_threshold=1,
            base_form_identifier="base",
            use_legacy_translation=False,
        )
    ),
    "korean_verbs": _needs_forms_task(
        FormGenerationConfig(
            language_code="ko",
            language_name="Korean",
            pos_type="verb",
            form_mapping=KO_VERB_FORM_MAPPING,
            client_method_name="query_korean_verb_conjugations",
            min_forms_threshold=2,
            base_form_identifier="polite_present",
            use_legacy_translation=False,
        )
    ),
    # Vietnamese (isolating - base form only)
    "vietnamese_nouns": _needs_forms_task(
        FormGenerationConfig(
            language_code="vi",
            language_name="Vietnamese",
            pos_type="noun",
            form_mapping=VI_NOUN_FORM_MAPPING,
            client_method_name="query_vietnamese_noun_forms",
            min_forms_threshold=1,
            base_form_identifier="base",
            use_legacy_translation=False,
        )
    ),
    "vietnamese_verbs": _needs_forms_task(
        FormGenerationConfig(
            language_code="vi",
            language_name="Vietnamese",
            pos_type="verb",
            form_mapping=VI_VERB_FORM_MAPPING,
            client_method_name="query_vietnamese_verb_forms",
            min_forms_threshold=1,
            base_form_identifier="base",
            use_legacy_translation=False,
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
