"""Fixtures. Every memory in these tests is invented."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from duckbot_schemas import MemoryItem, RetentionPolicy, SensitivityLevel

from duckbot_memory import LexicalIndex

NOW = datetime(2026, 9, 18, 12, 0, tzinfo=UTC)


def memory(
    text: str,
    *,
    source: str = "notes",
    sensitivity: SensitivityLevel = SensitivityLevel.MINIMIZE,
    retention: RetentionPolicy = RetentionPolicy.DAYS_365,
    age_days: int = 0,
) -> MemoryItem:
    return MemoryItem(
        source=source,
        text=text,
        sensitivity=sensitivity,
        retention=retention,
        created_at=NOW - timedelta(days=age_days),
    )


@pytest.fixture
def items() -> list[MemoryItem]:
    return [
        memory("客戶陳嘉雯的年度審計報告已完成", source="email"),
        memory("年度審計的付款安排是分兩期", source="notes"),
        memory("辦公室傢俬報價單，預算約四萬八", source="quotation"),
        memory("The tenancy agreement renewal is due in March", source="email"),
    ]


@pytest.fixture
def index(items: list[MemoryItem]) -> LexicalIndex:
    built = LexicalIndex()
    built.rebuild(items)
    return built
