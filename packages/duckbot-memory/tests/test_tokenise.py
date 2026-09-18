"""Tokenisation, and the Chinese cases a whitespace tokeniser silently fails."""

from __future__ import annotations

import pytest

from duckbot_memory import is_cjk, normalise, tokenise


class TestChinese:
    def test_a_run_becomes_bigrams(self) -> None:
        assert tokenise("年度審計") == ["年度", "度審", "審計"]

    def test_a_query_term_matches_a_substring_of_a_longer_run(self) -> None:
        """The whole point: 審計 is findable inside 客戶的年度審計報告."""
        assert set(tokenise("審計")) <= set(tokenise("客戶的年度審計報告"))

    def test_a_single_character_is_still_a_token(self) -> None:
        assert tokenise("香") == ["香"]

    def test_the_ideographic_zero_does_not_split_a_year(self) -> None:
        """二〇二六 is ordinary Chinese date writing; 〇 lives outside the ideograph blocks."""
        assert "二〇" in tokenise("二〇二六年")

    def test_punctuation_separates_rather_than_joins(self) -> None:
        """、and 。are in the same Unicode block as 〇 and must not become tokens."""
        tokens = tokenise("報告、附件。")
        assert tokens == ["報告", "附件"]


class TestLatin:
    def test_words_are_words(self) -> None:
        assert tokenise("Tenancy agreement renewal") == ["tenancy", "agreement", "renewal"]

    def test_case_does_not_matter(self) -> None:
        assert tokenise("ACME Ltd") == tokenise("acme ltd")

    def test_numbers_are_kept(self) -> None:
        assert "2026" in tokenise("due in 2026")


class TestMixed:
    def test_both_scripts_in_one_string(self) -> None:
        tokens = tokenise("二〇二六年 Q3 report")
        assert "q3" in tokens
        assert "report" in tokens
        assert "六年" in tokens

    def test_full_width_latin_matches_half_width(self) -> None:
        """Full-width characters come out of a Chinese IME constantly."""
        assert tokenise("ＨＫ") == tokenise("HK")

    def test_empty_text_is_no_tokens(self) -> None:
        assert tokenise("") == []
        assert tokenise("，。、") == []


class TestHelpers:
    @pytest.mark.parametrize("char", ["香", "港", "審", "〇"])
    def test_cjk_is_recognised(self, char: str) -> None:
        assert is_cjk(char)

    @pytest.mark.parametrize("char", ["a", "1", " ", "、", "。"])
    def test_non_cjk_is_not(self, char: str) -> None:
        assert not is_cjk(char)

    def test_normalise_is_case_folded_and_nfkc(self) -> None:
        assert normalise("ＡＢc") == "abc"
