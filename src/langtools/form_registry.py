"""Central registry mapping (language_code, pos_type) to LanguageFormSpec.

Replaces the per-language form-mapping definitions that were duplicated across
every ``langtools/<lang>/llm_forms.py`` module.  Each entry in :data:`FORM_SPECS`
fully describes the forms, prompt path, query type, schema name, and enum
mapping for one (language, POS) combination.
"""

from typing import Dict, List, Optional, Tuple

from clients.types import SchemaProperty
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
    "ha": "Hausa",
    "hi": "Hindi",
    "hr": "Croatian",
    "hu": "Hungarian",
    "hy": "Armenian",
    "ig": "Igbo",
    "it": "Italian",
    "ja": "Japanese",
    "ka": "Georgian",
    "km": "Khmer",
    "kn": "Kannada",
    "ko": "Korean",
    "lo": "Lao",
    "lt": "Lithuanian",
    "lv": "Latvian",
    "ml": "Malayalam",
    "ms": "Malay",
    "mt": "Maltese",
    "my": "Burmese",
    "nl": "Dutch",
    "om": "Oromo",
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

# Lithuanian 7-case system
_LT_CASES: List[str] = [
    "nominative",
    "genitive",
    "dative",
    "accusative",
    "instrumental",
    "locative",
    "vocative",
]

# German 4-case system
_DE_CASES: List[str] = ["nominative", "accusative", "dative", "genitive"]

# Latvian 7-case system (same cases as Lithuanian)
_LV_CASES: List[str] = [
    "nominative",
    "genitive",
    "dative",
    "accusative",
    "instrumental",
    "locative",
    "vocative",
]

# Polish 7-case system (same as Lithuanian)
_PL_CASES: List[str] = [
    "nominative",
    "genitive",
    "dative",
    "accusative",
    "instrumental",
    "locative",
    "vocative",
]


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


def _make_base_noun_spec(lang_code: str, lang_name: str) -> LanguageFormSpec:
    """Create a LanguageFormSpec for a base-only noun (CJK / isolating)."""
    upper = lang_code.upper()
    lower_name = lang_name.lower()
    form_mapping: Dict[str, GrammaticalForm] = {
        "base": _gf(f"NOUN_{upper}_BASE"),
    }
    return LanguageFormSpec(
        language_code=lang_code,
        language_name=lang_name,
        pos_type="noun",
        form_mapping=form_mapping,
        form_fields=["base"],
        prompt_path=f"{lang_code}/noun",
        query_type=f"{lower_name}_noun_forms",
        schema_name=f"{lang_name}NounForms",
        schema_description=f"{lang_name} noun forms",
    )


# ---------------------------------------------------------------------------
# Build the complete FORM_SPECS dict
# ---------------------------------------------------------------------------

FORM_SPECS: Dict[Tuple[str, str], LanguageFormSpec] = {}


# ===== Pattern A: singular/plural nouns + 6-person verbs =====
# Standard languages with singular/plural nouns and 6-person x 3-tense verbs.
_PATTERN_A_LANGS: List[Tuple[str, str]] = [
    ("fi", "Finnish"),
    ("es", "Spanish"),
    ("pt", "Portuguese"),
    ("it", "Italian"),
    ("nl", "Dutch"),
    ("bg", "Bulgarian"),
    ("cs", "Czech"),
    ("da", "Danish"),
    ("el", "Greek"),
    ("et", "Estonian"),
    ("ga", "Irish"),
    ("hr", "Croatian"),
    ("hu", "Hungarian"),
    ("mt", "Maltese"),
    ("ro", "Romanian"),
    ("si", "Sinhala"),
    ("sk", "Slovak"),
    ("sl", "Slovenian"),
    ("ta", "Tamil"),
    ("te", "Telugu"),
    ("kn", "Kannada"),
    ("ml", "Malayalam"),
]

for _lc, _ln in _PATTERN_A_LANGS:
    FORM_SPECS[(_lc, "noun")] = _make_singular_plural_noun_spec(_lc, _ln)
    FORM_SPECS[(_lc, "verb")] = _make_6person_verb_spec(_lc, _ln)


# ===== Pattern B: singular/plural nouns + 3-tense verbs =====
_PATTERN_B_LANGS: List[Tuple[str, str]] = [
    ("sw", "Swahili"),
    ("hi", "Hindi"),
    ("bn", "Bengali"),
    ("am", "Amharic"),
    ("az", "Azerbaijani"),
    ("fa", "Persian"),
    ("ha", "Hausa"),
    ("hy", "Armenian"),
    ("ig", "Igbo"),
    ("ka", "Georgian"),
    ("km", "Khmer"),
    ("lo", "Lao"),
    ("ms", "Malay"),
    ("my", "Burmese"),
    ("om", "Oromo"),
    ("ps", "Pashto"),
    ("sn", "Shona"),
    ("so", "Somali"),
    ("th", "Thai"),
    ("tl", "Filipino"),
    ("tr", "Turkish"),
    ("uk", "Ukrainian"),
    ("xh", "Xhosa"),
    ("yo", "Yoruba"),
    ("zu", "Zulu"),
]

for _lc, _ln in _PATTERN_B_LANGS:
    FORM_SPECS[(_lc, "noun")] = _make_singular_plural_noun_spec(_lc, _ln)
    FORM_SPECS[(_lc, "verb")] = _make_tense_only_verb_spec(_lc, _ln)


# ===== Pattern C: CJK / isolating languages =====

# --- Chinese ---
FORM_SPECS[("zh", "noun")] = _make_base_noun_spec("zh", "Chinese")

FORM_SPECS[("zh", "verb")] = LanguageFormSpec(
    language_code="zh",
    language_name="Chinese",
    pos_type="verb",
    form_mapping={
        "base": GrammaticalForm.VERB_ZH_BASE,
        "perfective": GrammaticalForm.VERB_ZH_PERFECTIVE,
        "experiential": GrammaticalForm.VERB_ZH_EXPERIENTIAL,
        "progressive": GrammaticalForm.VERB_ZH_PROGRESSIVE,
    },
    form_fields=["base", "perfective", "experiential", "progressive"],
    prompt_path="zh/verb",
    query_type="chinese_verb_forms",
    schema_name="ChineseVerbForms",
    schema_description="Chinese verb forms",
    form_descriptions={
        "base": "bare verb (e.g. 买)",
        "perfective": "verb + 了 — completed action (e.g. 买了)",
        "experiential": "verb + 过 — have done before (e.g. 买过)",
        "progressive": "在 + verb — in progress (e.g. 在买)",
    },
)

# --- Japanese ---
FORM_SPECS[("ja", "noun")] = _make_base_noun_spec("ja", "Japanese")

FORM_SPECS[("ja", "verb")] = LanguageFormSpec(
    language_code="ja",
    language_name="Japanese",
    pos_type="verb",
    form_mapping={
        "masu_form": GrammaticalForm.VERB_JA_MASU,
        "te_form": GrammaticalForm.VERB_JA_TE,
        "ta_form": GrammaticalForm.VERB_JA_TA,
        "nai_form": GrammaticalForm.VERB_JA_NAI,
    },
    form_fields=["masu_form", "te_form", "ta_form", "nai_form"],
    prompt_path="ja/verb",
    query_type="japanese_verb_conjugations",
    schema_name="JapaneseVerbConjugations",
    schema_description="Japanese verb conjugations",
)

# --- Korean ---
FORM_SPECS[("ko", "noun")] = _make_base_noun_spec("ko", "Korean")

FORM_SPECS[("ko", "verb")] = LanguageFormSpec(
    language_code="ko",
    language_name="Korean",
    pos_type="verb",
    form_mapping={
        "polite_present": GrammaticalForm.VERB_KO_POLITE_PRESENT,
        "polite_past": GrammaticalForm.VERB_KO_POLITE_PAST,
        "polite_future": GrammaticalForm.VERB_KO_POLITE_FUTURE,
    },
    form_fields=["polite_present", "polite_past", "polite_future"],
    prompt_path="ko/verb",
    query_type="korean_verb_conjugations",
    schema_name="KoreanVerbConjugations",
    schema_description="Korean verb conjugations",
)

# --- Vietnamese ---
FORM_SPECS[("vi", "noun")] = _make_base_noun_spec("vi", "Vietnamese")

FORM_SPECS[("vi", "verb")] = LanguageFormSpec(
    language_code="vi",
    language_name="Vietnamese",
    pos_type="verb",
    form_mapping={
        "base": GrammaticalForm.VERB_VI_BASE,
    },
    form_fields=["base"],
    prompt_path="vi/verb",
    query_type="vietnamese_verb_forms",
    schema_name="VietnameseVerbForms",
    schema_description="Vietnamese verb forms",
)


# ===== Pattern D: English (source language) =====

FORM_SPECS[("en", "noun")] = LanguageFormSpec(
    language_code="en",
    language_name="English",
    pos_type="noun",
    form_mapping={
        "singular": GrammaticalForm.NOUN_EN_SINGULAR,
        "plural": GrammaticalForm.NOUN_EN_PLURAL,
    },
    form_fields=["singular", "plural"],
    prompt_path="en/noun",
    query_type="english_noun_forms",
    schema_name="EnglishNounForms",
    schema_description="English noun forms",
    is_source_language=True,
    word_variable="noun",
)

FORM_SPECS[("en", "verb")] = LanguageFormSpec(
    language_code="en",
    language_name="English",
    pos_type="verb",
    form_mapping={
        "infinitive": GrammaticalForm.VERB_INFINITIVE,
        "present_participle": GrammaticalForm.VERB_PRESENT_PARTICIPLE,
        "past_participle": GrammaticalForm.VERB_PAST_PARTICIPLE,
        "1s_present": GrammaticalForm.VERB_EN_1S_PRESENT,
        "2s_present": GrammaticalForm.VERB_EN_2S_PRESENT,
        "3s_present": GrammaticalForm.VERB_EN_3S_PRESENT,
        "1p_present": GrammaticalForm.VERB_EN_1P_PRESENT,
        "2p_present": GrammaticalForm.VERB_EN_2P_PRESENT,
        "3p_present": GrammaticalForm.VERB_EN_3P_PRESENT,
        "1s_past": GrammaticalForm.VERB_EN_1S_PAST,
        "2s_past": GrammaticalForm.VERB_EN_2S_PAST,
        "3s_past": GrammaticalForm.VERB_EN_3S_PAST,
        "1p_past": GrammaticalForm.VERB_EN_1P_PAST,
        "2p_past": GrammaticalForm.VERB_EN_2P_PAST,
        "3p_past": GrammaticalForm.VERB_EN_3P_PAST,
        "1s_future": GrammaticalForm.VERB_EN_1S_FUTURE,
        "2s_future": GrammaticalForm.VERB_EN_2S_FUTURE,
        "3s_future": GrammaticalForm.VERB_EN_3S_FUTURE,
        "1p_future": GrammaticalForm.VERB_EN_1P_FUTURE,
        "2p_future": GrammaticalForm.VERB_EN_2P_FUTURE,
        "3p_future": GrammaticalForm.VERB_EN_3P_FUTURE,
        "2s_imp": GrammaticalForm.VERB_EN_2S_IMP,
        "2p_imp": GrammaticalForm.VERB_EN_2P_IMP,
    },
    form_fields=[
        "1s_present",
        "2s_present",
        "3s_present",
        "1p_present",
        "2p_present",
        "3p_present",
        "1s_past",
        "2s_past",
        "3s_past",
        "1p_past",
        "2p_past",
        "3p_past",
        "1s_future",
        "2s_future",
        "3s_future",
        "1p_future",
        "2p_future",
        "3p_future",
        "2s_imp",
        "2p_imp",
    ],
    prompt_path="en/verb",
    query_type="english_verb_conjugations",
    schema_name="EnglishVerbConjugations",
    schema_description="English verb conjugations",
    is_source_language=True,
    word_variable="verb",
)

FORM_SPECS[("en", "adjective")] = LanguageFormSpec(
    language_code="en",
    language_name="English",
    pos_type="adjective",
    form_mapping={
        "positive": GrammaticalForm.ADJ_EN_POSITIVE,
        "comparative": GrammaticalForm.ADJ_EN_COMPARATIVE,
        "superlative": GrammaticalForm.ADJ_EN_SUPERLATIVE,
    },
    form_fields=["positive", "comparative", "superlative"],
    prompt_path="en/adjective",
    query_type="english_adjective_forms",
    schema_name="EnglishAdjectiveForms",
    schema_description="English adjective forms",
    is_source_language=True,
    word_variable="adjective",
)

FORM_SPECS[("en", "adverb")] = LanguageFormSpec(
    language_code="en",
    language_name="English",
    pos_type="adverb",
    form_mapping={
        "positive": GrammaticalForm.ADVERB_EN_POSITIVE,
        "comparative": GrammaticalForm.ADVERB_EN_COMPARATIVE,
        "superlative": GrammaticalForm.ADVERB_EN_SUPERLATIVE,
    },
    form_fields=["positive", "comparative", "superlative"],
    prompt_path="en/adverb",
    query_type="english_adverb_forms",
    schema_name="EnglishAdverbForms",
    schema_description="English adverb forms",
    is_source_language=True,
    word_variable="adverb",
)


# ===== Special cases =====

# --- French: singular/plural nouns with gender, verbs use imperfect ---

FORM_SPECS[("fr", "noun")] = LanguageFormSpec(
    language_code="fr",
    language_name="French",
    pos_type="noun",
    form_mapping={
        "singular": GrammaticalForm.NOUN_FR_SINGULAR,
        "plural": GrammaticalForm.NOUN_FR_PLURAL,
    },
    form_fields=["singular", "plural"],
    prompt_path="fr/noun",
    query_type="french_noun_forms",
    schema_name="FrenchNounForms",
    schema_description="French noun forms with gender",
    extra_schema_properties={
        "gender": SchemaProperty("string", "Gender: 'masculine' or 'feminine'"),
    },
)

_FR_VERB_FIELDS: List[str] = []
_FR_VERB_MAPPING: Dict[str, GrammaticalForm] = {}
for _tense_suffix in ["present", "impf", "future"]:
    for _person in _PERSONS_6:
        _field = f"{_person}_{_tense_suffix}"
        _FR_VERB_FIELDS.append(_field)
        _FR_VERB_MAPPING[_field] = _gf(f"VERB_FR_{_person.upper()}_{_tense_suffix.upper()}")
# Past participle forms
_FR_VERB_FIELDS.extend(["pc_m", "pc_f"])
_FR_VERB_MAPPING["pc_m"] = GrammaticalForm.VERB_FR_PC_M
_FR_VERB_MAPPING["pc_f"] = GrammaticalForm.VERB_FR_PC_F

FORM_SPECS[("fr", "verb")] = LanguageFormSpec(
    language_code="fr",
    language_name="French",
    pos_type="verb",
    form_mapping=_FR_VERB_MAPPING,
    form_fields=_FR_VERB_FIELDS,
    prompt_path="fr/verb",
    query_type="french_verb_conjugations",
    schema_name="FrenchVerbConjugations",
    schema_description="French verb conjugations",
)

# --- German: 8-case nouns + 6-person verbs ---

_DE_NOUN_FIELDS: List[str] = []
_DE_NOUN_MAPPING: Dict[str, GrammaticalForm] = {}
for _case in _DE_CASES:
    for _number in ["singular", "plural"]:
        _field = f"{_case}_{_number}"
        _DE_NOUN_FIELDS.append(_field)
        _DE_NOUN_MAPPING[_field] = _gf(f"NOUN_DE_{_case.upper()}_{_number.upper()}")

FORM_SPECS[("de", "noun")] = LanguageFormSpec(
    language_code="de",
    language_name="German",
    pos_type="noun",
    form_mapping=_DE_NOUN_MAPPING,
    form_fields=_DE_NOUN_FIELDS,
    prompt_path="de/noun",
    query_type="german_noun_forms",
    schema_name="GermanNounDeclensions",
    schema_description="German noun declensions",
)

FORM_SPECS[("de", "verb")] = _make_6person_verb_spec("de", "German")

# --- Lithuanian: 14-case nouns, 6-person verbs, 28-form adjectives, 3-form adverbs ---

_LT_NOUN_FIELDS: List[str] = []
_LT_NOUN_MAPPING: Dict[str, GrammaticalForm] = {}
for _case in _LT_CASES:
    for _number in ["singular", "plural"]:
        _field = f"{_case}_{_number}"
        _LT_NOUN_FIELDS.append(_field)
        _LT_NOUN_MAPPING[_field] = _gf(f"NOUN_LT_{_case.upper()}_{_number.upper()}")

FORM_SPECS[("lt", "noun")] = LanguageFormSpec(
    language_code="lt",
    language_name="Lithuanian",
    pos_type="noun",
    form_mapping=_LT_NOUN_MAPPING,
    form_fields=_LT_NOUN_FIELDS,
    prompt_path="lt/noun",
    query_type="lithuanian_noun_declensions",
    schema_name="LithuanianNounDeclensions",
    schema_description="Lithuanian noun declensions",
    extra_schema_properties={
        "number_type": SchemaProperty(
            "string",
            "The number type of this noun",
            enum=["regular", "plurale_tantum", "singulare_tantum"],
        ),
    },
)

FORM_SPECS[("lt", "verb")] = _make_6person_verb_spec("lt", "Lithuanian")

_LT_ADJ_FIELDS: List[str] = []
_LT_ADJ_MAPPING: Dict[str, GrammaticalForm] = {}
for _case in _LT_CASES:
    for _number in ["singular", "plural"]:
        for _gender in ["m", "f"]:
            _field = f"{_case}_{_number}_{_gender}"
            _LT_ADJ_FIELDS.append(_field)
            _LT_ADJ_MAPPING[_field] = _gf(
                f"ADJ_LT_{_case.upper()}_{_number.upper()}_{_gender.upper()}"
            )

FORM_SPECS[("lt", "adjective")] = LanguageFormSpec(
    language_code="lt",
    language_name="Lithuanian",
    pos_type="adjective",
    form_mapping=_LT_ADJ_MAPPING,
    form_fields=_LT_ADJ_FIELDS,
    prompt_path="lt/adjective",
    query_type="lithuanian_adjective_declensions",
    schema_name="LithuanianAdjectiveDeclensions",
    schema_description="Lithuanian adjective declensions",
)

FORM_SPECS[("lt", "adverb")] = LanguageFormSpec(
    language_code="lt",
    language_name="Lithuanian",
    pos_type="adverb",
    form_mapping={
        "positive": GrammaticalForm.ADVERB_LT_POSITIVE,
        "comparative": GrammaticalForm.ADVERB_LT_COMPARATIVE,
        "superlative": GrammaticalForm.ADVERB_LT_SUPERLATIVE,
    },
    form_fields=["positive", "comparative", "superlative"],
    prompt_path="lt/adverb",
    query_type="lithuanian_adverb_forms",
    schema_name="LithuanianAdverbForms",
    schema_description="Lithuanian adverb forms",
)

# --- Latvian: 14-case nouns, 6-person verbs, 28-form adjectives, 3-form adverbs ---

_LV_NOUN_FIELDS: List[str] = []
_LV_NOUN_MAPPING: Dict[str, GrammaticalForm] = {}
for _case in _LV_CASES:
    for _number in ["singular", "plural"]:
        _field = f"{_case}_{_number}"
        _LV_NOUN_FIELDS.append(_field)
        _LV_NOUN_MAPPING[_field] = _gf(f"NOUN_LV_{_case.upper()}_{_number.upper()}")

FORM_SPECS[("lv", "noun")] = LanguageFormSpec(
    language_code="lv",
    language_name="Latvian",
    pos_type="noun",
    form_mapping=_LV_NOUN_MAPPING,
    form_fields=_LV_NOUN_FIELDS,
    prompt_path="lv/noun",
    query_type="latvian_noun_declensions",
    schema_name="LatvianNounDeclensions",
    schema_description="Latvian noun declensions",
    extra_schema_properties={
        "number_type": SchemaProperty(
            "string",
            "The number type of this noun",
            enum=["regular", "plurale_tantum", "singulare_tantum"],
        ),
    },
)

FORM_SPECS[("lv", "verb")] = _make_6person_verb_spec("lv", "Latvian")

_LV_ADJ_FIELDS: List[str] = []
_LV_ADJ_MAPPING: Dict[str, GrammaticalForm] = {}
for _case in _LV_CASES:
    for _number in ["singular", "plural"]:
        for _gender in ["m", "f"]:
            _field = f"{_case}_{_number}_{_gender}"
            _LV_ADJ_FIELDS.append(_field)
            _LV_ADJ_MAPPING[_field] = _gf(
                f"ADJ_LV_{_case.upper()}_{_number.upper()}_{_gender.upper()}"
            )

FORM_SPECS[("lv", "adjective")] = LanguageFormSpec(
    language_code="lv",
    language_name="Latvian",
    pos_type="adjective",
    form_mapping=_LV_ADJ_MAPPING,
    form_fields=_LV_ADJ_FIELDS,
    prompt_path="lv/adjective",
    query_type="latvian_adjective_declensions",
    schema_name="LatvianAdjectiveDeclensions",
    schema_description="Latvian adjective declensions",
)

FORM_SPECS[("lv", "adverb")] = LanguageFormSpec(
    language_code="lv",
    language_name="Latvian",
    pos_type="adverb",
    form_mapping={
        "positive": GrammaticalForm.ADVERB_LV_POSITIVE,
        "comparative": GrammaticalForm.ADVERB_LV_COMPARATIVE,
        "superlative": GrammaticalForm.ADVERB_LV_SUPERLATIVE,
    },
    form_fields=["positive", "comparative", "superlative"],
    prompt_path="lv/adverb",
    query_type="latvian_adverb_forms",
    schema_name="LatvianAdverbForms",
    schema_description="Latvian adverb forms",
)

# --- Polish: 14-case nouns + 6-person verbs ---

_PL_NOUN_FIELDS: List[str] = []
_PL_NOUN_MAPPING: Dict[str, GrammaticalForm] = {}
for _case in _PL_CASES:
    for _number in ["singular", "plural"]:
        _field = f"{_case}_{_number}"
        _PL_NOUN_FIELDS.append(_field)
        _PL_NOUN_MAPPING[_field] = _gf(f"NOUN_PL_{_case.upper()}_{_number.upper()}")

FORM_SPECS[("pl", "noun")] = LanguageFormSpec(
    language_code="pl",
    language_name="Polish",
    pos_type="noun",
    form_mapping=_PL_NOUN_MAPPING,
    form_fields=_PL_NOUN_FIELDS,
    prompt_path="pl/noun",
    query_type="polish_noun_forms",
    schema_name="PolishNounForms",
    schema_description="Polish noun forms",
)

FORM_SPECS[("pl", "verb")] = _make_6person_verb_spec("pl", "Polish")

# --- Swedish: singular/plural nouns + 3-tense verbs (no person) ---
# Note: Swedish verbs use "conjugations" naming despite being tense-only.

FORM_SPECS[("sv", "noun")] = _make_singular_plural_noun_spec("sv", "Swedish")

FORM_SPECS[("sv", "verb")] = LanguageFormSpec(
    language_code="sv",
    language_name="Swedish",
    pos_type="verb",
    form_mapping={
        "present": GrammaticalForm.VERB_SV_PRESENT,
        "past": GrammaticalForm.VERB_SV_PAST,
        "future": GrammaticalForm.VERB_SV_FUTURE,
    },
    form_fields=["present", "past", "future"],
    prompt_path="sv/verb",
    query_type="swedish_verb_conjugations",
    schema_name="SwedishVerbConjugations",
    schema_description="Swedish verb conjugations",
)
