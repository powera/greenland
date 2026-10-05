"""Per-language settings for form generation, and the entry point that runs it.

Each ``langtools/<lang>/forms_config.py`` may declare ``FORM_TASK_SETTINGS``, a
dict keyed by part of speech.  Every key is optional:

``fetcher``
    ``"translation"`` to work through lemmas that have a translation in the
    language, or ``"needs_forms"`` (the default) for lemmas missing forms.
``threshold``
    How many of the slots a lemma must already have to count as done.  The
    default scales with the number of slots.
``base_form``
    The slot marked ``is_base_form``.  The default is the first of singular,
    nominative singular, 1s present, ... that the language has.
``extract_gender``
    Read the noun's gender off its generated forms (article or ending) and
    store it as a grammar fact.  Only for languages whose forms carry it.
``generator``
    The name of a function in ``langtools.<lang>.llm_forms`` that produces the
    forms -- typically rules first, then the LLM.  Without it, forms come
    straight from the LLM (``llm_forms_base.query_forms``).
``on_demand``
    Whether Vilkas ``--fix`` and Barsukas may generate this part of speech for
    a chosen lemma.  The batch tasks run regardless.

A storage dialect (``DIALECT_LANGUAGE_NAMES`` in its parent's forms_config)
shares its parent's settings, and its generator is called with
``language_code=<dialect>``.
"""

import importlib
import importlib.util
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

TaskSettings = Dict[str, Any]
FormsResult = Tuple[Dict[str, str], bool]


@lru_cache(maxsize=1)
def _load() -> Tuple[Dict[Tuple[str, str], TaskSettings], Dict[str, str]]:
    """Return (settings by (language, pos), module language by language)."""
    settings: Dict[Tuple[str, str], TaskSettings] = {}
    module_language: Dict[str, str] = {}
    langtools_dir = Path(__file__).resolve().parent
    for config_path in sorted(langtools_dir.glob("*/forms_config.py")):
        lang_dir = config_path.parent.name
        spec = importlib.util.spec_from_file_location(
            f"langtools.{lang_dir}.forms_config", config_path
        )
        if spec is None or spec.loader is None:
            continue
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        task_settings = getattr(module, "FORM_TASK_SETTINGS", None)
        if not isinstance(task_settings, dict):
            continue
        language_code: str = getattr(module, "LANGUAGE_CODE", lang_dir)
        codes: List[str] = [language_code]
        dialects = getattr(module, "DIALECT_LANGUAGE_NAMES", None)
        if isinstance(dialects, dict):
            codes.extend(str(code) for code in dialects)
        for code in codes:
            module_language[code] = lang_dir
            for pos_type, pos_settings in task_settings.items():
                settings[(code, pos_type)] = dict(pos_settings)
    return settings, module_language


def get_task_settings(language_code: str, pos_type: str) -> TaskSettings:
    """Return the declared settings for one language and part of speech (maybe empty)."""
    return dict(_load()[0].get((language_code, pos_type), {}))


# Slots tried, in order, when a language declares no ``base_form`` setting.
_DEFAULT_BASE_FORM_CANDIDATES: Tuple[str, ...] = (
    "singular",
    "nominative_singular",
    "1s_present",
    "present",
    "polite_present",
    "masu",
    "positive",
)


def compute_default_base_form(form_fields: List[str]) -> str:
    """The base slot for a spec whose language declares no ``base_form``."""
    if form_fields[0] == "base":
        return "base"
    for candidate in _DEFAULT_BASE_FORM_CANDIDATES:
        if candidate in form_fields:
            return candidate
    return form_fields[0]


def get_base_form_field(language_code: str, pos_type: str) -> Optional[str]:
    """The spec field marked ``is_base_form`` for this language and POS.

    None when the language has no form spec for *pos_type*.
    """
    from langtools.form_registry import FORM_SPECS

    spec = FORM_SPECS.get((language_code, pos_type))
    if spec is None or not spec.form_fields:
        return None
    base_field = get_task_settings(language_code, pos_type).get("base_form")
    return str(base_field) if base_field else compute_default_base_form(spec.form_fields)


def get_base_grammatical_form(language_code: str, pos_type: str) -> Optional[str]:
    """The GrammaticalForm value of the base slot, e.g. ``adjective/es_singular_m``.

    This is the label the forms workflow stores on the ``is_base_form`` row,
    i.e. the specific name of the form that ``base_target`` holds.
    """
    from langtools.form_registry import FORM_SPECS

    base_field = get_base_form_field(language_code, pos_type)
    if base_field is None:
        return None
    form = FORM_SPECS[(language_code, pos_type)].form_mapping.get(base_field)
    return str(form.value) if form is not None else None


def get_on_demand_pos_types() -> Dict[str, List[str]]:
    """Language -> parts of speech that may be generated for a chosen lemma."""
    pos_types: Dict[str, List[str]] = {}
    for (language_code, pos_type), task_settings in _load()[0].items():
        if task_settings.get("on_demand"):
            pos_types.setdefault(language_code, []).append(pos_type)
    return pos_types


def _generator(language_code: str, pos_type: str) -> Optional[Callable[..., FormsResult]]:
    name = get_task_settings(language_code, pos_type).get("generator")
    if not name:
        return None
    module_language = _load()[1][language_code]
    module = importlib.import_module(f"langtools.{module_language}.llm_forms")
    generator: Callable[..., FormsResult] = getattr(module, name)
    return generator


def get_generator_name(language_code: str, pos_type: str) -> str:
    """The generator a run will use, for logs: the function name, or ``query_forms``."""
    return str(get_task_settings(language_code, pos_type).get("generator") or "query_forms")


def generate_forms(
    language_code: str,
    pos_type: str,
    client: Any,
    lemma_id: int,
    get_session_func: Callable[[], Session],
) -> FormsResult:
    """Produce the forms of one lemma in one language.

    *client* is a ``clients.unified_client.UnifiedLLMClient``.  Uses the
    language's declared generator if it has one, otherwise asks the LLM.
    """
    generator = _generator(language_code, pos_type)
    if generator is None:
        from langtools.form_registry import FORM_SPECS
        from langtools.llm_forms_base import query_forms

        return query_forms(
            FORM_SPECS[(language_code, pos_type)], client, lemma_id, get_session_func
        )
    if _load()[1][language_code] != language_code:
        return generator(client, lemma_id, get_session_func, language_code=language_code)
    return generator(client, lemma_id, get_session_func)
