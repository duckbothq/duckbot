"""Hong Kong Identity Card numbers, with check-digit validation.

A bare regular expression for an HKID matches a great deal that is not one — product
codes, reference numbers, anything shaped like a letter followed by six digits. The
check digit is what makes the difference between a detector a professional firm will
trust and one that cries wolf until somebody turns it off.

Format: one or two letters, six digits, and a check digit in brackets. The check digit
is 0–9 or A.

The algorithm: each character is weighted by its position, counting down from 9 for a
two-letter number. A one-letter number is treated as though it were space-padded on the
left, and the space has value 36. Letters are 10 for A through 35 for Z. The weighted
sum plus the check digit must be divisible by 11, where a check digit of A counts as 10.
"""

from __future__ import annotations

import re

HKID_PATTERN = re.compile(
    r"""
    (?<![A-Za-z0-9])          # not part of a longer token
    (?P<letters>[A-Za-z]{1,2})
    \s?
    (?P<digits>\d{6})
    \s?
    \(?(?P<check>[0-9Aa])\)?
    (?![A-Za-z0-9])
    """,
    re.VERBOSE,
)

_SPACE_VALUE = 36


def _char_value(char: str) -> int:
    if char == " ":
        return _SPACE_VALUE
    if char.isdigit():
        return int(char)
    return ord(char.upper()) - ord("A") + 10


def check_digit(letters: str, digits: str) -> str:
    """Return the correct check digit for a letter/digit pair."""
    body = letters.upper().rjust(2, " ") + digits
    total = sum(_char_value(c) * (9 - i) for i, c in enumerate(body))
    remainder = total % 11
    value = (11 - remainder) % 11
    return "A" if value == 10 else str(value)


def is_valid(letters: str, digits: str, check: str) -> bool:
    """True when the check digit is consistent with the rest of the number."""
    if len(digits) != 6 or not digits.isdigit():
        return False
    if not letters.isalpha() or not 1 <= len(letters) <= 2:
        return False
    return check_digit(letters, digits) == check.upper()


def find_all(text: str) -> list[tuple[int, int, str]]:
    """Return ``(start, end, matched_text)`` for every *valid* HKID in the text.

    Candidates that fail the check digit are discarded. That is the point: the detector
    is only useful if the people relying on it believe its output.
    """
    found: list[tuple[int, int, str]] = []
    for match in HKID_PATTERN.finditer(text):
        letters = match.group("letters")
        digits = match.group("digits")
        check = match.group("check")
        if is_valid(letters, digits, check):
            found.append((match.start(), match.end(), match.group(0)))
    return found
