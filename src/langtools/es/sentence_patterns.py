"""Spanish pattern sentences: querer / tener / gustar / ser + color /
estar + feeling / number + noun, for every person.

The lessons are the article's gender, gusta vs gustan with the liker as an
indirect-object pronoun, ser for a color and estar for a feeling.

es-419 uses the same patterns with ustedes for the second person plural:
ustedes takes the third-person-plural verb and les, and unlike vosotros it is
kept even though the verb has no person of its own to show.

Mirrors Trakaido's SpanishSentenceQuiz.swift / spanishSentenceQuiz.ts.
"""

from typing import Dict, List, Optional, Sequence, Tuple

from langtools.sentence_patterns.common import (
    COLORABLE_GROUPS,
    ENGLISH_NUMBERS,
    adjective_forms,
    capitalize,
    english_clause,
    english_indefinite,
    missing,
    missing_gender,
    objects,
    sentence,
)
from langtools.sentence_patterns.types import (
    Outcome,
    SentencePattern,
    SlotAdjective,
    SlotNoun,
    SlotWord,
    Subject,
    WordPools,
)

EL_FEMININE_NOUNS = frozenset(
    {"ave", "agua", "águila", "alma", "arma", "hacha", "hambre", "área", "aula", "hada"}
)

FEELINGS = frozenset({"happy", "sad", "angry", "tired", "excited", "afraid"})

NUMBERS: Dict[int, str] = {
    2: "dos",
    3: "tres",
    4: "cuatro",
    5: "cinco",
    6: "seis",
    7: "siete",
    8: "ocho",
    9: "nueve",
    10: "diez",
}

VERBS: Dict[str, Dict[str, str]] = {
    "querer": {
        "1s": "quiero",
        "2s": "quieres",
        "3s": "quiere",
        "1p": "queremos",
        "2p": "queréis",
        "3p": "quieren",
    },
    "tener": {
        "1s": "tengo",
        "2s": "tienes",
        "3s": "tiene",
        "1p": "tenemos",
        "2p": "tenéis",
        "3p": "tienen",
    },
    "estar": {
        "1s": "estoy",
        "2s": "estás",
        "3s": "está",
        "1p": "estamos",
        "2p": "estáis",
        "3p": "están",
    },
}

# Subject key -> (default pronoun, feminine alternative or None).
PRONOUNS: Dict[str, Tuple[str, Optional[str]]] = {
    "1s": ("yo", None),
    "2s": ("tú", None),
    "3s_m": ("él", None),
    "3s_f": ("ella", None),
    "1p": ("nosotros", "nosotras"),
    "2p": ("vosotros", "vosotras"),
    "3p": ("ellos", "ellas"),
}

INDIRECT_PRONOUNS: Dict[str, str] = {
    "1s": "me",
    "2s": "te",
    "3s_m": "le",
    "3s_f": "le",
    "1p": "nos",
    "2p": "os",
    "3p": "les",
}

# Stressed pronouns for the "a mí me gusta" doubling.
STRESSED_PRONOUNS: Dict[str, str] = {"1s": "mí", "2s": "ti"}


class _Spanish:
    """One variety's patterns; es-419 swaps vosotros for ustedes."""

    def __init__(self, language_code: str) -> None:
        self.latin_american = language_code == "es-419"

    # -- grammar -------------------------------------------------------------

    def _verb_person(self, subject: Subject) -> str:
        if self.latin_american and subject.person == "2p":
            return "3p"
        return subject.person

    def _pronoun(self, subject: Subject) -> Tuple[str, Optional[str]]:
        if self.latin_american and subject.key == "2p":
            return "ustedes", None
        return PRONOUNS[subject.key]

    def _needs_pronoun(self, subject: Subject) -> bool:
        """Third person keeps the pronoun to show he/she; so does ustedes,
        whose verb is identical to ellos'."""
        return self._verb_person(subject).startswith("3")

    def clause(self, subject: Subject, verb: str, rest: str) -> Tuple[str, List[str]]:
        form = VERBS[verb][self._verb_person(subject)]
        pronoun, feminine = self._pronoun(subject)
        with_pronoun = [capitalize(f"{pronoun} {form} {rest}")]
        if feminine:
            with_pronoun.append(capitalize(f"{feminine} {form} {rest}"))
        if self._needs_pronoun(subject):
            return with_pronoun[0], with_pronoun[1:]
        return capitalize(f"{form} {rest}"), with_pronoun

    def like(self, subject: Subject, plural: bool, thing: str) -> Tuple[str, List[str]]:
        """'Me gusta el gato' / 'A él le gustan los gatos'."""
        verb = "gustan" if plural else "gusta"
        indirect = INDIRECT_PRONOUNS[subject.key]
        if self.latin_american and subject.key == "2p":
            indirect = "les"
        bare = f"{indirect} {verb} {thing}"
        pronoun, feminine = self._pronoun(subject)
        stressed = [STRESSED_PRONOUNS.get(subject.key, pronoun)]
        if feminine:
            stressed.append(feminine)
        doubled = [capitalize(f"a {s} {bare}") for s in stressed]
        if self._needs_pronoun(subject):
            # "Le gusta" alone does not say who; the doubling does.
            return doubled[0], doubled[1:] + [capitalize(bare)]
        return capitalize(bare), doubled

    # -- articles ------------------------------------------------------------

    @staticmethod
    def singular_article(noun: SlotNoun, definite: bool) -> str:
        masculine_form = noun.gender == "masculine" or noun.target in EL_FEMININE_NOUNS
        if definite:
            return "el" if masculine_form else "la"
        return "un" if masculine_form else "una"

    @staticmethod
    def plural_article(noun: SlotNoun) -> str:
        return "los" if noun.gender == "masculine" else "las"

    # -- candidates ----------------------------------------------------------

    @staticmethod
    def objects(pools: WordPools) -> List[Tuple[SlotWord, ...]]:
        return [(n,) for n in objects(pools.nouns)]

    @staticmethod
    def countables(pools: WordPools) -> List[Tuple[SlotWord, ...]]:
        return [(n,) for n in objects(pools.nouns) if not is_mass(n)]

    @staticmethod
    def plurals(pools: WordPools) -> List[Tuple[SlotWord, ...]]:
        return [(n,) for n in objects(pools.nouns) if not is_mass(n)]

    @staticmethod
    def colorables(pools: WordPools) -> List[Tuple[SlotWord, ...]]:
        nouns = [n for n in pools.nouns if n.group in COLORABLE_GROUPS and not is_mass(n)]
        return [(n, c) for n in nouns for c in pools.colors()]

    @staticmethod
    def feelings(pools: WordPools) -> List[Tuple[SlotWord, ...]]:
        return [(a,) for a in pools.feelings() if a.english in FEELINGS]

    # -- builds --------------------------------------------------------------

    def want(self, words: Sequence[SlotWord], subject: Optional[Subject]) -> List[Outcome]:
        assert subject is not None
        noun = _noun(words)
        if is_mass(noun):
            thing, english_thing = noun.target, noun.english
        elif noun.gender is None:
            return [missing_gender("want", noun)]
        else:
            thing = f"{self.singular_article(noun, False)} {noun.target}"
            english_thing = english_indefinite(noun.english)
        correct, accepted = self.clause(subject, "querer", thing)
        english = english_clause(subject, "want", english_thing)
        return [sentence("want", (noun,), english, correct, subject, tuple(accepted))]

    def have(self, words: Sequence[SlotWord], subject: Optional[Subject]) -> List[Outcome]:
        assert subject is not None
        noun = _noun(words)
        if noun.gender is None:
            return [missing_gender("have", noun)]
        thing = f"{self.singular_article(noun, False)} {noun.target}"
        correct, accepted = self.clause(subject, "tener", thing)
        english = english_clause(subject, "have", english_indefinite(noun.english))
        return [sentence("have", (noun,), english, correct, subject, tuple(accepted))]

    def like_one(self, words: Sequence[SlotWord], subject: Optional[Subject]) -> List[Outcome]:
        assert subject is not None
        noun = _noun(words)
        if noun.gender is None:
            return [missing_gender("like-one", noun)]
        correct, accepted = self.like(
            subject, False, f"{self.singular_article(noun, True)} {noun.target}"
        )
        thing = noun.english if is_mass(noun) else f"the {noun.english}"
        english = english_clause(subject, "like", thing)
        return [sentence("like-one", (noun,), english, correct, subject, tuple(accepted))]

    def like_many(self, words: Sequence[SlotWord], subject: Optional[Subject]) -> List[Outcome]:
        assert subject is not None
        noun = _noun(words)
        if noun.gender is None:
            return [missing_gender("like-many", noun)]
        if not noun.forms.get("plural"):
            return [missing("like-many", noun, "form plural")]
        if not noun.english_plural:
            return [missing("like-many", noun, "en plural")]
        things = f"{self.plural_article(noun)} {noun.forms['plural']}"
        correct, accepted = self.like(subject, True, things)
        english = english_clause(subject, "like", noun.english_plural)
        return [sentence("like-many", (noun,), english, correct, subject, tuple(accepted))]

    def color(self, words: Sequence[SlotWord], subject: Optional[Subject]) -> List[Outcome]:
        noun = _noun(words)
        color = words[1]
        assert isinstance(color, SlotAdjective)
        if noun.gender is None:
            return [missing_gender("color", noun)]
        forms = adjective_forms(color)
        if forms is None:
            return [missing("color", color, "adjective gender/number forms")]
        singular = capitalize(f"{self.singular_article(noun, True)} {noun.target}")
        results: List[Outcome] = [
            sentence(
                "color",
                (noun, color),
                f"The {noun.english} is {color.english}.",
                f"{singular} es {forms[(noun.gender, False)]}",
            )
        ]
        if not noun.forms.get("plural"):
            results.append(missing("color", noun, "form plural"))
        elif not noun.english_plural:
            results.append(missing("color", noun, "en plural"))
        else:
            plural = capitalize(f"{self.plural_article(noun)} {noun.forms['plural']}")
            results.append(
                sentence(
                    "color",
                    (noun, color),
                    f"The {noun.english_plural} are {color.english}.",
                    f"{plural} son {forms[(noun.gender, True)]}",
                )
            )
        return results

    def feeling(self, words: Sequence[SlotWord], subject: Optional[Subject]) -> List[Outcome]:
        assert subject is not None
        feeling = words[0]
        assert isinstance(feeling, SlotAdjective)
        forms = adjective_forms(feeling)
        if forms is None:
            return [missing("feeling", feeling, "adjective gender/number forms")]
        plural = subject.person.endswith("p")
        pronoun, feminine_pronoun = self._pronoun(subject)
        if subject.gender:
            pairs = [(pronoun, forms[(subject.gender, plural)])]
        else:
            # Either gender, with the pronoun agreeing: "nosotras estamos cansadas".
            pairs = [
                (pronoun, forms[("masculine", plural)]),
                (feminine_pronoun or pronoun, forms[("feminine", plural)]),
            ]
        estar = VERBS["estar"][self._verb_person(subject)]
        variants: List[str] = []
        for pair_pronoun, adjective in pairs:
            if not self._needs_pronoun(subject):
                variants.append(capitalize(f"{estar} {adjective}"))
            variants.append(capitalize(f"{pair_pronoun} {estar} {adjective}"))
        correct, accepted = variants[0], variants[1:]
        english = english_clause(subject, "be", feeling.english)
        return [sentence("feeling", (feeling,), english, correct, subject, tuple(accepted))]

    def number(self, words: Sequence[SlotWord], subject: Optional[Subject]) -> List[Outcome]:
        assert subject is not None
        noun = _noun(words)
        if not noun.forms.get("plural"):
            return [missing("number", noun, "form plural")]
        if not noun.english_plural:
            return [missing("number", noun, "en plural")]
        results: List[Outcome] = []
        for value, spanish in NUMBERS.items():
            correct, accepted = self.clause(subject, "tener", f"{spanish} {noun.forms['plural']}")
            digits, _ = self.clause(subject, "tener", f"{value} {noun.forms['plural']}")
            english = english_clause(
                subject, "have", f"{ENGLISH_NUMBERS[value]} {noun.english_plural}"
            )
            results.append(
                sentence("number", (noun,), english, correct, subject, tuple(accepted + [digits]))
            )
        return results

    def patterns(self) -> List[SentencePattern]:
        return [
            SentencePattern("want", self.objects, self.want),
            SentencePattern("have", self.countables, self.have),
            SentencePattern("like-one", self.objects, self.like_one),
            SentencePattern("like-many", self.plurals, self.like_many),
            SentencePattern("color", self.colorables, self.color, personal=False),
            SentencePattern("feeling", self.feelings, self.feeling),
            SentencePattern("number", self.plurals, self.number),
        ]


def _noun(words: Sequence[SlotWord]) -> SlotNoun:
    noun = words[0]
    assert isinstance(noun, SlotNoun)
    return noun


def is_mass(noun: SlotNoun) -> bool:
    return noun.countability == "uncountable"


PATTERNS: List[SentencePattern] = _Spanish("es").patterns()
LATIN_AMERICAN_PATTERNS: List[SentencePattern] = _Spanish("es-419").patterns()
