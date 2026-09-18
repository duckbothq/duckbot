"""Rule-based detectors for Hong Kong business documents.

Honest scope. Rules do some things very well and some things badly, and pretending
otherwise produces a detector nobody trusts:

* **Reliable**: HKID (check-digit validated), phone numbers, email addresses, business
  registration numbers, monetary amounts. These have structure, and structure is what
  rules are for.
* **Partial**: personal names. The heuristics here catch common shapes — a Hong Kong
  Chinese surname followed by one or two characters, or a romanised name written with
  the surname in capitals — and will miss others. Names are the local model's job; these
  rules are the floor, not the ceiling.
* **Not attempted**: addresses. Hong Kong addresses are too varied for rules to reach
  useful recall, and a detector with poor recall on an entity type is worse than no
  detector, because it produces false confidence.

Recall matters far more than precision here. An over-redaction annoys the user; a missed
HKID destroys the reason the product exists.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass

from . import hkid


@dataclass(frozen=True)
class Detection:
    """One match, before it becomes a schema object."""

    entity_type: str
    start: int
    end: int
    text: str
    confidence: float


# Hong Kong Chinese surnames, curated rather than exhaustive.
#
# Characters that are far more common as ordinary words than as surnames are deliberately
# excluded — 高, 文, 方, 石, 白, 毛, 江, 史, 田, 常, 武, 易, 湯 and their like. Including them
# raises recall on paper and produces an over-redacting detector in practice, and an
# over-redacting detector is one the customer switches off.
HK_SURNAMES = frozenset(
    "陳李黃張何歐周吳劉蔡楊許鄭謝郭馬林葉梁徐朱孫盧曾蕭鄧傅鍾程曹袁"
    "潘杜戴夏姜范鄒熊邵孟龍萬段雷錢尹黎喬賀賴莫溫馮邱翁崔顏廖邢邊"
)

_SURNAME_CLASS = "".join(sorted(HK_SURNAMES))

# Titles and roles that make a name a name. Chinese runs without spaces, so a bare
# "surname plus one or two characters" pattern matches an enormous amount of ordinary
# prose. Anchoring on context is what makes this usable.
_NAME_PREFIX = "(?:員工|同事|客戶|家長|學生|申請人|負責人|聯絡人|經辦人|新同事|職員)"
_NAME_SUFFIX = "(?:先生|小姐|女士|太太|經理|主任|老師|醫生|律師|會計師|工程師)"

# No look-behind: the prefixes have different lengths and Python requires a fixed-width
# look-behind. The prefix is matched normally and only the name group's span is used.
# A connector often sits between the role word and the name — 負責人*為*何志強. Note that
# this particular example is genuinely ambiguous: 為何 also means "why", so the surname 何
# after 為 is exactly the case a rule cannot settle and a model can.
_CJK_NAME_WITH_PREFIX = re.compile(
    rf"{_NAME_PREFIX}(?:為|是|叫|係)?\s*(?P<name>[{_SURNAME_CLASS}][\u4e00-\u9fff]{{1,2}})"
)
_CJK_NAME_WITH_SUFFIX = re.compile(
    rf"(?P<name>[{_SURNAME_CLASS}][\u4e00-\u9fff]{{1,2}})(?={_NAME_SUFFIX})"
)
_CJK_NAME_AFTER_LABEL = re.compile(
    rf"(?:姓名|名稱|客戶|收件人|申請人)\s*[:：]\s*(?P<name>[{_SURNAME_CLASS}][\u4e00-\u9fff]{{1,2}})"
)

_ROMANISED_NAME = re.compile(r"(?<![A-Za-z])((?:[A-Z]{2,})(?:\s+[A-Z][a-z]+){1,3})(?![A-Za-z])")

_PHONE = re.compile(
    r"""
    (?<![\d])
    (?:\+?852[\s-]?)?
    (?P<number>[23569]\d{3}[\s-]?\d{4})
    (?![\d])
    """,
    re.VERBOSE,
)

_EMAIL = re.compile(r"(?<![\w.])[\w.+-]+@[\w-]+\.[\w.-]+(?![\w])")

# Business Registration: eight digits, then a three-digit branch code.
_BR_NUMBER = re.compile(r"(?<![\d])(\d{8}[-\s]?\d{3})(?![\d])")

_MONEY = re.compile(
    r"""
    (?<![\w])
    (?:HK\$|HKD|港幣|\$)
    \s?
    \d{1,3}(?:,\d{3})*(?:\.\d{1,2})?
    (?![\w])
    """,
    re.VERBOSE | re.IGNORECASE,
)

_SALARY_CONTEXT = re.compile(r"(月薪|年薪|薪金|salary|remuneration)", re.IGNORECASE)


def detect_hkid(text: str) -> list[Detection]:
    return [
        Detection("HKID", start, end, matched, 0.99) for start, end, matched in hkid.find_all(text)
    ]


def detect_phone(text: str) -> list[Detection]:
    out: list[Detection] = []
    for m in _PHONE.finditer(text):
        out.append(Detection("PHONE", m.start(), m.end(), m.group(0), 0.9))
    return out


def detect_email(text: str) -> list[Detection]:
    return [Detection("EMAIL", m.start(), m.end(), m.group(0), 0.98) for m in _EMAIL.finditer(text)]


def detect_br_number(text: str) -> list[Detection]:
    return [
        Detection("BR_NUMBER", m.start(), m.end(), m.group(0), 0.7)
        for m in _BR_NUMBER.finditer(text)
    ]


def detect_money(text: str) -> list[Detection]:
    """Monetary amounts.

    Confidence is raised when the surrounding text mentions salary, because a salary is
    materially more sensitive than a quotation total and the policy layer may want to
    treat it differently.
    """
    out: list[Detection] = []
    for m in _MONEY.finditer(text):
        window = text[max(0, m.start() - 40) : m.end() + 20]
        salary = bool(_SALARY_CONTEXT.search(window))
        out.append(
            Detection(
                "SALARY" if salary else "MONEY",
                m.start(),
                m.end(),
                m.group(0),
                0.9 if salary else 0.8,
            )
        )
    return out


def detect_person_name(text: str) -> list[Detection]:
    """Personal names — partial by construction. See the module docstring.

    Chinese names are anchored on context: a role word before, a title after, or an
    explicit label. Without an anchor, "surname plus one or two characters" matches far
    too much ordinary prose to be usable, and the local model is the right tool for the
    unanchored case.

    This is the entity type where the rule layer is weakest, and the corpus report says
    so rather than hiding it behind an overall average.
    """
    out: list[Detection] = []
    for pattern, confidence in (
        (_CJK_NAME_WITH_PREFIX, 0.75),
        (_CJK_NAME_WITH_SUFFIX, 0.8),
        (_CJK_NAME_AFTER_LABEL, 0.85),
    ):
        for m in pattern.finditer(text):
            out.append(
                Detection(
                    "PERSON_NAME", m.start("name"), m.end("name"), m.group("name"), confidence
                )
            )
    for m in _ROMANISED_NAME.finditer(text):
        out.append(Detection("PERSON_NAME", m.start(), m.end(), m.group(0), 0.55))
    return out


Detector = Callable[[str], list["Detection"]]
"""A detector takes text and returns detections. Nothing more, so they compose."""


ALL_DETECTORS: tuple[Detector, ...] = (
    detect_hkid,
    detect_email,
    detect_phone,
    detect_money,
    detect_br_number,
    detect_person_name,
)


def _overlaps(a: Detection, b: Detection) -> bool:
    return a.start < b.end and b.start < a.end


def resolve_overlaps(detections: Iterable[Detection]) -> list[Detection]:
    """Keep the most trustworthy detection where two overlap.

    An HKID contains a run of digits that other patterns will also match. Preferring the
    longer span, then the higher confidence, keeps the strongest structural match — the
    one with a verified check digit — rather than a fragment of it.
    """
    ordered = sorted(detections, key=lambda d: (-(d.end - d.start), -d.confidence, d.start))
    kept: list[Detection] = []
    for candidate in ordered:
        if not any(_overlaps(candidate, k) for k in kept):
            kept.append(candidate)
    return sorted(kept, key=lambda d: d.start)


_MIN_PROPAGATION_LENGTH = 3


def propagate_known_values(text: str, detections: Sequence[Detection]) -> list[Detection]:
    """Redact every occurrence of a value, not only the one that carried the anchor.

    A name is introduced once with a role word — 客戶陳嘉雯 — and used bare for the rest of
    the document. Only the anchored occurrence is detected, so the value leaks from the
    same document in which it was already identified. Once a detector has committed to a
    value, every other literal occurrence of it is the same value, and re-using that
    decision costs nothing in precision: no pattern is widened, and nothing is redacted
    that was not already judged sensitive somewhere above.

    Short values are excluded. A two-character Chinese name is also an ordinary word —
    張開, 李子 — and propagating one would redact prose. Below
    ``_MIN_PROPAGATION_LENGTH`` characters a value keeps only its anchored occurrences,
    which is a deliberate hole and the local model's job to close.
    """
    best: dict[tuple[str, str], float] = {}
    for d in detections:
        key = (d.text, d.entity_type)
        best[key] = max(best.get(key, 0.0), d.confidence)

    extra: list[Detection] = []
    for (value, entity_type), confidence in best.items():
        if len(value) < _MIN_PROPAGATION_LENGTH:
            continue
        start = text.find(value)
        while start != -1:
            extra.append(Detection(entity_type, start, start + len(value), value, confidence))
            start = text.find(value, start + 1)
    return [*detections, *extra]


def detect_all(text: str, detectors: Sequence[Detector] = ALL_DETECTORS) -> list[Detection]:
    found: list[Detection] = []
    for detector in detectors:
        found.extend(detector(text))
    # Resolve first, so that only surviving detections are propagated — a fragment that
    # lost to a longer match should not come back through the second pass.
    resolved = resolve_overlaps(found)
    return resolve_overlaps(propagate_known_values(text, resolved))
