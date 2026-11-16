"""Chinese measure-word lists: the stored string form and its list form.

A noun has one primary measure word (the ``measure_words`` grammar fact, the
default word after 一) and two optional lists beside it:

* ``measure_words_alternates`` - other classifiers equally correct for one
  item (椅子: primary 把, alternate 张).
* ``measure_words_portions`` - other containers and measures, which change
  the quantity (汤: primary 碗, portions 杯, 锅, 份).

The lists are stored as one string, classifiers joined by ``", "``, or
``none`` once checked with nothing to add.  ``none`` keeps "checked, empty"
distinct from "never asked", which a missing row means.  CJK classifiers never
contain a comma, so the join needs no escaping.
"""

import re
from typing import Dict, List, Mapping, Optional, Sequence

ALTERNATES_FACT = "measure_words_alternates"
PORTIONS_FACT = "measure_words_portions"
LIST_FACT_TYPES = (ALTERNATES_FACT, PORTIONS_FACT)

NONE_VALUE = "none"
SEPARATOR = ", "

# Any list separator a model or a human might type.
_SPLIT_PATTERN = re.compile(r"[,，、;；]")
# A classifier is one to three CJK characters; no digits or pinyin.
_CLASSIFIER_PATTERN = re.compile(r"^[㐀-鿿]{1,3}$")
# A leading counting numeral means the model answered 一只 instead of 只.  Not
# 千/百/万 (千克 is a unit), and a bare 两 is the tael (一两茶叶).
_NUMERAL_CHARACTERS = frozenset("一二两三四五六七八九十几")


def validate_classifier(item: str) -> str:
    """Return the stripped classifier, or raise ValueError for anything else."""
    text = item.strip()
    if not _CLASSIFIER_PATTERN.match(text):
        raise ValueError(f"Not a Chinese measure word: {item!r}")
    if text == "一" or (len(text) > 1 and text[0] in _NUMERAL_CHARACTERS):
        raise ValueError(f"Measure word must not include a numeral: {item!r}")
    return text


def format_measure_word_list(items: Sequence[str], exclude: Optional[str] = None) -> str:
    """Validate, deduplicate and join a list for storage; empty becomes ``none``.

    ``exclude`` (the primary) is dropped wherever it appears.
    """
    classifiers: List[str] = []
    for item in items:
        if not item.strip():
            continue
        classifier = validate_classifier(item)
        if classifier != exclude and classifier not in classifiers:
            classifiers.append(classifier)
    return SEPARATOR.join(classifiers) if classifiers else NONE_VALUE


def parse_measure_word_list(value: Optional[str]) -> Optional[List[str]]:
    """Stored string -> list.  None (unchecked) stays None; ``none`` is []."""
    if value is None or not value.strip():
        return None
    if value.strip() == NONE_VALUE:
        return []
    return [item.strip() for item in _SPLIT_PATTERN.split(value) if item.strip()]


def measure_word_lists(facts: Mapping[str, Optional[str]]) -> Dict[str, List[str]]:
    """The checked list facts in *facts*, as lists keyed by fact type."""
    result: Dict[str, List[str]] = {}
    for fact_type in LIST_FACT_TYPES:
        parsed = parse_measure_word_list(facts.get(fact_type))
        if parsed is not None:
            result[fact_type] = parsed
    return result
