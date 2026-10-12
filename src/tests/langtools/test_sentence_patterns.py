"""Tests for langtools.sentence_patterns, on hand-built word pools."""

from typing import Dict, List, Optional

from langtools.sentence_patterns import render
from langtools.sentence_patterns.types import (
    Gender,
    PatternResult,
    RenderedSentence,
    SlotAdjective,
    SlotNoun,
    WordPools,
)


def _noun(
    target: str,
    english: str = "cat",
    gender: Optional[Gender] = "feminine",
    forms: Optional[Dict[str, str]] = None,
    group: str = "animal",
    english_plural: Optional[str] = "cats",
    gender_fact: Optional[str] = None,
    measure_word: Optional[str] = None,
) -> SlotNoun:
    return SlotNoun(
        guid=f"N_{english}",
        english=english,
        target=target,
        group=group,
        countability="uncountable" if english == "water" else "countable",
        english_countability="uncountable" if english == "water" else "countable",
        english_plural=english_plural,
        gender=gender,
        gender_fact=gender_fact or gender,
        measure_word=measure_word,
        forms=forms or {},
    )


def _find(result: PatternResult, pattern_id: str, subject: Optional[str]) -> List[RenderedSentence]:
    return [s for s in result.sentences if s.pattern_id == pattern_id and s.subject == subject]


LT_CAT = _noun(
    "katė",
    forms={
        "nominative_singular": "katė",
        "genitive_singular": "katės",
        "accusative_singular": "katę",
        "nominative_plural": "katės",
        "genitive_plural": "kačių",
        "accusative_plural": "kates",
    },
)

LT_TIRED = SlotAdjective(
    guid="A_tired",
    english="tired",
    target="pavargęs",
    kind="feeling",
    forms={
        "nominative_singular_m": "pavargęs",
        "nominative_singular_f": "pavargusi",
        "nominative_plural_m": "pavargę",
        "nominative_plural_f": "pavargusios",
    },
)


def test_lithuanian_case_by_verb_and_person() -> None:
    result = render("lt", WordPools([LT_CAT], []))
    (want,) = _find(result, "want", "1s")
    assert (want.english, want.target) == ("I want a cat.", "Noriu katės")
    assert "Aš noriu katės" in want.also_accepted
    (have,) = _find(result, "have", "3s_f")
    assert (have.english, have.target) == ("She has a cat.", "Ji turi katę")
    (like,) = _find(result, "like-many", "2p")
    assert (like.target, like.detail) == ("Jums patinka katės", "you: several people")
    assert "Mėgstate kates" in like.also_accepted


def test_lithuanian_numbers_agree_and_ten_takes_genitive() -> None:
    result = render("lt", WordPools([LT_CAT], []), ["number"])
    targets = {s.target for s in _find(result, "number", "1s")}
    assert "Turiu dvi kates" in targets
    assert "Turiu dešimt kačių" in targets


def test_lithuanian_feeling_agrees_with_subject() -> None:
    result = render("lt", WordPools([], [LT_TIRED]))
    (she,) = _find(result, "feeling", "3s_f")
    assert she.target == "Ji yra pavargusi"
    (they,) = _find(result, "feeling", "3p")
    assert they.target == "Jie yra pavargę"
    assert "Jos yra pavargusios" in they.also_accepted
    (i,) = _find(result, "feeling", "1s")
    assert {"Aš esu pavargusi", "Esu pavargęs"} <= set(i.also_accepted)


def test_missing_form_is_a_skip_reported_once() -> None:
    bare = _noun("katė", forms={"accusative_singular": "katę"})
    result = render("lt", WordPools([bare], []), ["want"])
    assert result.sentences == []
    assert [(s.pattern_id, s.reason) for s in result.skips] == [
        ("want", "missing form genitive_singular")
    ]


ES_CAT = _noun("gato", gender="masculine", forms={"plural": "gatos"})


def test_spanish_vosotros_and_latin_american_ustedes() -> None:
    (spain,) = _find(render("es", WordPools([ES_CAT], [])), "want", "2p")
    assert spain.target == "Queréis un gato"
    assert "Vosotras queréis un gato" in spain.also_accepted
    latam = render("es-419", WordPools([ES_CAT], []))
    (want,) = _find(latam, "want", "2p")
    assert want.target == "Ustedes quieren un gato"
    (like,) = _find(latam, "like-many", "2p")
    assert like.target == "A ustedes les gustan los gatos"


def test_spanish_gustar_and_el_before_stressed_a() -> None:
    water = _noun("agua", english="water", gender="feminine", group="food")
    result = render("es", WordPools([ES_CAT, water], []), ["like-one"])
    assert _find(result, "like-one", "3s_m")[0].target == "A él le gusta el gato"
    (likes_water,) = [s for s in _find(result, "like-one", "1s") if "agua" in s.target]
    assert likes_water.target == "Me gusta el agua"


def test_common_gender_fact_is_named_in_the_skip() -> None:
    student = _noun("élève", english="student", gender=None, gender_fact="common")
    result = render("fr", WordPools([student], []), ["have"])
    assert result.skips[0].reason == "missing masculine/feminine gender (fact is common)"


def test_french_elision_and_partitive() -> None:
    plane = _noun("avion", english="plane", gender="masculine", group="vehicle")
    water = _noun("eau", english="water", gender="feminine", group="food")
    result = render("fr", WordPools([plane, water], []), ["want", "like-one"])
    targets = {s.target for s in result.sentences if s.subject == "1s"}
    assert {"Je veux un avion", "Je veux de l'eau", "J'aime l'avion"} <= targets
    assert "Elles aiment l'avion" in _find(result, "like-one", "3p")[0].also_accepted


def test_chinese_needs_measure_word() -> None:
    cat = _noun("猫", gender=None, measure_word="只")
    result = render("zh", WordPools([cat, _noun("狗", english="dog", gender=None)], []))
    assert _find(result, "have", "3s_f")[0].target == "她有一只猫"
    assert "我有两只猫" in {s.target for s in _find(result, "number", "1s")}
    assert ("number", "N_dog", "missing measure_words") in {
        (s.pattern_id, s.guid, s.reason) for s in result.skips
    }


def test_chinese_strips_attributive_de() -> None:
    afraid = SlotAdjective("A_afraid", "afraid", "害怕的", "feeling")
    (sentence,) = _find(render("zh", WordPools([], [afraid])), "feeling", "1s")
    assert sentence.target == "我很害怕"


def test_missing_countability_is_not_guessed() -> None:
    from dataclasses import replace

    noun = replace(ES_CAT, countability=None)
    result = render("es", WordPools([noun], []), ["want"])
    assert not result.sentences
    assert result.skips[0].reason == "missing countability"


def test_mass_noun_and_plural_only_guards() -> None:
    from dataclasses import replace

    rice = replace(
        ES_CAT,
        english="rice",
        target="arroz",
        countability="uncountable",
        english_countability="uncountable",
    )
    result = render("es", WordPools([rice], []), ["want", "number"])
    assert _find(result, "want", "1s")[0].english == "I want rice."
    assert not _find(result, "number", "1s")
    trousers = replace(ES_CAT, number_type="plurale_tantum")
    result = render("es", WordPools([trousers], []), ["have"])
    assert not result.sentences
    assert result.skips[0].reason == "unsupported plural-only noun"


def test_database_pools_keep_missing_facts_and_varieties_separate() -> None:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from sentences.pattern_pools import load_pools
    from storage.models.schema import Base, DerivativeForm, Lemma, LemmaTranslation
    from storage.models.grammar_fact import GrammarFact

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        lemma = Lemma(
            lemma_text="cat (animal)",
            definition_text="a cat",
            pos_type="noun",
            pos_subtype="animal",
            guid="N02_001",
            difficulty_level=1,
        )
        session.add(lemma)
        session.flush()
        session.add_all(
            [
                LemmaTranslation(lemma_id=lemma.id, language_code="es", translation="gato"),
                LemmaTranslation(lemma_id=lemma.id, language_code="es-419", translation="gato"),
                DerivativeForm(
                    lemma_id=lemma.id,
                    language_code="en",
                    grammatical_form="noun/en_plural",
                    derivative_form_text="cats",
                ),
                DerivativeForm(
                    lemma_id=lemma.id,
                    language_code="es-419",
                    grammatical_form="noun/es-419_plural",
                    derivative_form_text="gatos",
                ),
                GrammarFact(
                    lemma_id=lemma.id,
                    language_code="es-419",
                    fact_type="grammatical_gender",
                    fact_value="masculine",
                ),
                GrammarFact(
                    lemma_id=lemma.id,
                    language_code="en",
                    fact_type="countability",
                    fact_value="countable",
                ),
            ]
        )
        session.flush()
        spain = load_pools(session, "es")
        latam = load_pools(session, "es-419")
        assert spain.nouns[0].english == "cat"
        assert spain.nouns[0].forms == {}
        assert spain.nouns[0].gender is None
        assert latam.nouns[0].forms == {"plural": "gatos"}
        assert latam.nouns[0].gender == "masculine"
        assert latam.nouns[0].english_plural == "cats"
        assert latam.nouns[0].english_countability == "countable"
        assert latam.nouns[0].countability is None
        assert not load_pools(session, "fr").nouns
    engine.dispose()


def test_english_articles_handle_common_sound_exceptions() -> None:
    from langtools.sentence_patterns.common import english_indefinite

    assert english_indefinite("uniform") == "a uniform"
    assert english_indefinite("unicorn") == "a unicorn"
    assert english_indefinite("hour") == "an hour"
    assert english_indefinite("apple") == "an apple"
