"""Is this Traditional Chinese?

A small multilingual model will often answer a Cantonese or Traditional Chinese prompt in
Simplified. For a Hong Kong customer that output is unusable — not slightly worse,
unusable — and it is the single most common way a model that benchmarks well turns out
to be unsuitable here. No general benchmark measures it. It is also cheap to detect
exactly, which makes leaving it unmeasured indefensible.

The detector is deliberately built for **precision over recall**. Reporting "this model
writes Simplified" when it does not would be a wrong verdict on a real decision, so the
set below holds only high-frequency characters whose Simplified form is not also valid
Traditional. Characters that exist in both — 后, 里, 只, 干, 台, 面, 采, 系 — are excluded
even though they are common in Simplified text, because their presence proves nothing.

The consequence is that a text with one unusual Simplified character may pass. That is
the intended trade: this answers "did the model switch script", which shows up in whole
sentences, not "is every character correct".
"""

from __future__ import annotations

SIMPLIFIED_ONLY = frozenset(
    "这个为国说时会学电无与东点务员银业产发关门问间对应该请报处备单价认证记录联络资讯"
    "长风飞马鸟鱼龙点党团军师农业医药经济营销购买卖贷账户头条见观觉视听读写译语"
    "书画图画术艺质体丰华亲爱乐欢乡镇县区总统计划设计开关闭闻问题际标准张纸笔"
)
"""Simplified forms whose Traditional counterpart is a different character.

Curated rather than exhaustive, and conservative by design. If you add to it, check the
character is not itself a valid Traditional character — 户, 后, 里, 只, 干, 台 all are,
and every one of them appears constantly in ordinary Hong Kong writing.
"""


def simplified_characters(text: str) -> list[str]:
    """Every Simplified-only character in the text, in order, without repeats."""
    return list(dict.fromkeys(c for c in text if c in SIMPLIFIED_ONLY))


def looks_simplified(text: str) -> bool:
    """True when the text contains any Simplified-only character."""
    return any(c in SIMPLIFIED_ONLY for c in text)
