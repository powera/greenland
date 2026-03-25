"""Japanese grammatical/function-word data."""

from typing import Final

from langtools.grammatical_word_schema import (
    ALSO_LEMMA_SUBCATEGORIES,
    GRAMMATICAL_ONLY_SUBCATEGORIES,
    GrammaticalWordsBySubcategory,
    build_subcategory_mapping,
    union_subcategories,
)

JAPANESE_PERSONAL_PRONOUNS: Final[frozenset[str]] = frozenset(
    {
        "私",
        "わたし",
        "僕",
        "ぼく",
        "俺",
        "おれ",
        "あなた",
        "君",
        "きみ",
        "彼",
        "かれ",
        "彼女",
        "かのじょ",
        "私たち",
        "わたしたち",
        "僕たち",
        "ぼくたち",
        "俺たち",
        "おれたち",
        "あなたたち",
        "彼ら",
        "かれら",
        "彼女ら",
        "かのじょら",
    }
)

JAPANESE_GRAMMATICAL_WORDS: Final[frozenset[str]] = frozenset(
    {
        "は",
        "が",
        "を",
        "に",
        "へ",
        "で",
        "と",
        "や",
        "の",
        "も",
        "から",
        "まで",
        "より",
        "か",
        "ね",
        "よ",
        "な",
        "ぞ",
        "です",
        "だ",
        "である",
        "ます",
        "ません",
        "でした",
        "ない",
        "いる",
        "ある",
        "なる",
        "できる",
        "する",
    }
)

JAPANESE_FUNCTION_WORDS: Final[frozenset[str]] = frozenset(
    {
        "そして",
        "しかし",
        "また",
        "または",
        "けれど",
        "ので",
        "のに",
        "から",
        "ため",
        "について",
        "によって",
        "として",
        "でも",
        "なら",
        "ただし",
        "もし",
    }
)

JAPANESE_NON_PERSONAL_PRONOUNS: Final[frozenset[str]] = frozenset(
    {
        "これ",
        "それ",
        "あれ",
        "この",
        "その",
        "あの",
        "ここ",
        "そこ",
        "あそこ",
        "どれ",
        "どの",
        "どこ",
        "誰",
        "だれ",
        "何",
        "なに",
        "なん",
    }
)

JAPANESE_GRAMMATICAL_WORDS_BY_SUBCATEGORY: Final[GrammaticalWordsBySubcategory] = (
    build_subcategory_mapping(
        personal_pronouns=JAPANESE_PERSONAL_PRONOUNS,
        grammatical_words=JAPANESE_GRAMMATICAL_WORDS,
        function_words=JAPANESE_FUNCTION_WORDS,
        non_personal_pronouns=JAPANESE_NON_PERSONAL_PRONOUNS,
        auxiliaries=frozenset(
            {
                "です",
                "だ",
                "である",
                "ます",
                "ません",
                "でした",
                "ない",
                "いる",
                "ある",
                "なる",
                "できる",
                "する",
            }
        ),
        particles=frozenset(
            {
                "は",
                "が",
                "を",
                "に",
                "へ",
                "で",
                "と",
                "や",
                "の",
                "も",
                "から",
                "まで",
                "より",
                "か",
                "ね",
                "よ",
                "な",
                "ぞ",
            }
        ),
        conjunctions=frozenset(
            {
                "そして",
                "しかし",
                "また",
                "または",
                "けれど",
                "ので",
                "のに",
                "から",
                "ため",
                "について",
                "によって",
                "として",
                "でも",
                "なら",
                "ただし",
                "もし",
            }
        ),
        interrogatives=frozenset({"どれ", "どの", "どこ", "誰", "だれ", "何", "なに", "なん"}),
        demonstratives=frozenset(
            {"これ", "それ", "あれ", "この", "その", "あの", "ここ", "そこ", "あそこ"}
        ),
    )
)

JAPANESE_GRAMMATICAL_ONLY: Final[frozenset[str]] = union_subcategories(
    JAPANESE_GRAMMATICAL_WORDS_BY_SUBCATEGORY, GRAMMATICAL_ONLY_SUBCATEGORIES
)

JAPANESE_ALSO_LEMMA: Final[frozenset[str]] = union_subcategories(
    JAPANESE_GRAMMATICAL_WORDS_BY_SUBCATEGORY, ALSO_LEMMA_SUBCATEGORIES
)

JAPANESE_ALL_TIERS: Final[frozenset[str]] = frozenset(
    JAPANESE_GRAMMATICAL_ONLY | JAPANESE_ALSO_LEMMA
)
