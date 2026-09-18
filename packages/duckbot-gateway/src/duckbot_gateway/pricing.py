"""What a call cost, computed exactly.

Three decisions worth knowing about before changing anything here.

**Decimal, not float.** Per-call costs are small and there are a great many of them. A
float accumulation is wrong by an amount nobody notices until it is compared against an
invoice. ``Money`` carries a decimal string for the same reason.

**An unknown price is an error, not a zero.** A gateway that silently prices an unknown
model at nothing produces a cost report that understates the bill.

**We do not ship prices.** ``config/prices.example.json`` has the right shape and no
numbers. Provider pricing changes without notice, and a figure baked into this package
by whoever wrote it would be quoted to a customer six months later by someone who
assumed it was maintained. Each entry carries the page it came from and the date
somebody checked it, so a stale one can be found rather than guessed at.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

from duckbot_schemas import ModelTier, Money

from .descriptors import ModelDescriptor
from .errors import UnknownPrice

TOKENS_PER_UNIT = Decimal(1_000_000)
"""Provider prices are quoted per million tokens. Changing this changes nothing else."""

_CENTS = Decimal("0.00000001")
"""Eight decimal places. A single cheap call can cost less than a thousandth of a cent."""

DEFAULT_MAX_AGE_DAYS = 90
"""How old a checked price may be before it is reported as stale."""


def _plain(value: Decimal) -> str:
    """Decimal as plain digits, never scientific notation.

    ``str(Decimal("3E-8"))`` keeps the exponent, and ``Money`` refuses it — correctly, as
    a cost record that reads ``3E-8`` is a cost record nobody can scan. A sub-cent figure
    is exactly the size a per-call cost tends to be, so this is the normal path, not an
    edge case.
    """
    return format(value, "f")


@dataclass(frozen=True)
class ModelPrice:
    """The price of one model, and the evidence for it."""

    provider: str
    model: str
    input_per_mtok: Decimal
    output_per_mtok: Decimal
    currency: str
    source: str
    """Where the figure came from — a pricing page, a contract, an invoice."""
    checked_on: date
    """When a person last confirmed it. Not when this file was edited."""

    def __post_init__(self) -> None:
        if self.input_per_mtok < 0 or self.output_per_mtok < 0:
            raise ValueError("a price cannot be negative")
        if not self.source.strip():
            raise ValueError(
                f"the price for {self.provider}/{self.model} must record where it came "
                "from; an unsourced price is a number somebody will have to re-derive"
            )

    @property
    def key(self) -> str:
        return f"{self.provider}/{self.model}"

    def age_days(self, as_of: date | None = None) -> int:
        return ((as_of or datetime.now(UTC).date()) - self.checked_on).days

    def is_stale(self, as_of: date | None = None, max_age_days: int = DEFAULT_MAX_AGE_DAYS) -> bool:
        return self.age_days(as_of) > max_age_days


class PriceTable:
    """Prices for every model that costs money."""

    def __init__(self, prices: list[ModelPrice] | None = None) -> None:
        self._prices: dict[str, ModelPrice] = {p.key: p for p in prices or []}

    def add(self, price: ModelPrice) -> None:
        self._prices[price.key] = price

    def get(self, key: str) -> ModelPrice | None:
        return self._prices.get(key)

    def stale(
        self, as_of: date | None = None, max_age_days: int = DEFAULT_MAX_AGE_DAYS
    ) -> list[ModelPrice]:
        """Prices nobody has confirmed recently. Surfaced, never acted on automatically.

        Refusing to compute a cost because a price is old would break billing at the
        worst possible moment. Reporting it lets an operator fix it before it matters.
        """
        return sorted(
            (p for p in self._prices.values() if p.is_stale(as_of, max_age_days)),
            key=lambda p: p.checked_on,
        )

    def cost(self, descriptor: ModelDescriptor, *, tokens_in: int, tokens_out: int) -> Money:
        """What this call cost.

        A local model is free — not approximately free, but zero, because no money
        changes hands. ``ModelCall`` enforces the same thing from the other side.
        """
        if tokens_in < 0 or tokens_out < 0:
            raise ValueError("token counts cannot be negative")
        if descriptor.tier is ModelTier.LOCAL:
            return Money(amount="0", currency="USD")

        price = self._prices.get(descriptor.key)
        if price is None:
            raise UnknownPrice(
                f"no price configured for {descriptor.key}. Add it to the price file with "
                "the page it came from and the date you checked, or the cost report for "
                "every task using this model will be wrong and silently so."
            )

        total = (
            Decimal(tokens_in) * price.input_per_mtok + Decimal(tokens_out) * price.output_per_mtok
        ) / TOKENS_PER_UNIT
        return Money(
            amount=_plain(total.quantize(_CENTS, rounding=ROUND_HALF_UP)),
            currency=price.currency,
        )

    @classmethod
    def from_file(cls, path: Path | str) -> PriceTable:
        """Load a price file. See ``config/prices.example.json`` for the shape."""
        raw: list[dict[str, Any]] = json.loads(Path(path).read_text(encoding="utf-8"))
        table = cls()
        for item in raw:
            for required in ("input_per_mtok", "output_per_mtok"):
                if item.get(required) is None:
                    raise UnknownPrice(
                        f"{item.get('provider')}/{item.get('model')} has no "
                        f"{required}. The example file ships without figures on purpose: "
                        "fill in what your account is actually charged, from the "
                        "provider's own pricing page, rather than inheriting a number "
                        "somebody guessed."
                    )
            table.add(
                ModelPrice(
                    provider=item["provider"],
                    model=item["model"],
                    input_per_mtok=Decimal(str(item["input_per_mtok"])),
                    output_per_mtok=Decimal(str(item["output_per_mtok"])),
                    currency=item.get("currency", "USD"),
                    source=item["source"],
                    checked_on=date.fromisoformat(item["checked_on"]),
                )
            )
        return table


def add_money(*amounts: Money) -> Money:
    """Sum costs without going through float.

    Mixed currencies are refused rather than converted. A conversion needs a rate, a rate
    needs a date, and quietly picking one would make the total look authoritative while
    being arbitrary.
    """
    if not amounts:
        return Money(amount="0", currency="USD")
    currencies = {m.currency for m in amounts}
    if len(currencies) > 1:
        raise ValueError(
            f"cannot add costs in different currencies ({', '.join(sorted(currencies))}); "
            "convert them deliberately, with a rate and a date you can point at"
        )
    total = sum((Decimal(m.amount) for m in amounts), Decimal(0))
    return Money(
        amount=_plain(total.quantize(_CENTS, rounding=ROUND_HALF_UP)),
        currency=amounts[0].currency,
    )
