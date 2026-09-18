"""Lexical retrieval.

These tests describe what lexical search does *and* what it does not: a paraphrase test
asserts a miss, because the package claims to be lexical and that claim should be
enforced rather than merely written down.
"""

from __future__ import annotations

from duckbot_schemas import MemoryItem, SensitivityLevel

from conftest import memory
from duckbot_memory import EmbeddingIndex, LexicalIndex, LocalOnlyViolation


def texts(hits: list) -> list[str]:
    return [h.item.text for h in hits]


class TestSearch:
    def test_a_chinese_query_finds_chinese_memories(self, index: LexicalIndex) -> None:
        found = texts(index.search("年度審計"))
        assert len(found) == 2
        assert all("年度審計" in t for t in found)

    def test_an_english_query_finds_english_memories(self, index: LexicalIndex) -> None:
        assert texts(index.search("tenancy")) == ["The tenancy agreement renewal is due in March"]

    def test_a_name_is_findable(self, index: LexicalIndex) -> None:
        assert texts(index.search("陳嘉雯")) == ["客戶陳嘉雯的年度審計報告已完成"]

    def test_an_unrelated_query_finds_nothing(self, index: LexicalIndex) -> None:
        assert index.search("量子力學") == []

    def test_an_empty_query_finds_nothing(self, index: LexicalIndex) -> None:
        assert index.search("") == []

    def test_a_paraphrase_is_missed_and_that_is_the_documented_behaviour(
        self, index: LexicalIndex
    ) -> None:
        """This is lexical search. 租約 shares no characters with tenancy agreement.

        If this test ever starts passing, something semantic has been added, and the
        README's claim about what this package does needs to change with it.
        """
        assert index.search("租約續期") == []

    def test_results_are_ordered_and_stable(self, index: LexicalIndex) -> None:
        """A retrieval layer that shuffles equal results makes every bug above it
        irreproducible."""
        first = [h.item.id for h in index.search("年度審計")]
        assert first == [h.item.id for h in index.search("年度審計")]

    def test_the_limit_is_respected(self, index: LexicalIndex) -> None:
        assert len(index.search("年度審計", limit=1)) == 1


class TestMaintenance:
    def test_adding_the_same_item_twice_does_not_double_count(self) -> None:
        index = LexicalIndex()
        item = memory("年度審計")
        index.add(item)
        index.add(item)
        assert len(index) == 1

    def test_removing_takes_it_out_of_results(self, index: LexicalIndex, items: list) -> None:
        assert index.remove(items[0].id)
        assert items[0].text not in texts(index.search("年度審計"))

    def test_removing_something_absent_is_false_not_an_error(self) -> None:
        assert not LexicalIndex().remove("mem_nothing")

    def test_rebuild_replaces_everything(self, index: LexicalIndex) -> None:
        index.rebuild([memory("完全不同的內容")])
        assert len(index) == 1
        assert index.search("年度審計") == []

    def test_an_empty_index_searches_without_dividing_by_zero(self) -> None:
        assert LexicalIndex().search("anything") == []


class LocalEmbedder:
    @property
    def is_local(self) -> bool:
        return True

    def embed(self, text: str) -> list[float]:
        return [float(len(text))]


class RemoteEmbedder:
    def __init__(self) -> None:
        self.seen: list[str] = []

    @property
    def is_local(self) -> bool:
        return False

    def embed(self, text: str) -> list[float]:
        self.seen.append(text)
        return [float(len(text))]


class TestEmbeddingRule:
    def test_a_remote_embedder_never_sees_local_only_text(self) -> None:
        """Refused before the call, not caught by a validator afterwards."""
        embedder = RemoteEmbedder()
        item = memory("身份證 A123456(3)", sensitivity=SensitivityLevel.LOCAL_ONLY)
        try:
            EmbeddingIndex(embedder).embed_item(item)
        except LocalOnlyViolation:
            pass
        else:  # pragma: no cover - the assertion below reports it
            raise AssertionError("expected LocalOnlyViolation")
        assert embedder.seen == [], "the text must not have been transmitted"

    def test_a_local_embedder_may(self) -> None:
        item = memory("身份證 A123456(3)", sensitivity=SensitivityLevel.LOCAL_ONLY)
        embedded = EmbeddingIndex(LocalEmbedder()).embed_item(item)
        assert embedded.embedding_ref
        assert not embedded.embedded_remotely

    def test_a_remote_embedder_may_take_less_sensitive_memories(self) -> None:
        embedded = EmbeddingIndex(RemoteEmbedder()).embed_item(memory("報價單"))
        assert embedded.embedded_remotely

    def test_the_schema_refuses_the_combination_as_well(self) -> None:
        """Two locks: this package refuses to do it, the schema refuses to record it."""
        item = memory("x", sensitivity=SensitivityLevel.LOCAL_ONLY)
        try:
            MemoryItem.model_validate({**item.model_dump(), "embedded_remotely": True})
        except ValueError:
            return
        raise AssertionError("the schema should refuse this")
