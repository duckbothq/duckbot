"""Cost arithmetic, and the refusal to guess.

Every price in this file is invented. Real prices belong in an operator's own price
file, sourced from the provider's page, which is why this package ships none.
"""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from duckbot_schemas import ModelTier, Money, SensitivityLevel

from duckbot_gateway import ModelDescriptor, ModelPrice, PriceTable, UnknownPrice, add_money

EXAMPLE_PRICES = Path(__file__).resolve().parents[1] / "config" / "prices.example.json"


def price(**overrides: object) -> ModelPrice:
    values: dict[str, object] = {
        "provider": "example-cheap",
        "model": "fast-1",
        "input_per_mtok": Decimal("1"),
        "output_per_mtok": Decimal("2"),
        "currency": "USD",
        "source": "invented for tests",
        "checked_on": date(2026, 9, 1),
    }
    values.update(overrides)
    return ModelPrice(**values)  # type: ignore[arg-type]


class TestCost:
    def test_it_is_exact(self, prices: PriceTable, cheap_descriptor: ModelDescriptor) -> None:
        """One dollar per million in, two out: 1000 in and 500 out is 0.002 exactly."""
        cost = prices.cost(cheap_descriptor, tokens_in=1000, tokens_out=500)
        assert cost.amount == "0.00200000"
        assert cost.currency == "USD"

    def test_small_calls_do_not_round_to_nothing(
        self, prices: PriceTable, cheap_descriptor: ModelDescriptor
    ) -> None:
        """Eight decimal places, because a cheap call costs less than a thousandth of a cent."""
        cost = prices.cost(cheap_descriptor, tokens_in=1, tokens_out=0)
        assert Decimal(cost.amount) > 0

    def test_a_local_model_is_free(
        self, prices: PriceTable, local_descriptor: ModelDescriptor
    ) -> None:
        assert prices.cost(local_descriptor, tokens_in=9999, tokens_out=9999).amount == "0"

    def test_an_unpriced_model_raises_rather_than_costing_nothing(
        self, cheap_descriptor: ModelDescriptor
    ) -> None:
        """A silent zero understates the bill, and the first to notice is the person paying."""
        with pytest.raises(UnknownPrice, match="no price configured"):
            PriceTable().cost(cheap_descriptor, tokens_in=10, tokens_out=10)

    def test_negative_token_counts_are_refused(
        self, prices: PriceTable, cheap_descriptor: ModelDescriptor
    ) -> None:
        with pytest.raises(ValueError):
            prices.cost(cheap_descriptor, tokens_in=-1, tokens_out=0)


class TestPriceRecord:
    def test_a_price_must_say_where_it_came_from(self) -> None:
        with pytest.raises(ValueError, match="where it came from"):
            price(source="  ")

    def test_a_negative_price_is_refused(self) -> None:
        with pytest.raises(ValueError):
            price(input_per_mtok=Decimal("-1"))

    def test_staleness_is_measured_from_when_a_person_checked(self) -> None:
        p = price(checked_on=date(2026, 1, 1))
        assert p.age_days(as_of=date(2026, 9, 18)) == 260
        assert p.is_stale(as_of=date(2026, 9, 18))
        assert not p.is_stale(as_of=date(2026, 1, 15))

    def test_stale_prices_are_reported_not_enforced(self, prices: PriceTable) -> None:
        """Refusing to price a call because the figure is old would break billing."""
        prices.add(price(model="old-1", checked_on=date(2025, 1, 1)))
        stale = prices.stale(as_of=date(2026, 9, 18))
        assert [p.model for p in stale] == ["old-1"]


class TestAddMoney:
    def test_totals_are_exact(self) -> None:
        total = add_money(Money(amount="0.00000001"), Money(amount="0.00000002"))
        assert total.amount == "0.00000003"

    def test_no_arguments_is_zero(self) -> None:
        assert add_money().amount == "0"

    def test_mixed_currencies_are_refused_rather_than_converted(self) -> None:
        """A conversion needs a rate and a date. Picking one quietly makes the total a guess."""
        with pytest.raises(ValueError, match="different currencies"):
            add_money(Money(amount="1", currency="USD"), Money(amount="1", currency="HKD"))


class TestTheExampleFile:
    def test_it_ships_without_figures(self) -> None:
        """Deliberate. A price baked in here would be quoted to a customer a year later."""
        entries = json.loads(EXAMPLE_PRICES.read_text(encoding="utf-8"))
        assert entries
        for entry in entries:
            assert entry["input_per_mtok"] is None
            assert entry["output_per_mtok"] is None
            assert entry["source"]
            assert entry["checked_on"]

    def test_loading_it_says_what_is_missing(self) -> None:
        with pytest.raises(UnknownPrice, match="input_per_mtok"):
            PriceTable.from_file(EXAMPLE_PRICES)

    def test_a_filled_in_file_loads(self, tmp_path: Path) -> None:
        path = tmp_path / "prices.json"
        path.write_text(
            json.dumps(
                [
                    {
                        "provider": "example-cheap",
                        "model": "fast-1",
                        "input_per_mtok": "1",
                        "output_per_mtok": "2",
                        "currency": "USD",
                        "source": "invented for tests",
                        "checked_on": "2026-09-01",
                    }
                ]
            ),
            encoding="utf-8",
        )
        table = PriceTable.from_file(path)
        loaded = table.get("example-cheap/fast-1")
        assert loaded is not None
        assert loaded.input_per_mtok == Decimal("1")

    def test_prices_are_read_as_decimals_not_floats(self, tmp_path: Path) -> None:
        """0.1 + 0.2 is the reason this package never touches float."""
        path = tmp_path / "prices.json"
        path.write_text(
            json.dumps(
                [
                    {
                        "provider": "p",
                        "model": "m",
                        "input_per_mtok": 0.1,
                        "output_per_mtok": 0.2,
                        "source": "invented",
                        "checked_on": "2026-09-01",
                    }
                ]
            ),
            encoding="utf-8",
        )
        table = PriceTable.from_file(path)
        descriptor = ModelDescriptor(
            provider="p",
            model="m",
            tier=ModelTier.LOW_COST,
            context_window=1000,
            max_sensitivity=SensitivityLevel.PUBLIC,
        )
        assert table.cost(descriptor, tokens_in=1_000_000, tokens_out=1_000_000).amount == (
            "0.30000000"
        )
