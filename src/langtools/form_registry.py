"""Central registry mapping (language_code, pos_type) to LanguageFormSpec.

Replaces the per-language form-mapping definitions that were duplicated across
every ``langtools/<lang>/llm_forms.py`` module.  Each entry in :data:`FORM_SPECS`
fully describes the forms, prompt path, query type, schema name, and enum
mapping for one (language, POS) combination.
"""

import importlib.util
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from clients.types import SchemaProperty
from langtools.form_patterns import expand_enum_names, expand_fields
from langtools.llm_forms_base import LanguageFormSpec
from storage.models.enums import GrammaticalForm

# ---------------------------------------------------------------------------
# Language name mapping
# ---------------------------------------------------------------------------

LANG_NAMES: Dict[str, str] = {
    "am": "Amharic",
    "az": "Azerbaijani",
    "bg": "Bulgarian",
    "bn": "Bengali",
    "cs": "Czech",
    "da": "Danish",
    "de": "German",
    "el": "Greek",
    "en": "English",
    "es": "Spanish",
    "et": "Estonian",
    "fa": "Persian",
    "fi": "Finnish",
    "fr": "French",
    "ga": "Irish",
    "gu": "Gujarati",
    "ha": "Hausa",
    "hi": "Hindi",
    "hr": "Croatian",
    "hu": "Hungarian",
    "hy": "Armenian",
    "id": "Indonesian",
    "ig": "Igbo",
    "it": "Italian",
    "ja": "Japanese",
    "ka": "Georgian",
    "kk": "Kazakh",
    "km": "Khmer",
    "kn": "Kannada",
    "ko": "Korean",
    "lo": "Lao",
    "lt": "Lithuanian",
    "lv": "Latvian",
    "ml": "Malayalam",
    "mr": "Marathi",
    "ms": "Malay",
    "mt": "Maltese",
    "my": "Burmese",
    "nl": "Dutch",
    "om": "Oromo",
    "or": "Odia",
    "pa": "Punjabi",
    "pl": "Polish",
    "ps": "Pashto",
    "pt": "Portuguese",
    "ro": "Romanian",
    "si": "Sinhala",
    "sk": "Slovak",
    "sl": "Slovenian",
    "sn": "Shona",
    "so": "Somali",
    "sv": "Swedish",
    "sw": "Swahili",
    "ta": "Tamil",
    "te": "Telugu",
    "th": "Thai",
    "tl": "Filipino",
    "tr": "Turkish",
    "uk": "Ukrainian",
    "ur": "Urdu",
    "uz": "Uzbek",
    "vi": "Vietnamese",
    "xh": "Xhosa",
    "yo": "Yoruba",
    "zh": "Chinese",
    "zu": "Zulu",
}

# ---------------------------------------------------------------------------
# Persons used in 6-person conjugation patterns
# ---------------------------------------------------------------------------

_PERSONS_6: List[str] = ["1s", "2s", "3s", "1p", "2p", "3p"]


# ---------------------------------------------------------------------------
# Helper: resolve a GrammaticalForm enum member by attribute name
# ---------------------------------------------------------------------------


def _gf(name: str) -> GrammaticalForm:
    """Return GrammaticalForm.<name>, raising AttributeError if missing."""
    return GrammaticalForm[name]


# ---------------------------------------------------------------------------
# Helper functions for common patterns
# ---------------------------------------------------------------------------


def _make_singular_plural_noun_spec(lang_code: str, lang_name: str) -> LanguageFormSpec:
    """Create a LanguageFormSpec for a standard singular/plural noun."""
    upper = lang_code.upper()
    lower_name = lang_name.lower()
    form_mapping: Dict[str, GrammaticalForm] = {
        "singular": _gf(f"NOUN_{upper}_SINGULAR"),
        "plural": _gf(f"NOUN_{upper}_PLURAL"),
    }
    return LanguageFormSpec(
        language_code=lang_code,
        language_name=lang_name,
        pos_type="noun",
        form_mapping=form_mapping,
        form_fields=["singular", "plural"],
        prompt_path=f"{lang_code}/noun",
        query_type=f"{lower_name}_noun_forms",
        schema_name=f"{lang_name}NounForms",
        schema_description=f"{lang_name} noun forms",
    )


def _make_6person_verb_spec(
    lang_code: str,
    lang_name: str,
    tenses: Optional[List[Tuple[str, str]]] = None,
) -> LanguageFormSpec:
    """Create a LanguageFormSpec for a 6-person x 3-tense verb conjugation.

    *tenses* defaults to ``[("present", "present"), ("past", "past"),
    ("future", "future")]``.  Each tuple is ``(tense_suffix, label)``.
    """
    if tenses is None:
        tenses = [("present", "present"), ("past", "past"), ("future", "future")]
    upper = lang_code.upper()
    lower_name = lang_name.lower()

    form_fields: List[str] = []
    form_mapping: Dict[str, GrammaticalForm] = {}
    for tense_suffix, _label in tenses:
        for person in _PERSONS_6:
            field_name = f"{person}_{tense_suffix}"
            form_fields.append(field_name)
            form_mapping[field_name] = _gf(f"VERB_{upper}_{person.upper()}_{tense_suffix.upper()}")

    return LanguageFormSpec(
        language_code=lang_code,
        language_name=lang_name,
        pos_type="verb",
        form_mapping=form_mapping,
        form_fields=form_fields,
        prompt_path=f"{lang_code}/verb",
        query_type=f"{lower_name}_verb_conjugations",
        schema_name=f"{lang_name}VerbConjugations",
        schema_description=f"{lang_name} verb conjugations",
    )


def _make_tense_only_verb_spec(lang_code: str, lang_name: str) -> LanguageFormSpec:
    """Create a LanguageFormSpec for a present/past/future verb (no person)."""
    upper = lang_code.upper()
    lower_name = lang_name.lower()
    form_mapping: Dict[str, GrammaticalForm] = {
        "present": _gf(f"VERB_{upper}_PRESENT"),
        "past": _gf(f"VERB_{upper}_PAST"),
        "future": _gf(f"VERB_{upper}_FUTURE"),
    }
    return LanguageFormSpec(
        language_code=lang_code,
        language_name=lang_name,
        pos_type="verb",
        form_mapping=form_mapping,
        form_fields=["present", "past", "future"],
        prompt_path=f"{lang_code}/verb",
        query_type=f"{lower_name}_verb_forms",
        schema_name=f"{lang_name}VerbForms",
        schema_description=f"{lang_name} verb forms",
    )


# ---------------------------------------------------------------------------
# Build the complete FORM_SPECS dict
# ---------------------------------------------------------------------------

FORM_SPECS: Dict[Tuple[str, str], LanguageFormSpec] = {}


# ===== Pattern A: singular/plural nouns + 6-person verbs =====
# Standard languages with singular/plural nouns and 6-person x 3-tense verbs.
_PATTERN_A_LANGS: List[Tuple[str, str]] = []

for _lc, _ln in _PATTERN_A_LANGS:
    FORM_SPECS[(_lc, "noun")] = _make_singular_plural_noun_spec(_lc, _ln)
    FORM_SPECS[(_lc, "verb")] = _make_6person_verb_spec(_lc, _ln)


# ===== Pattern B: singular/plural nouns + 3-tense verbs =====
# Note: These languages don't have forms_config.py yet, so we skip them.
# The enum members will be created once forms_config.py files are added.
_PATTERN_B_LANGS: List[Tuple[str, str]] = [
    ("az", "Azerbaijani"),
    ("fa", "Persian"),
    ("gu", "Gujarati"),
    ("hy", "Armenian"),
    ("id", "Indonesian"),
    ("ka", "Georgian"),
    ("kk", "Kazakh"),
    ("mr", "Marathi"),
    ("ms", "Malay"),
    ("or", "Odia"),
    ("pa", "Punjabi"),
    ("ps", "Pashto"),
    ("tl", "Filipino"),
    ("tr", "Turkish"),
    ("ur", "Urdu"),
    ("uz", "Uzbek"),
]

# Skip Pattern B for now - these will be handled by forms_config.py files
# for _lc, _ln in _PATTERN_B_LANGS:
#     FORM_SPECS[(_lc, "noun")] = _make_singular_plural_noun_spec(_lc, _ln)
#     FORM_SPECS[(_lc, "verb")] = _make_tense_only_verb_spec(_lc, _ln)


# ===== Config-driven languages =====
# All Asian languages, Latvian, Ukrainian, Polish, Thai, and others are
# auto-discovered below from their langtools/*/forms_config.py files.


# ---------------------------------------------------------------------------
# Auto-discover langtools/*/forms_config.py and build FORM_SPECS entries
# ---------------------------------------------------------------------------

_POS_TYPE_MAP: Dict[str, str] = {
    "noun": "noun",
    "verb": "verb",
    "adjective": "adjective",
    "adverb": "adverb",
}

# POS-specific naming for query_type / schema_name suffixes
_POS_QUERY_SUFFIX: Dict[str, str] = {
    "noun": "forms",
    "verb": "conjugations",
    "adjective": "declensions",
    "adverb": "forms",
}


def _build_spec_from_config(
    lang_code: str,
    lang_name: str,
    pos_type: str,
    config: Dict[str, Any],
) -> LanguageFormSpec:
    """Build a :class:`LanguageFormSpec` from a forms_config dict."""
    fields = expand_fields(config)
    enum_names = expand_enum_names(config, lang_code, pos_type)
    form_mapping: Dict[str, GrammaticalForm] = {field: _gf(enum_names[field]) for field in fields}

    # extra_schema_properties from config["extra_schema"]
    extra_props: Optional[Dict[str, SchemaProperty]] = None
    if "extra_schema" in config:
        extra_props = {}
        for prop_name, prop_def in config["extra_schema"].items():
            type_str, description, *rest = prop_def
            enum_vals = rest[0] if rest else None
            extra_props[prop_name] = SchemaProperty(type_str, description, enum=enum_vals)

    query_type = config.get("query_type", f"{lang_name.lower()}_{pos_type}_forms")
    schema_name = config.get("schema_name", f"{lang_name}{pos_type.capitalize()}Forms")
    schema_desc = config.get(
        "schema_description",
        f"{lang_name} {pos_type} {'declensions' if pos_type in ('noun', 'adjective') else 'forms'}",
    )
    if pos_type == "verb" and "schema_description" not in config:
        schema_desc = f"{lang_name} verb conjugations"

    return LanguageFormSpec(
        language_code=lang_code,
        language_name=lang_name,
        pos_type=pos_type,
        form_mapping=form_mapping,
        form_fields=fields,
        prompt_path=config.get("prompt_path", f"{lang_code}/{pos_type}"),
        query_type=query_type,
        schema_name=schema_name,
        schema_description=schema_desc,
        extra_schema_properties=extra_props,
        form_descriptions=config.get("form_descriptions"),
        is_source_language=config.get("is_source_language", False),
        word_variable=config.get("word_variable"),
    )


def _auto_register_from_forms_configs() -> None:
    """Scan langtools/*/forms_config.py and register missing FORM_SPECS entries."""
    langtools_dir = Path(__file__).resolve().parent
    if not langtools_dir.is_dir():
        return

    for config_path in sorted(langtools_dir.glob("*/forms_config.py")):
        lang_dir = config_path.parent.name
        mod_name = f"langtools.{lang_dir}.forms_config"
        try:
            spec = importlib.util.spec_from_file_location(mod_name, config_path)
            if spec is None or spec.loader is None:
                continue
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
        except Exception:
            continue

        lang_code: str = getattr(mod, "LANGUAGE_CODE", lang_dir)
        lang_name: str = getattr(mod, "LANGUAGE_NAME", lang_dir.capitalize())

        for attr_name in sorted(dir(mod)):
            if not attr_name.endswith("_CONFIG"):
                continue
            cfg = getattr(mod, attr_name)
            if not isinstance(cfg, dict) or "type" not in cfg:
                continue
            pos_type = attr_name.removesuffix("_CONFIG").lower()
            if pos_type not in _POS_TYPE_MAP:
                continue

            spec_key = (lang_code, pos_type)
            if spec_key in FORM_SPECS:
                continue  # hand-coded entry takes precedence

            FORM_SPECS[spec_key] = _build_spec_from_config(lang_code, lang_name, pos_type, cfg)


_auto_register_from_forms_configs()
