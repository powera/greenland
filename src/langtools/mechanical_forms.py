"""Rule-based paradigms per language, for bootstrap and the release export.

``words.mechanical_forms`` writes the forms the rules can
derive, and ``storage.release.mechanical_filter`` keeps exactly those out of
``data/release``; both ask this module for the paradigm, so they cannot drift.

A language with rules has ``langtools/<lang>/mechanical.py`` exposing:

``POS_TYPES``
    The parts of speech it builds.
``BASE_FORM_KEYS``
    POS -> the builder key of the form marked ``is_base_form``.
``build_paradigm(session, lemma, pos_type, language_code, word)``
    Returns ``(forms, metadata)``: builder key -> text, or ``None`` when the
    rules decline this word, plus any grammar facts the builder inferred
    (Lithuanian gender).  It reads the lemma's grammar facts itself.

and optionally:

``USES_LEMMA_TEXT = True``
    The word is the lemma text (English) rather than its translation.
``FORM_KEYS``
    POS -> builder key -> GrammaticalForm value, for builders whose keys do
    not match the enum.  Otherwise the value is ``<pos>/<lang>_<key>``.
``build_variant_paradigm(session, lemma, pos_type, text)``
    Inflects a spelling variant's base form.

A storage dialect declared in its parent's forms_config
(``DIALECT_LANGUAGE_NAMES``) uses the parent's module with its own language
code and its own translation.
"""

import importlib
from functools import lru_cache
from pathlib import Path
from types import ModuleType
from typing import Any, Dict, Optional, Tuple

from sqlalchemy.orm import Session

Paradigm = Tuple[Optional[Dict[str, str]], Dict[str, str]]


def read_facts(
    session: Session, lemma_id: int, language_code: str, *fact_types: str
) -> Tuple[Optional[str], ...]:
    """Read several grammar facts for a lemma in one call."""
    from storage.crud.grammar_fact import get_grammar_fact_value

    return tuple(
        get_grammar_fact_value(session, lemma_id, language_code, fact_type)
        for fact_type in fact_types
    )


def is_mechanically_safe_translation(word: str) -> bool:
    """Whether *word* is a single, lowercase word safe to inflect by rule.

    Multi-word translations ("teikti pirmenybę", "en colère") and proper nouns
    ("Varšuva") must not be inflected mechanically. The Lithuanian conjugator
    logs a warning for an infinitive that does not end in -ti/-tis but still
    returns a paradigm built from the truncated stem, which silently drops the
    second word -- so the caller has to refuse these rather than rely on the
    builder returning None.
    """
    word = word.strip()
    if not word or " " in word:
        return False
    return word == word.lower()


@lru_cache(maxsize=1)
def _modules() -> Dict[str, ModuleType]:
    """Language code -> its mechanical module, dialects included."""
    modules: Dict[str, ModuleType] = {}
    langtools_dir = Path(__file__).resolve().parent
    for module_path in sorted(langtools_dir.glob("*/mechanical.py")):
        lang_dir = module_path.parent.name
        module = importlib.import_module(f"langtools.{lang_dir}.mechanical")
        modules[lang_dir] = module
        forms_config = importlib.import_module(f"langtools.{lang_dir}.forms_config")
        dialects = getattr(forms_config, "DIALECT_LANGUAGE_NAMES", None)
        if isinstance(dialects, dict):
            for dialect_code in dialects:
                modules[str(dialect_code)] = module
    return modules


def supported() -> Dict[str, Tuple[str, ...]]:
    """Language -> the parts of speech its rules build."""
    return {code: tuple(module.POS_TYPES) for code, module in _modules().items()}


def base_form_keys() -> Dict[Tuple[str, str], str]:
    """(language, POS) -> the builder key of the base form."""
    return {
        (code, pos_type): key
        for code, module in _modules().items()
        for pos_type, key in module.BASE_FORM_KEYS.items()
    }


def build_for_lemma_with_metadata(session: Session, lemma: Any, language_code: str) -> Paradigm:
    """Return the mechanical paradigm for *lemma* and its paradigm metadata."""
    from storage.translation_helpers import get_translation

    module = _modules().get(language_code)
    pos_type = lemma.pos_type.lower()
    if module is None or pos_type not in module.POS_TYPES:
        return None, {}

    if getattr(module, "USES_LEMMA_TEXT", False):
        word = lemma.lemma_text
    else:
        translation = get_translation(session, lemma, language_code)
        if not translation or not is_mechanically_safe_translation(translation):
            return None, {}
        word = translation.strip()

    paradigm: Paradigm = module.build_paradigm(session, lemma, pos_type, language_code, word)
    return paradigm


def build_variant_paradigm(
    session: Session, lemma: Any, language_code: str, text: str
) -> Optional[Dict[str, str]]:
    """Inflect a spelling variant, or None if the language has no variant rules."""
    module = _modules().get(language_code)
    builder = getattr(module, "build_variant_paradigm", None) if module else None
    if builder is None:
        return None
    result: Optional[Dict[str, str]] = builder(session, lemma, lemma.pos_type.lower(), text)
    return result


@lru_cache(maxsize=1)
def _valid_grammatical_forms() -> frozenset[str]:
    from storage.models.enums import GrammaticalForm

    return frozenset(member.value for member in GrammaticalForm)


def resolve_grammatical_form(language_code: str, pos_type: str, form_key: str) -> Optional[str]:
    """Map a builder's output key to a GrammaticalForm value, or None to skip."""
    module = _modules().get(language_code)
    form_keys = getattr(module, "FORM_KEYS", None) if module else None
    if form_keys is not None:
        value: Optional[str] = form_keys.get(pos_type, {}).get(form_key)
        return value

    candidate = f"{pos_type}/{language_code}_{form_key}"
    return candidate if candidate in _valid_grammatical_forms() else None
