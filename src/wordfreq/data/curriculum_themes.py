"""Topic-band themes: the coarse subject areas a specialist word belongs to.

Each theme is one topic-band unit (1000-1299). Most came from one wordfreq
corpus, and that corpus is the evidence a *new* word is on-theme: a word
ranked far better there than in the general-fiction corpora is a subject
word, not general vocabulary.

Keep these coarse. A theme is a place a learner opts into ("legal", "cooking"),
not a taxonomy; ``pos_subtype`` already does the fine-grained grouping inside
a unit. A new theme earns an entry when it has a corpus or a clear subtype and
enough words to fill a level.

The tag is written to ``Lemma.tags`` / ``PendingImport.tags`` (see
``storage.crud.lemma_tags``); it is the theme's name.

Not yet a theme: modern medicine. No corpus covers it -- ``wiki_biology`` is
organisms and anatomy, ``early_modern_science`` is historical -- so medical
words still place by subtype (``disease_condition``, ``medication_remedy``).
"""

from dataclasses import dataclass
from typing import Mapping, Optional


@dataclass(frozen=True)
class CurriculumTheme:
    """One topic-band theme."""

    name: str
    #: Topic-band levels holding this theme, the main unit first.
    levels: tuple[int, ...]
    #: wordfreq corpus names (``Corpus.name``) whose vocabulary marks the theme.
    corpora: tuple[str, ...] = ()
    #: Subtypes that are this theme on their own. Only subtypes that almost
    #: never mean general vocabulary belong here.
    subtypes: frozenset[str] = frozenset()
    description: str = ""


CURRICULUM_THEMES: tuple[CurriculumTheme, ...] = (
    CurriculumTheme("arts", (1000,), ("wiki_arts",), description="art, music, literature"),
    CurriculumTheme("biology", (1010,), ("wiki_biology",), description="organisms and anatomy"),
    CurriculumTheme("geography", (1020,), ("wiki_geography",)),
    CurriculumTheme("history", (1030,), ("wiki_history",), description="history and biography"),
    CurriculumTheme(
        "modern_life",
        (1040,),
        ("wiki_modern_life",),
        description="everyday life and technology",
    ),
    CurriculumTheme(
        "physical_science",
        (1050,),
        ("wiki_physical_science",),
        description="physics, astronomy, earth science",
    ),
    CurriculumTheme(
        "society",
        (1060,),
        ("wiki_society", "religious_translated"),
        description="society, philosophy and religion",
    ),
    CurriculumTheme(
        "legal",
        (1070, 1130),
        ("legal_scotus",),
        frozenset({"legal", "legal_concept", "legal_document"}),
    ),
    CurriculumTheme("math", (1080,), ("wiki_math",), frozenset({"mathematical"})),
    CurriculumTheme("cooking", (1090,), ("cooking",), description="cooking and the kitchen"),
    # No level yet: 1100 is the chemical-elements cohort, which owns it.
    CurriculumTheme("chemistry", (), subtypes=frozenset({"chemical_compound"})),
    CurriculumTheme("linguistics", (1110,), ("wiki_linguistics",)),
)

THEMES_BY_NAME: Mapping[str, CurriculumTheme] = {theme.name: theme for theme in CURRICULUM_THEMES}


def theme_for_subtype(pos_subtype: Optional[str]) -> Optional[CurriculumTheme]:
    """The theme a subtype implies on its own, if any."""
    if not pos_subtype:
        return None
    for theme in CURRICULUM_THEMES:
        if pos_subtype in theme.subtypes:
            return theme
    return None
