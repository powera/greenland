#!/usr/bin/python3

"""Enumeration types for linguistic models.

The ``*Subtype`` enums are **generated** from
:data:`storage.models.guid_prefixes.SUBTYPE_DEFS`, which is the single source of
truth for what subtypes exist. Adding one means editing that table, not this
file -- these classes exist so that ``NounSubtype.LEGAL_DOCUMENT`` keeps
working and so the enums cannot drift from the GUID prefixes.

One deliberate asymmetry is preserved from the hand-written version: each enum
has a bare ``OTHER = "other"`` member, while the prefix table keys the same
bucket ``"<pos>_other"``. The catch-all is reachable by GUID but is not offered
as a classification choice, and
``src/tests/storage/test_pos_enum_helpers.py`` asserts exactly that.
"""

import enum
from typing import Any, Dict

from storage.models.guid_prefixes import SUBTYPE_DEFS

# The catch-all every POS type carries. Keyed "<pos>_other" in SUBTYPE_DEFS but
# exposed as the bare value here; see the module docstring.
_CATCH_ALL_VALUE = "other"


def _build_subtype_enum(pos_type: str, class_name: str) -> Any:
    """Build one ``*Subtype`` enum from the subtype table.

    Member names are ``subtype.upper()`` unless the definition overrides it
    with ``member_name``. The ``<pos>_other`` key becomes ``OTHER = "other"``.

    Returns ``Any`` rather than ``Type[enum.Enum]`` deliberately. A functional
    Enum has no statically known members, so a precise annotation would make
    every ``NounSubtype.PERSONAL_NAME`` in the codebase a mypy error even
    though it resolves fine at runtime -- the hand-written classes these
    replace typed those accesses, and this keeps them accepted.
    """
    members: Dict[str, str] = {}
    for subtype, spec in SUBTYPE_DEFS[pos_type].items():
        if subtype == f"{pos_type}_other":
            members["OTHER"] = _CATCH_ALL_VALUE
            continue
        members[spec.member_name or subtype.upper()] = subtype

    # A plain Enum, not a str mixin: the hand-written classes these replace
    # were plain, and a mixin would quietly make ``member == "legal_document"``
    # true, hiding comparisons that should have used ``.value``.
    built = enum.Enum(class_name, members)  # type: ignore[misc]
    built.__doc__ = f"Subtypes for {pos_type}s. Generated from SUBTYPE_DEFS in guid_prefixes.py."
    return built


NounSubtype = _build_subtype_enum("noun", "NounSubtype")
VerbSubtype = _build_subtype_enum("verb", "VerbSubtype")
AdjectiveSubtype = _build_subtype_enum("adjective", "AdjectiveSubtype")
AdverbSubtype = _build_subtype_enum("adverb", "AdverbSubtype")
NumeralSubtype = _build_subtype_enum("numeral", "NumeralSubtype")


class GrammaticalForm(enum.Enum):
    """Grammatical forms for derivative forms with part-of-speech prefixes."""

    # Verb forms - generic/language-neutral
    VERB_INFINITIVE = "verb/infinitive"
    VERB_PAST_PARTICIPLE = "verb/past_participle"
    VERB_PRESENT_PARTICIPLE = "verb/present_participle"
    VERB_GERUND = "verb/gerund"

    # Noun forms (English)
    NOUN_SINGULAR = "noun/singular"
    NOUN_PLURAL = "noun/plural"
    NOUN_POSSESSIVE_SINGULAR = "noun/possessive_singular"
    NOUN_POSSESSIVE_PLURAL = "noun/possessive_plural"

    # Adjective forms (English)
    ADJECTIVE_POSITIVE = "adjective/positive"
    ADJECTIVE_COMPARATIVE = "adjective/comparative"
    ADJECTIVE_SUPERLATIVE = "adjective/superlative"

    # Adverb forms
    ADVERB_POSITIVE = "adverb/positive"
    ADVERB_COMPARATIVE = "adverb/comparative"
    ADVERB_SUPERLATIVE = "adverb/superlative"

    # Language-specific adverb base forms (invariant adverbs)
    ADVERB_KO_BASE = "adverb/ko_base"

    # Pronoun forms - Korean (simplified)
    # Word itself indicates person/number/formality; tag indicates function
    PRONOUN_KO_SUBJECTIVE = "pronoun/ko_subjective"  # 나, 저, 너, 그, 그녀, 우리, 너희, 그들
    PRONOUN_KO_POSSESSIVE = "pronoun/ko_possessive"  # 나의/내, 저의/제, 우리의/우리

    # Legacy forms (deprecated - use language-specific forms above)
    PRONOUN_SUBJECTIVE = "pronoun/subjective"  # Deprecated: use pronoun/en_subjective
    PRONOUN_OBJECTIVE = "pronoun/objective"  # Deprecated: use pronoun/en_objective
    PRONOUN_POSSESSIVE = "pronoun/possessive"  # Deprecated: use pronoun/en_possessive
    PRONOUN_REFLEXIVE = "pronoun/reflexive"  # Deprecated: use pronoun/en_reflexive

    # Other parts of speech (typically invariant)
    PREPOSITION = "preposition/base"
    CONJUNCTION = "conjunction/base"
    INTERJECTION = "interjection/base"
    DETERMINER = "determiner/base"
    ARTICLE = "article/base"

    # Korean numerals (native Korean vs Sino-Korean systems)
    NUMERAL_KO_NATIVE = "numeral/ko_native"  # 하나, 둘, 셋 (native Korean, for counting)
    NUMERAL_KO_SINO = "numeral/ko_sino"  # 일, 이, 삼 (Sino-Korean, for dates/numbers)
    NUMERAL_KO_ORDINAL = "numeral/ko_ordinal"  # 첫째, 둘째, 셋째

    # Kannada noun forms (singular/plural only)
    NOUN_KN_SINGULAR = "noun/kn_singular"
    NOUN_KN_PLURAL = "noun/kn_plural"

    # Estonian noun forms (singular/plural only - no grammatical gender)
    NOUN_ET_SINGULAR = "noun/et_singular"
    NOUN_ET_PLURAL = "noun/et_plural"

    # Latvian noun forms (legacy singular/plural - kept for backward compatibility)
    NOUN_LV_SINGULAR = "noun/lv_singular"
    NOUN_LV_PLURAL = "noun/lv_plural"

    # Malay noun forms (singular/plural - plural via reduplication e.g. buku-buku)
    NOUN_MS_SINGULAR = "noun/ms_singular"
    NOUN_MS_PLURAL = "noun/ms_plural"

    # Malay verb forms (isolating - no person conjugation, tense via context/markers)
    VERB_MS_PRESENT = "verb/ms_present"
    VERB_MS_PAST = "verb/ms_past"
    VERB_MS_FUTURE = "verb/ms_future"

    # Filipino (Tagalog) noun forms (singular/plural - plural via mga prefix)
    NOUN_TL_SINGULAR = "noun/tl_singular"
    NOUN_TL_PLURAL = "noun/tl_plural"

    # Filipino verb forms (aspect-based: completed/incompleted/contemplated)
    VERB_TL_PRESENT = "verb/tl_present"
    VERB_TL_PAST = "verb/tl_past"
    VERB_TL_FUTURE = "verb/tl_future"

    # Bengali noun forms (singular/plural)
    NOUN_BN_SINGULAR = "noun/bn_singular"
    NOUN_BN_PLURAL = "noun/bn_plural"

    # Bengali verb forms (person/tense conjugation)
    VERB_BN_PRESENT = "verb/bn_present"
    VERB_BN_PAST = "verb/bn_past"
    VERB_BN_FUTURE = "verb/bn_future"

    # Pashto noun forms (singular/plural - gender/case inflection)
    NOUN_PS_SINGULAR = "noun/ps_singular"
    NOUN_PS_PLURAL = "noun/ps_plural"

    # Pashto verb forms (person/number/gender/tense conjugation)
    VERB_PS_PRESENT = "verb/ps_present"
    VERB_PS_PAST = "verb/ps_past"
    VERB_PS_FUTURE = "verb/ps_future"

    # Persian noun forms (singular/plural)
    NOUN_FA_SINGULAR = "noun/fa_singular"
    NOUN_FA_PLURAL = "noun/fa_plural"

    # Persian verb forms (person/number/tense conjugation)
    VERB_FA_PRESENT = "verb/fa_present"
    VERB_FA_PAST = "verb/fa_past"
    VERB_FA_FUTURE = "verb/fa_future"

    # Georgian noun forms (singular/plural - case declension)
    NOUN_KA_SINGULAR = "noun/ka_singular"
    NOUN_KA_PLURAL = "noun/ka_plural"

    # Georgian verb forms (complex screeve system with person/tense)
    VERB_KA_PRESENT = "verb/ka_present"
    VERB_KA_PAST = "verb/ka_past"
    VERB_KA_FUTURE = "verb/ka_future"

    # Armenian noun forms (singular/plural - case declension)
    NOUN_HY_SINGULAR = "noun/hy_singular"
    NOUN_HY_PLURAL = "noun/hy_plural"

    # Armenian verb forms (person/number/tense conjugation)
    VERB_HY_PRESENT = "verb/hy_present"
    VERB_HY_PAST = "verb/hy_past"
    VERB_HY_FUTURE = "verb/hy_future"

    # Azerbaijani noun forms (singular/plural - agglutinative with vowel harmony)
    NOUN_AZ_SINGULAR = "noun/az_singular"
    NOUN_AZ_PLURAL = "noun/az_plural"

    # Azerbaijani verb forms (agglutinative person/tense/mood conjugation)
    VERB_AZ_PRESENT = "verb/az_present"
    VERB_AZ_PAST = "verb/az_past"
    VERB_AZ_FUTURE = "verb/az_future"

    # Turkish noun forms (singular/plural - agglutinative with vowel harmony)
    NOUN_TR_SINGULAR = "noun/tr_singular"
    NOUN_TR_PLURAL = "noun/tr_plural"

    # Turkish verb forms (agglutinative person/tense/mood conjugation)
    VERB_TR_PRESENT = "verb/tr_present"
    VERB_TR_PAST = "verb/tr_past"
    VERB_TR_FUTURE = "verb/tr_future"

    # Ukrainian noun forms (legacy singular/plural - kept for backward compatibility)
    NOUN_UK_SINGULAR = "noun/uk_singular"
    NOUN_UK_PLURAL = "noun/uk_plural"

    # Ukrainian verb forms (legacy tense-only - kept for backward compatibility)
    VERB_UK_PRESENT = "verb/uk_present"
    VERB_UK_PAST = "verb/uk_past"
    VERB_UK_FUTURE = "verb/uk_future"

    # Generic forms
    BASE_FORM = "base_form"
    OTHER = "other"


# ---------------------------------------------------------------------------
# Auto-generate GrammaticalForm members from langtools/*/forms_config.py
# ---------------------------------------------------------------------------
# Existing hand-written members are stable DB values and are never touched.
# This block only *adds* members that are defined in a forms_config but not
# yet present in the enum above, so new languages get their enum entries
# without manual edits to this file.


def _auto_extend_grammatical_form() -> None:
    """Scan forms_config modules and add missing GrammaticalForm members."""
    import importlib.util
    from pathlib import Path

    from langtools.form_patterns import get_all_enum_pairs

    langtools_dir = Path(__file__).resolve().parent.parent.parent / "langtools"
    if not langtools_dir.is_dir():
        return

    existing_values = {m.value for m in GrammaticalForm}
    new_members: dict[str, str] = {}

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

        # A storage dialect keeps its own paradigm rows, so it needs its own
        # members: verb/es-419_1s_present alongside verb/es_1s_present.
        dialect_names = getattr(mod, "DIALECT_LANGUAGE_NAMES", None)
        form_lang_codes: list[str] = [lang_code]
        if isinstance(dialect_names, dict):
            form_lang_codes.extend(str(code) for code in dialect_names)

        # Optional direct enum overrides for legacy/stable values that don't
        # map cleanly to form-pattern expansion.
        overrides = getattr(mod, "GRAMMATICAL_FORM_OVERRIDES", None)
        if isinstance(overrides, dict):
            for member_name, value_str in overrides.items():
                if not isinstance(member_name, str) or not isinstance(value_str, str):
                    continue
                if value_str not in existing_values and member_name not in new_members:
                    new_members[member_name] = value_str

        for attr_name in dir(mod):
            if not attr_name.endswith("_CONFIG"):
                continue
            cfg = getattr(mod, attr_name)
            if not isinstance(cfg, dict) or "type" not in cfg:
                continue
            # Derive pos_type from the attribute name: NOUN_CONFIG → noun
            pos_type = attr_name.removesuffix("_CONFIG").lower()
            for form_lang_code in form_lang_codes:
                for member_name, value_str in get_all_enum_pairs(cfg, form_lang_code, pos_type):
                    if value_str not in existing_values and member_name not in new_members:
                        new_members[member_name] = value_str

    # Dynamically extend the enum
    if new_members:
        # Use the stdlib approach: extend __members__ via _value2member_map_
        for name, value in sorted(new_members.items()):
            member = object.__new__(GrammaticalForm)
            member._value_ = value
            member._name_ = name
            GrammaticalForm._value2member_map_[value] = member  # type: ignore[attr-defined]
            GrammaticalForm._member_map_[name] = member  # type: ignore[attr-defined]
            GrammaticalForm._member_names_.append(name)  # type: ignore[attr-defined]


_auto_extend_grammatical_form()
