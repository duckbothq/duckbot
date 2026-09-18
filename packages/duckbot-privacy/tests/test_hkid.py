"""HKID check-digit validation.

Every number in this file is invented. The check digits are computed by the algorithm,
not copied from a real card.
"""

from __future__ import annotations

import pytest

from duckbot_privacy import hkid

# (letters, digits, correct check digit)
KNOWN = [
    ("Z", "683365", "A"),
    ("A", "123456", "3"),
    ("K", "470285", "9"),
    ("AB", "987654", "3"),
    ("P", "550331", "4"),
    ("C", "665544", "9"),
]


@pytest.mark.parametrize(("letters", "digits", "check"), KNOWN)
def test_check_digit_is_stable(letters: str, digits: str, check: str) -> None:
    assert hkid.check_digit(letters, digits) == check


@pytest.mark.parametrize(("letters", "digits", "check"), KNOWN)
def test_valid_numbers_validate(letters: str, digits: str, check: str) -> None:
    assert hkid.is_valid(letters, digits, check)


@pytest.mark.parametrize(("letters", "digits", "check"), KNOWN)
def test_wrong_check_digit_is_rejected(letters: str, digits: str, check: str) -> None:
    wrong = "0" if check != "0" else "1"
    assert not hkid.is_valid(letters, digits, wrong)


def test_check_digit_of_ten_is_written_as_a() -> None:
    assert hkid.check_digit("Z", "683365") == "A"
    assert hkid.is_valid("Z", "683365", "a"), "lower case must be accepted"


def test_case_is_not_significant() -> None:
    assert hkid.is_valid("ab", "987654", "3")


def test_malformed_input_is_false_not_an_exception() -> None:
    assert not hkid.is_valid("A", "12345", "1")
    assert not hkid.is_valid("A", "12345X", "1")
    assert not hkid.is_valid("ABC", "123456", "1")
    assert not hkid.is_valid("", "123456", "1")
    assert not hkid.is_valid("1", "123456", "1")


def test_find_all_accepts_the_common_written_forms() -> None:
    text = "身份證 A123456(3)、K470285(9) 同 AB987654(3) 都要遮。"
    found = hkid.find_all(text)
    assert [m for _, _, m in found] == ["A123456(3)", "K470285(9)", "AB987654(3)"]


def test_find_all_offsets_point_at_the_match() -> None:
    text = "編號：A123456(3) 完"
    ((start, end, matched),) = hkid.find_all(text)
    assert text[start:end] == matched


def test_find_all_discards_a_bad_check_digit() -> None:
    """The whole value of the detector is that it does not cry wolf."""
    assert hkid.find_all("參考編號 A123456(9)") == []


def test_find_all_ignores_a_number_inside_a_longer_token() -> None:
    assert hkid.find_all("SKU-XA123456(3)9") == []


def test_find_all_tolerates_missing_brackets_and_spacing() -> None:
    assert len(hkid.find_all("A 123456 3")) == 1
