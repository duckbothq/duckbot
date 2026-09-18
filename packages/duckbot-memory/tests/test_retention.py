"""Retention, which only counts if something actually deletes."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest
from duckbot_schemas import RetentionPolicy

from conftest import NOW, memory
from duckbot_memory import (
    InMemoryMemoryStore,
    RetentionSweeper,
    SqliteMemoryStore,
    expires_at,
    is_expired,
)


class TestDeadlines:
    def test_thirty_days_means_thirty_days(self) -> None:
        item = memory("x", retention=RetentionPolicy.DAYS_30)
        assert expires_at(item) == item.created_at + timedelta(days=30)

    def test_a_year_means_a_year(self) -> None:
        item = memory("x", retention=RetentionPolicy.DAYS_365)
        assert expires_at(item) == item.created_at + timedelta(days=365)

    @pytest.mark.parametrize("policy", [RetentionPolicy.SESSION, RetentionPolicy.INDEFINITE])
    def test_the_two_policies_with_no_clock_have_no_deadline(self, policy: RetentionPolicy) -> None:
        assert expires_at(memory("x", retention=policy)) is None

    def test_age_is_measured_from_creation_not_from_last_use(self) -> None:
        """ "Kept for 30 days" must not quietly become "30 days after you stop using it"."""
        item = memory("x", retention=RetentionPolicy.DAYS_30, age_days=31)
        recently_used = item.model_copy(update={"last_used_at": NOW})
        assert is_expired(recently_used, NOW)

    def test_an_item_is_not_expired_on_the_day_before(self) -> None:
        assert not is_expired(memory("x", retention=RetentionPolicy.DAYS_30, age_days=29), NOW)

    def test_an_indefinite_item_never_expires(self) -> None:
        old = memory("x", retention=RetentionPolicy.INDEFINITE, age_days=10_000)
        assert not is_expired(old, NOW)


@pytest.fixture
def store() -> InMemoryMemoryStore:
    store = InMemoryMemoryStore()
    for item in (
        memory("fresh", retention=RetentionPolicy.DAYS_30, age_days=1),
        memory("stale", retention=RetentionPolicy.DAYS_30, age_days=45),
        memory("ancient", retention=RetentionPolicy.DAYS_365, age_days=400),
        memory("forever", retention=RetentionPolicy.INDEFINITE, age_days=4000),
        memory("this session", retention=RetentionPolicy.SESSION, age_days=0),
    ):
        store.put(item)
    return store


class TestSweeping:
    def test_it_deletes_what_is_past_its_date(self, store: InMemoryMemoryStore) -> None:
        result = RetentionSweeper(store).sweep(now=NOW)
        assert result.deleted == 2
        assert {i.text for i in store.all_items()} == {"fresh", "forever", "this session"}

    def test_a_dry_run_changes_nothing(self, store: InMemoryMemoryStore) -> None:
        """The first question anybody asks is "what would this remove"."""
        before = store.count()
        result = RetentionSweeper(store).sweep(now=NOW, dry_run=True)
        assert result.would_delete == 2
        assert result.deleted == 0
        assert store.count() == before

    def test_sweeping_does_not_touch_session_memory(self, store: InMemoryMemoryStore) -> None:
        """A session ending is not a clock event; different trigger, different method."""
        RetentionSweeper(store).sweep(now=NOW)
        assert any(i.retention is RetentionPolicy.SESSION for i in store.all_items())

    def test_ending_the_session_drops_session_memory_only(self, store: InMemoryMemoryStore) -> None:
        result = RetentionSweeper(store).end_session()
        assert result.deleted == 1
        assert not any(i.retention is RetentionPolicy.SESSION for i in store.all_items())
        assert any(i.text == "stale" for i in store.all_items())

    def test_the_result_reports_what_was_examined(self, store: InMemoryMemoryStore) -> None:
        assert RetentionSweeper(store).sweep(now=NOW).examined == 5


class TestForgetting:
    def test_an_erasure_request_is_its_own_act(self, store: InMemoryMemoryStore) -> None:
        """Somebody asking to be forgotten is not a special case of housekeeping."""
        target = next(i for i in store.all_items() if i.text == "forever")
        assert RetentionSweeper(store).forget([target.id]) == 1
        assert store.get(target.id) is None

    def test_forgetting_something_absent_removes_nothing(self, store: InMemoryMemoryStore) -> None:
        assert RetentionSweeper(store).forget(["mem_nothing"]) == 0


class TestSqliteStore:
    def test_it_round_trips(self, tmp_path: Path) -> None:
        item = memory("客戶陳嘉雯的年度審計報告")
        with SqliteMemoryStore(tmp_path / "memory.db") as store:
            store.put(item)
            loaded = store.get(item.id)
        assert loaded is not None
        assert loaded.text == item.text
        assert loaded.sensitivity is item.sensitivity

    def test_it_survives_reopening(self, tmp_path: Path) -> None:
        path = tmp_path / "memory.db"
        item = memory("persisted")
        with SqliteMemoryStore(path) as store:
            store.put(item)
        with SqliteMemoryStore(path) as store:
            assert store.count() == 1

    def test_delete_really_deletes(self, tmp_path: Path) -> None:
        """Unlike the audit log, memory must be removable. That is the point of retention."""
        item = memory("temporary")
        with SqliteMemoryStore(tmp_path / "memory.db") as store:
            store.put(item)
            assert store.delete(item.id)
            assert not store.delete(item.id)
            assert store.count() == 0

    def test_the_sweeper_works_over_sqlite_too(self, tmp_path: Path) -> None:
        with SqliteMemoryStore(tmp_path / "memory.db") as store:
            store.put(memory("stale", retention=RetentionPolicy.DAYS_30, age_days=45))
            store.put(memory("fresh", retention=RetentionPolicy.DAYS_30, age_days=1))
            assert RetentionSweeper(store).sweep(now=NOW).deleted == 1
            assert [i.text for i in store.all_items()] == ["fresh"]

    def test_deleting_nothing_is_not_an_error(self, tmp_path: Path) -> None:
        with SqliteMemoryStore(tmp_path / "memory.db") as store:
            assert store.delete_many([]) == 0

    def test_putting_the_same_id_twice_updates(self, tmp_path: Path) -> None:
        item = memory("first")
        with SqliteMemoryStore(tmp_path / "memory.db") as store:
            store.put(item)
            store.put(item.model_copy(update={"text": "second"}))
            assert store.count() == 1
            stored = store.get(item.id)
            assert stored is not None
            assert stored.text == "second"
