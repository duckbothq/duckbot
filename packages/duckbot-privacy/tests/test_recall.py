"""Scoring, and the regression guard on the shipped number.

The threshold tests at the bottom are the point of this file. A detector change that
drops recall should fail CI, not be discovered by a customer. The thresholds sit a little
below the current figures so that ordinary corpus growth does not break the build, and
they are raised deliberately, not drifted into.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from duckbot_privacy.corpus import Document, load_documents, parse_marked
from duckbot_privacy.recall import CorpusScore, EntityScore, score

CORPUS_PATH = Path(__file__).resolve().parents[1] / "corpus" / "hk_business_v1.json"


def document(marked: str, doc_id: str = "d1") -> Document:
    text, spans = parse_marked(marked)
    return Document(id=doc_id, language="zh-Hant", description="test", text=text, spans=spans)


class TestEntityScore:
    def test_recall_and_precision(self) -> None:
        s = EntityScore("HKID", expected=4, found=5, hits=3, false_positives=2)
        assert s.recall == pytest.approx(0.75)
        assert s.precision == pytest.approx(0.6)

    def test_an_entity_nobody_marked_is_not_a_failure(self) -> None:
        s = EntityScore("HKID", expected=0, found=0, hits=0, false_positives=0)
        assert s.recall == 1.0
        assert s.precision == 1.0


class TestScoring:
    def test_a_fully_detected_document_scores_perfectly(self) -> None:
        result = score([document("客戶[[PERSON_NAME:陳嘉雯]]，身份證 [[HKID:A123456(3)]]。")])
        assert result.overall_recall == 1.0
        assert result.missed == ()

    def test_a_missed_span_is_named_not_averaged_away(self) -> None:
        """A report that gives only a percentage cannot be acted on."""
        result = score([document("就[[PERSON_NAME:張明輝]]客戶的年度審計。", doc_id="memo")])
        assert result.overall_recall == 0.0
        ((doc_id, span),) = result.missed
        assert doc_id == "memo"
        assert span.text == "張明輝"

    def test_a_partial_overlap_counts_as_a_hit(self) -> None:
        """Catching 9876 5432 where the corpus marked +852 9876 5432 did the job."""
        result = score([document("電話 +852 [[PHONE:9876 5432]]。")])
        assert result.overall_recall == 1.0

    def test_false_positives_lower_precision_but_not_recall(self) -> None:
        marked = "客戶[[PERSON_NAME:陳嘉雯]]，身份證 A123456(3)。"
        result = score([document(marked)])
        assert result.overall_recall == 1.0
        (hkid_score,) = [s for s in result.per_entity if s.entity_type == "HKID"]
        assert hkid_score.expected == 0
        assert hkid_score.found == 1
        assert hkid_score.false_positives == 1

    def test_scores_are_aggregated_across_documents(self) -> None:
        result = score(
            [
                document("身份證 [[HKID:A123456(3)]]", doc_id="a"),
                document("身份證 [[HKID:K470285(9)]]", doc_id="b"),
            ]
        )
        (hkid_score,) = [s for s in result.per_entity if s.entity_type == "HKID"]
        assert hkid_score.expected == 2
        assert hkid_score.hits == 2

    def test_an_empty_corpus_does_not_divide_by_zero(self) -> None:
        assert score([]).overall_recall == 1.0


class TestReport:
    def test_it_names_each_entity_type_and_the_misses(self) -> None:
        result = score(
            [document("就[[PERSON_NAME:張明輝]]客戶，身份證 [[HKID:A123456(3)]]。", doc_id="memo")]
        )
        report = result.format_report()
        assert "PERSON_NAME" in report
        assert "HKID" in report
        assert "memo" in report
        assert "張明輝" in report


@pytest.fixture(scope="module")
def shipped() -> CorpusScore:
    return score(load_documents(CORPUS_PATH))


class TestTheShippedNumber:
    """If these fail, detection got worse. Find out why before changing the threshold."""

    def test_overall_recall_does_not_regress(self, shipped: CorpusScore) -> None:
        assert shipped.overall_recall >= 0.95

    @pytest.mark.parametrize(
        "entity_type", ["HKID", "PHONE", "EMAIL", "BR_NUMBER", "MONEY", "SALARY"]
    )
    def test_structured_entities_are_caught_in_full(
        self, shipped: CorpusScore, entity_type: str
    ) -> None:
        """These have structure. Rules are exactly what structure is for, so 100% or a bug."""
        (entity_score,) = [s for s in shipped.per_entity if s.entity_type == entity_type]
        assert entity_score.recall == 1.0

    def test_name_recall_does_not_regress(self, shipped: CorpusScore) -> None:
        """Names are the local model's job; this floor stops the rules going backwards.

        If this ever reads 100%, that is a reason to grow the corpus, not to describe the
        problem as solved — ten documents are easy to overfit, and the README should not
        start claiming names are handled by rules.
        """
        (names,) = [s for s in shipped.per_entity if s.entity_type == "PERSON_NAME"]
        assert names.recall >= 0.85

    def test_precision_stays_high(self, shipped: CorpusScore) -> None:
        """Recall wins when they conflict, but a detector that redacts everything is useless."""
        found = sum(s.found for s in shipped.per_entity)
        hits = sum(s.hits for s in shipped.per_entity)
        assert hits / found >= 0.95
