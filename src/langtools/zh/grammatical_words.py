"""Chinese grammatical/function-word data.

* **grammatical_only** – structural particles (的/地/得), aspect markers
  (了/着/过), modal particles, personal pronouns, plural marker, negation,
  grammatical adverbs, and the *bǎ/bèi/ràng* construction markers.
* **also_lemma** – coverbs/prepositions that double as verbs (从/到/给/…),
  conjunctions, demonstratives, interrogatives, copula 是, existential 有,
  and auxiliaries with independent verb senses (想/能/会/要).

Measure words are excluded even when awkward to translate.
"""

from typing import Final

# ── tier 1: always grammatical, never a lemma ──────────────────────────

CHINESE_GRAMMATICAL_ONLY: Final[frozenset[str]] = frozenset(
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
        # Personal pronouns
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
        # Grammatical adverbs (modify verb/sentence structure)
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

# ── tier 2: function words that are (or could be) lemmas ───────────────

CHINESE_ALSO_LEMMA: Final[frozenset[str]] = frozenset(
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
        "这里",
        "那里",
        "这儿",
        "那儿",
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

# ── combined set ───────────────────────────────────────────────────────

CHINESE_GRAMMATICAL_WORDS: Final[frozenset[str]] = frozenset(
    CHINESE_GRAMMATICAL_ONLY | CHINESE_ALSO_LEMMA
)
