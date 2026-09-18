"""Splitting text into searchable units, in a way that works on Chinese.

Most retrieval code assumes words are separated by spaces. Traditional Chinese is not
written that way, and a whitespace tokeniser handed 「客戶陳嘉雯的年度審計報告」 produces one
enormous token that matches nothing. That is not a small degradation; it is the search
silently not working for most of our customers' documents.

The approach here is **character bigrams for CJK and words for everything else**, which
is the standard cheap answer and a good one: 「年度審計」 yields 年度, 度審, 審計, so a query
for 審計 matches. It needs no dictionary, no model and no segmentation library, which
matters because every one of those is a dependency, a licence and a download.

What it is not: it is not word segmentation, and a bigram index will occasionally match
across a word boundary — 「香港大學生」 produces 港大, which would match a query for 港大 even
though the text says something else. That is a precision cost we accept for having no
dependency and no model, and it is the sort of thing a proper segmenter fixes later.
"""

from __future__ import annotations

import re
import unicodedata
from itertools import pairwise

_LATIN_WORD = re.compile(r"[0-9a-z]+")

_CJK_RANGES = (
    (0x3007, 0x3007),  # 〇, the ideographic zero
    (0x3400, 0x4DBF),  # extension A
    (0x4E00, 0x9FFF),  # unified ideographs
    (0xF900, 0xFAFF),  # compatibility ideographs
    (0x20000, 0x2FA1F),  # extensions B onward
)
"""〇 is listed on its own rather than by taking its whole block.

It lives in CJK Symbols and Punctuation, alongside 、。「」— which must *not* become
tokens. But 〇 is a digit in ordinary Chinese date writing, and without it 二〇二六年
tokenises as two broken runs and a search for 二〇二六 finds nothing."""


def is_cjk(char: str) -> bool:
    code = ord(char)
    return any(low <= code <= high for low, high in _CJK_RANGES)


def normalise(text: str) -> str:
    """Case-folded and NFKC-normalised.

    NFKC matters more here than it looks: full-width digits and Latin letters are common
    in documents typed on a Chinese IME, and 'ＨＫ' not matching 'HK' would be a puzzling
    bug to be told about by a customer.
    """
    return unicodedata.normalize("NFKC", text).casefold()


def tokenise(text: str) -> list[str]:
    """Latin words, CJK character bigrams, and single CJK characters at the boundaries.

    A lone CJK character is emitted when it has no neighbour to pair with, so that a
    one-character term is still findable.
    """
    normalised = normalise(text)
    tokens: list[str] = []

    run: list[str] = []
    for char in normalised:
        if is_cjk(char):
            run.append(char)
            continue
        if run:
            tokens.extend(_bigrams(run))
            run = []
    if run:
        tokens.extend(_bigrams(run))

    tokens.extend(_LATIN_WORD.findall(normalised))
    return tokens


def _bigrams(run: list[str]) -> list[str]:
    if len(run) == 1:
        return [run[0]]
    return ["".join(pair) for pair in pairwise(run)]
