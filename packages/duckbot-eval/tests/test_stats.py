"""Scores with their precision attached."""

from __future__ import annotations

import pytest

from duckbot_eval import cases_needed, wilson


class TestWilson:
    def test_a_small_run_produces_an_honest_interval(self) -> None:
        """8/10 is not 80%; it is somewhere between half and almost all."""
        rate = wilson(8, 10)
        assert rate.value == pytest.approx(0.8)
        assert rate.low < 0.55
        assert rate.high > 0.9

    def test_more_cases_narrow_it(self) -> None:
        assert wilson(80, 100).width < wilson(8, 10).width

    def test_a_perfect_score_does_not_claim_certainty(self) -> None:
        """5/5 is not proof. The lower bound says so."""
        rate = wilson(5, 5)
        assert rate.value == 1.0
        assert rate.low < 0.7

    def test_a_zero_score_stays_within_range(self) -> None:
        """The normal approximation produces a negative bound here. Wilson does not."""
        rate = wilson(0, 5)
        assert rate.low == 0.0
        assert 0.0 < rate.high < 1.0

    def test_no_cases_is_not_a_division_by_zero(self) -> None:
        rate = wilson(0, 0)
        assert rate.value == 0.0
        assert str(rate) == "n/a (no cases)"

    def test_impossible_counts_are_refused(self) -> None:
        with pytest.raises(ValueError):
            wilson(6, 5)
        with pytest.raises(ValueError):
            wilson(-1, 5)

    def test_the_string_form_carries_the_interval(self) -> None:
        """So a figure cannot be copied out of the report without it."""
        rendered = str(wilson(8, 10))
        assert "8/10" in rendered
        assert "95% CI" in rendered


class TestCasesNeeded:
    def test_it_reports_a_number_large_enough_to_settle_the_argument(self) -> None:
        assert cases_needed(0.9, 0.05) > 100

    def test_a_looser_target_needs_fewer(self) -> None:
        assert cases_needed(0.9, 0.10) < cases_needed(0.9, 0.05)

    def test_nonsense_inputs_are_refused(self) -> None:
        with pytest.raises(ValueError):
            cases_needed(1.5, 0.05)
        with pytest.raises(ValueError):
            cases_needed(0.9, 0)
