"""Chinese grammatical/function-word data.

Four tiers:

1. **personal_pronouns** – 我, 你, 他, 她, 我们, 自己, …
2. **grammatical_words** – structural particles (的/地/得), aspect markers
   (了/着/过), modal particles, construction markers (把/被/让), negation,
   grammatical adverbs, pure auxiliaries (可以, 应该, …)
3. **function_words** – coverb-prepositions (从/到/给/…), conjunctions
   (和/或/但是/…), copula 是, existential 有, auxiliaries with verb senses
   (想/能/会/要)
4. **non_personal_pronouns** – demonstratives (这/那), interrogatives
   (谁/什么/哪里), determiners (每/各/某)

Tiers 1–2 have no analogues in data/release; tiers 3–4 do.
"""

from typing import Final

from langtools.grammatical_word_schema import (
    ALSO_LEMMA_SUBCATEGORIES,
    GRAMMATICAL_ONLY_SUBCATEGORIES,
    GrammaticalWordsBySubcategory,
    build_subcategory_mapping,
    union_subcategories,
)

# ── tier 1: personal pronouns ──────────────────────────────────────────

CHINESE_PERSONAL_PRONOUNS: Final[frozenset[str]] = frozenset(
    {
        "我",
        "你",
        "他",
        "她",
        "它",
        "我们",
        "你们",
        "他们",
        "她们",
        "自己",
        # Plural marker
        "们",
    }
)

# ── tier 2: grammatical words ─────────────────────────────────────────

CHINESE_GRAMMATICAL_WORDS: Final[frozenset[str]] = frozenset(
    {
        # Structural particles
        "的",
        "地",
        "得",
        # Aspect / tense particles
        "了",
        "着",
        "过",
        # Sentence-final / modal particles
        "吗",
        "呢",
        "吧",
        "啊",
        "呀",
        "嘛",
        "哦",
        "啦",
        # Construction markers
        "把",
        "被",
        "让",
        # Negation
        "不",
        "没",
        "别",
        "未",
        "非",
        # Grammatical adverbs
        "就",
        "都",
        "也",
        "还",
        "又",
        "再",
        "才",
        "只",
        "很",
        "太",
        "最",
        "更",
        "已",
        "已经",
        "正",
        "正在",
        "刚",
        "刚才",
        "常",
        "常常",
        "总",
        "总是",
        # Pure auxiliaries (no independent verb sense)
        "可以",
        "应该",
        "该",
        "必须",
    }
)

# ── tier 3: function words ────────────────────────────────────────────

CHINESE_FUNCTION_WORDS: Final[frozenset[str]] = frozenset(
    {
        # Coverbs / prepositions (also full verbs)
        "在",
        "从",
        "到",
        "向",
        "往",
        "对",
        "给",
        "跟",
        "比",
        "为",
        "用",
        "按",
        "离",
        "沿",
        "关于",
        # Conjunctions
        "和",
        "与",
        "或",
        "或者",
        "但",
        "但是",
        "而",
        "而且",
        "因为",
        "所以",
        "如果",
        "虽然",
        "虽",
        "虽说",
        "尽管",
        "不但",
        "不仅",
        "既",
        # Copula / existence
        "是",
        "有",
        # Auxiliaries with independent verb senses
        "会",
        "能",
        "要",
        "想",
        # Negation that doubles as lemma
        "没有",
    }
)

# ── tier 4: non-personal pronouns ─────────────────────────────────────

CHINESE_NON_PERSONAL_PRONOUNS: Final[frozenset[str]] = frozenset(
    {
        # Demonstratives / determiners
        "这",
        "那",
        "哪",
        "每",
        "各",
        "某",
        "些",
        "这些",
        "那些",
        # Interrogatives
        "谁",
        "什么",
        "哪里",
        "哪儿",
        # Demonstrative location words
        "这里",
        "那里",
        "这儿",
        "那儿",
    }
)

# ── aggregate sets ─────────────────────────────────────────────────────

CHINESE_GRAMMATICAL_WORDS_BY_SUBCATEGORY: Final[GrammaticalWordsBySubcategory] = (
    build_subcategory_mapping(
        personal_pronouns=CHINESE_PERSONAL_PRONOUNS,
        grammatical_words=CHINESE_GRAMMATICAL_WORDS,
        function_words=CHINESE_FUNCTION_WORDS,
        non_personal_pronouns=CHINESE_NON_PERSONAL_PRONOUNS,
        auxiliaries=frozenset({"可以", "应该", "该", "必须"}),
        particles=frozenset(
            {
                "的",
                "地",
                "得",
                "了",
                "着",
                "过",
                "吗",
                "呢",
                "吧",
                "啊",
                "呀",
                "嘛",
                "哦",
                "啦",
                "把",
                "被",
                "让",
                "不",
                "没",
                "别",
                "未",
                "非",
                "就",
                "都",
                "也",
                "还",
                "又",
                "再",
                "才",
                "只",
                "很",
                "太",
                "最",
                "更",
                "已",
                "已经",
                "正",
                "正在",
                "刚",
                "刚才",
                "常",
                "常常",
                "总",
                "总是",
            }
        ),
        prepositions=frozenset(
            {
                "在",
                "从",
                "到",
                "向",
                "往",
                "对",
                "给",
                "跟",
                "比",
                "为",
                "用",
                "按",
                "离",
                "沿",
                "关于",
            }
        ),
        conjunctions=frozenset(
            {
                "和",
                "与",
                "或",
                "或者",
                "但",
                "但是",
                "而",
                "而且",
                "因为",
                "所以",
                "如果",
                "虽然",
                "虽",
                "虽说",
                "尽管",
                "不但",
                "不仅",
                "既",
            }
        ),
        determiners=frozenset({"每", "各", "某", "些"}),
        interrogatives=frozenset({"谁", "什么", "哪里", "哪儿"}),
        demonstratives=frozenset(
            {"这", "那", "哪", "这些", "那些", "这里", "那里", "这儿", "那儿"}
        ),
    )
)

CHINESE_GRAMMATICAL_ONLY: Final[frozenset[str]] = union_subcategories(
    CHINESE_GRAMMATICAL_WORDS_BY_SUBCATEGORY, GRAMMATICAL_ONLY_SUBCATEGORIES
)

CHINESE_ALSO_LEMMA: Final[frozenset[str]] = union_subcategories(
    CHINESE_GRAMMATICAL_WORDS_BY_SUBCATEGORY, ALSO_LEMMA_SUBCATEGORIES
)

CHINESE_ALL_TIERS: Final[frozenset[str]] = frozenset(CHINESE_GRAMMATICAL_ONLY | CHINESE_ALSO_LEMMA)
