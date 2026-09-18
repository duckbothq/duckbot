"""Measuring detection quality.

The number that matters is **recall**, per entity type. An over-redaction annoys the
user; a missed HKID destroys the reason the product exists. Precision is reported too,
because a detector that redacts everything scores perfect recall and is useless — but
when the two conflict, recall wins.

A detection counts as a hit when it overlaps a ground-truth span of the same type.
Overlap rather than exact match is deliberate: a detector that catches ``9876 5432``
where the corpus marked ``+852 9876 5432`` has done the job that matters, which is
keeping the number out of the outbound payload.
"""

from __future__ import annotations

from dataclasses import dataclass

from .corpus import Document, Span
from .detectors import Detection, detect_all


@dataclass(frozen=True)
class EntityScore:
    entity_type: str
    expected: int
    found: int
    hits: int
    false_positives: int

    @property
    def recall(self) -> float:
        return self.hits / self.expected if self.expected else 1.0

    @property
    def precision(self) -> float:
        return self.hits / self.found if self.found else 1.0


@dataclass(frozen=True)
class CorpusScore:
    per_entity: tuple[EntityScore, ...]
    missed: tuple[tuple[str, Span], ...]

    @property
    def overall_recall(self) -> float:
        expected = sum(s.expected for s in self.per_entity)
        hits = sum(s.hits for s in self.per_entity)
        return hits / expected if expected else 1.0

    def format_report(self) -> str:
        lines = [
            f"{'entity':<14}{'expected':>9}{'found':>7}{'hits':>6}{'recall':>9}{'precision':>11}",
            "-" * 56,
        ]
        for s in sorted(self.per_entity, key=lambda x: x.entity_type):
            lines.append(
                f"{s.entity_type:<14}{s.expected:>9}{s.found:>7}{s.hits:>6}"
                f"{s.recall:>9.1%}{s.precision:>11.1%}"
            )
        lines.append("-" * 56)
        lines.append(f"{'overall recall':<14}{self.overall_recall:>38.1%}")
        if self.missed:
            lines.append("")
            lines.append("missed:")
            for doc_id, span in self.missed:
                lines.append(f"  {doc_id:<24} {span.entity_type:<14} {span.text!r}")
        return "\n".join(lines)


def _overlaps(a_start: int, a_end: int, b_start: int, b_end: int) -> bool:
    return a_start < b_end and b_start < a_end


def score(documents: list[Document]) -> CorpusScore:
    expected: dict[str, int] = {}
    found: dict[str, int] = {}
    hits: dict[str, int] = {}
    missed: list[tuple[str, Span]] = []

    for doc in documents:
        detections: list[Detection] = detect_all(doc.text)
        for d in detections:
            found[d.entity_type] = found.get(d.entity_type, 0) + 1

        matched_detections: set[int] = set()
        for span in doc.spans:
            expected[span.entity_type] = expected.get(span.entity_type, 0) + 1
            hit_index = next(
                (
                    i
                    for i, d in enumerate(detections)
                    if i not in matched_detections
                    and d.entity_type == span.entity_type
                    and _overlaps(d.start, d.end, span.start, span.end)
                ),
                None,
            )
            if hit_index is None:
                missed.append((doc.id, span))
            else:
                matched_detections.add(hit_index)
                hits[span.entity_type] = hits.get(span.entity_type, 0) + 1

    entity_types = sorted(set(expected) | set(found))
    per_entity = tuple(
        EntityScore(
            entity_type=t,
            expected=expected.get(t, 0),
            found=found.get(t, 0),
            hits=hits.get(t, 0),
            false_positives=max(0, found.get(t, 0) - hits.get(t, 0)),
        )
        for t in entity_types
    )
    return CorpusScore(per_entity=per_entity, missed=tuple(missed))
