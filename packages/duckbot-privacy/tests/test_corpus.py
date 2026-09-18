"""The corpus loader, and invariants the shipped corpus must satisfy.

The loader exists so that whoever adds a document writes readable text instead of
counting characters. If offsets had to be maintained by hand, the corpus would rot and
the recall figure would quietly stop meaning anything.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from duckbot_privacy import hkid
from duckbot_privacy.corpus import Document, load_documents, parse_marked
from duckbot_privacy.detectors import detect_all

CORPUS_PATH = Path(__file__).resolve().parents[1] / "corpus" / "hk_business_v1.json"


class TestParseMarked:
    def test_markers_are_stripped(self) -> None:
        text, _ = parse_marked("客戶[[PERSON_NAME:陳嘉雯]]已確認。")
        assert text == "客戶陳嘉雯已確認。"

    def test_offsets_address_the_clean_text(self) -> None:
        text, spans = parse_marked("客戶[[PERSON_NAME:陳嘉雯]]已確認。")
        (span,) = spans
        assert text[span.start : span.end] == span.text == "陳嘉雯"
        assert span.entity_type == "PERSON_NAME"

    def test_several_markers_stay_aligned(self) -> None:
        text, spans = parse_marked(
            "[[PERSON_NAME:李偉明]]的電話是 [[PHONE:2345 6789]]，電郵 [[EMAIL:wm.lee@example.hk]]。"
        )
        assert len(spans) == 3
        for span in spans:
            assert text[span.start : span.end] == span.text

    def test_text_without_markers_is_returned_unchanged(self) -> None:
        text, spans = parse_marked("沒有敏感資料。")
        assert text == "沒有敏感資料。"
        assert spans == ()


@pytest.fixture(scope="module")
def documents() -> list[Document]:
    return load_documents(CORPUS_PATH)


class TestShippedCorpus:
    def test_it_loads(self, documents: list[Document]) -> None:
        assert len(documents) >= 10

    def test_ids_are_unique(self, documents: list[Document]) -> None:
        ids = [d.id for d in documents]
        assert len(ids) == len(set(ids))

    def test_every_span_matches_its_text(self, documents: list[Document]) -> None:
        for doc in documents:
            for span in doc.spans:
                assert doc.text[span.start : span.end] == span.text, doc.id

    def test_both_languages_are_represented(self, documents: list[Document]) -> None:
        assert {"zh-Hant", "en"} <= {d.language for d in documents}

    def test_every_marked_hkid_has_a_correct_check_digit(self, documents: list[Document]) -> None:
        """An invented HKID with a wrong check digit would make the corpus lie.

        The detector discards numbers that fail the check digit, so a bad fixture would
        show up as a recall failure that no change to the detector could fix.
        """
        marked = [s.text for d in documents for s in d.spans if s.entity_type == "HKID"]
        assert marked
        for value in marked:
            assert hkid.find_all(value), value

    def test_the_clean_document_provokes_nothing(self, documents: list[Document]) -> None:
        """Over-redaction guard. A detector that redacts everything scores well on recall."""
        (doc,) = [d for d in documents if d.id == "no-sensitive-data"]
        assert doc.spans == ()
        assert detect_all(doc.text) == []

    def test_the_false_positive_bait_provokes_nothing(self, documents: list[Document]) -> None:
        (doc,) = [d for d in documents if d.id == "near-miss-identifiers"]
        assert doc.spans == ()
        assert detect_all(doc.text) == []
