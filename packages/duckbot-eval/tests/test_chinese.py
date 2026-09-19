"""The Simplified-character detector.

Precision matters far more than recall here: reporting "this model writes Simplified"
when it does not is a wrong verdict on a real purchasing decision.
"""

from __future__ import annotations

import pytest

from duckbot_eval import SIMPLIFIED_ONLY, looks_simplified, simplified_characters

TRADITIONAL = (
    "香港特別行政區政府資訊科技總監辦公室發出最新指引，後面嗰個台只係干手淨腳，裡面冇乜嘢要處理。"
)


class TestPrecision:
    def test_ordinary_traditional_writing_is_clean(self) -> None:
        assert not looks_simplified(TRADITIONAL)
        assert simplified_characters(TRADITIONAL) == []

    @pytest.mark.parametrize("char", ["後", "裡", "里", "只", "干", "台", "面", "系", "采", "戶"])
    def test_characters_valid_in_both_scripts_are_not_flagged(self, char: str) -> None:
        """Every one of these is ordinary Traditional Chinese as well as Simplified."""
        assert char not in SIMPLIFIED_ONLY

    def test_english_is_not_flagged(self) -> None:
        assert not looks_simplified("The tenancy agreement renewal is due in March")


class TestDetection:
    def test_a_simplified_sentence_is_caught(self) -> None:
        assert looks_simplified("这个报告说时间已经过了")

    def test_the_offending_characters_are_named(self) -> None:
        """So a failing report says what it saw rather than only that it disapproved."""
        assert simplified_characters("这个报告") == ["这", "个", "报"]

    def test_repeats_are_reported_once(self) -> None:
        assert simplified_characters("这这这个") == ["这", "个"]

    def test_the_traditional_form_of_a_flagged_character_is_not_flagged(self) -> None:
        assert looks_simplified("这個") and not looks_simplified("這個")

    def test_mixed_output_is_caught(self) -> None:
        """The realistic failure: a model that mostly writes Traditional and slips."""
        assert looks_simplified("客戶陳嘉雯的年度审计報告")
