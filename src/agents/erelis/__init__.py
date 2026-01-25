"""Erelis (Eagle) Agent - False Lemma Match Detection.

This agent checks for sentences where a lemma is linked but the lemma's
translation doesn't appear in the sentence translation, indicating a
potential false match.

Example: "we had dinner" -> Chinese "我们吃了晚饭" (with 'eat')
If "吃了" is incorrectly linked to the lemma "to have", that's a false match
because the Chinese for "have" (有) doesn't appear in the sentence.
"""

from .agent import ErelisAgent, FalseLemmaMatch

__all__ = ["ErelisAgent", "FalseLemmaMatch"]
