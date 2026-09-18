"""Counting tokens, and being honest that we are guessing.

Nothing here tokenises the way a model does. A real count needs the model's own
tokeniser, which differs per provider and is a dependency and a download. So this is an
estimate, it says so in ``is_estimate``, and everything that reports a number carries
that flag with it — the same discipline as ``usage_reported`` in the gateway, and for the
same reason: a guess and a measurement must not look alike once they are written down.

**The estimate is biased upward on purpose.** For a budget, over-counting means fitting
fewer memories than strictly necessary, which costs a little quality. Under-counting
means overflowing the model's context window, which costs the whole request. The two
errors are not symmetrical, so the guess leans to the safe side.

**Chinese is counted at roughly one token per character**, against roughly one per four
characters for Latin text. That ratio is not a detail for a Hong Kong product: the same
document in Traditional Chinese costs several times more tokens than in English, which
shows up directly on the bill and is part of why the local model tier matters.
"""

from __future__ import annotations

import math
from typing import Protocol

from .tokenise import is_cjk

_LATIN_CHARS_PER_TOKEN = 4


class TokenCounter(Protocol):
    @property
    def is_estimate(self) -> bool: ...

    def count(self, text: str) -> int: ...


class HeuristicTokenCounter:
    """The default. Cheap, dependency-free, and openly approximate."""

    @property
    def is_estimate(self) -> bool:
        return True

    def count(self, text: str) -> int:
        if not text:
            return 0
        cjk = sum(1 for c in text if is_cjk(c))
        other = len(text) - cjk
        return cjk + math.ceil(other / _LATIN_CHARS_PER_TOKEN)
