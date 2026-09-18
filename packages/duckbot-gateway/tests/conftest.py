"""Fixtures shared across the gateway tests.

Nothing here touches a network, and no fixture carries a real price. The prices below
are invented round numbers chosen so that the arithmetic in a failing test is obvious at
a glance.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from duckbot_schemas import ModelTier, SensitivityLevel

from duckbot_gateway import (
    Capability,
    ModelDescriptor,
    ModelPrice,
    PriceTable,
)

TEXT = frozenset({Capability.TEXT})


@pytest.fixture
def local_descriptor() -> ModelDescriptor:
    return ModelDescriptor(
        provider="ollama",
        model="small-local",
        tier=ModelTier.LOCAL,
        context_window=8_000,
        max_sensitivity=SensitivityLevel.LOCAL_ONLY,
        capabilities=frozenset({Capability.TEXT, Capability.TRADITIONAL_CHINESE}),
    )


@pytest.fixture
def cheap_descriptor() -> ModelDescriptor:
    return ModelDescriptor(
        provider="example-cheap",
        model="fast-1",
        tier=ModelTier.LOW_COST,
        context_window=32_000,
        max_sensitivity=SensitivityLevel.ANONYMIZE,
        capabilities=frozenset({Capability.TEXT}),
    )


@pytest.fixture
def frontier_descriptor() -> ModelDescriptor:
    return ModelDescriptor(
        provider="example-frontier",
        model="big-1",
        tier=ModelTier.FRONTIER,
        context_window=200_000,
        max_sensitivity=SensitivityLevel.ANONYMIZE,
        capabilities=frozenset(
            {
                Capability.TEXT,
                Capability.TOOL_USE,
                Capability.VISION,
                Capability.TRADITIONAL_CHINESE,
            }
        ),
    )


@pytest.fixture
def prices(cheap_descriptor: ModelDescriptor, frontier_descriptor: ModelDescriptor) -> PriceTable:
    """Invented prices. One dollar and ten dollars per million, to keep sums readable."""
    return PriceTable(
        [
            ModelPrice(
                provider=cheap_descriptor.provider,
                model=cheap_descriptor.model,
                input_per_mtok=Decimal("1"),
                output_per_mtok=Decimal("2"),
                currency="USD",
                source="invented for tests",
                checked_on=date(2026, 9, 1),
            ),
            ModelPrice(
                provider=frontier_descriptor.provider,
                model=frontier_descriptor.model,
                input_per_mtok=Decimal("10"),
                output_per_mtok=Decimal("20"),
                currency="USD",
                source="invented for tests",
                checked_on=date(2026, 9, 1),
            ),
        ]
    )
